"""Small HTTP helper for the official npm and PyPI registries.

Downloads are streamed to disk. This module does not extract or run files.
"""

import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

from registry_connectors.errors import DownloadTooLargeError, NetworkError

USER_AGENT = "PackSleuthY/0.1 (package integrity checker; does not execute packages)"
TIMEOUT_SECONDS = 20
CHUNK_SIZE = 64 * 1024
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_METADATA_BYTES = 5 * 1024 * 1024


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when the next URL is still on an allowed host."""

    def __init__(self, allowed_hosts):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        ensure_allowed_url(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener(allowed_hosts):
    return urllib.request.build_opener(_AllowlistedRedirectHandler(allowed_hosts))


def ensure_allowed_url(url, allowed_hosts):
    """Reject any URL that is not HTTPS on one expected registry host."""

    if not isinstance(url, str):
        raise NetworkError("Network failure: the registry returned a download URL that was refused.")

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or host not in allowed_hosts
    ):
        raise NetworkError("Network failure: the registry returned a download URL that was refused.")
    return parsed


def get_json(url, allowed_hosts, opener=None):
    """Fetch a small JSON document. Returns (status, payload) for 200 and 404."""

    raw, status = _read_response(url, allowed_hosts, opener, accept="application/json", limit=MAX_METADATA_BYTES)
    if status == 404:
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        return 404, payload

    if status != 200:
        raise NetworkError(f"Network failure: the registry responded with HTTP {status}.")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NetworkError("Network failure: the registry returned data that was not valid JSON.") from exc
    return 200, payload


def stream_to_file(url, allowed_hosts, destination, opener=None, declared_size=None):
    """Stream a file to destination and return the hash objects plus byte count."""

    if declared_size is not None and declared_size > MAX_DOWNLOAD_BYTES:
        raise DownloadTooLargeError()

    ensure_allowed_url(url, allowed_hosts)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    active_opener = opener or build_opener(allowed_hosts)

    try:
        response = active_opener.open(request, timeout=TIMEOUT_SECONDS)
    except urllib.error.HTTPError as exc:
        exc.close()
        raise NetworkError(f"Network failure: the registry responded with HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise NetworkError("Network failure: the package download did not finish.") from exc

    try:
        _reject_large_content_length(response.headers)
        return _write_stream(response, destination)
    finally:
        response.close()


def _read_response(url, allowed_hosts, opener, accept, limit):
    ensure_allowed_url(url, allowed_hosts)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    active_opener = opener or build_opener(allowed_hosts)

    try:
        response = active_opener.open(request, timeout=TIMEOUT_SECONDS)
        status = getattr(response, "status", 200)
        try:
            return _read_limited(response, limit), status
        finally:
            response.close()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(limit + 1)
        finally:
            exc.close()
        if len(body) > limit:
            raise NetworkError("Network failure: the registry response was too large.") from exc
        return body, exc.code
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise NetworkError("Network failure: could not reach the package registry.") from exc


def _read_limited(response, limit):
    data = bytearray()
    while len(data) <= limit:
        chunk = response.read(min(CHUNK_SIZE, limit - len(data) + 1))
        if not chunk:
            break
        data.extend(chunk)
    if len(data) > limit:
        raise NetworkError("Network failure: the registry response was too large.")
    return bytes(data)


def _reject_large_content_length(headers):
    if headers is None:
        return
    raw_length = headers.get("Content-Length")
    if raw_length is None:
        return
    try:
        length = int(raw_length)
    except (TypeError, ValueError):
        return
    if length > MAX_DOWNLOAD_BYTES:
        raise DownloadTooLargeError()


def _write_stream(response, destination):
    import hashlib

    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    sha384 = hashlib.sha384()
    sha512 = hashlib.sha512()
    total = 0

    with destination.open("wb") as handle:
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            if total + len(chunk) > MAX_DOWNLOAD_BYTES:
                raise DownloadTooLargeError()
            total += len(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
            sha384.update(chunk)
            sha512.update(chunk)
            handle.write(chunk)

    return {
        "sha1": sha1,
        "sha256": sha256,
        "sha384": sha384,
        "sha512": sha512,
        "size": total,
    }
