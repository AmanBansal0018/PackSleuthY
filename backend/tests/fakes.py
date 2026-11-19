"""Fake registry HTTP responses for tests. No network calls are made."""

import io
import json
import urllib.error


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {}
        self._offset = 0

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self.body) - self._offset
        chunk = self.body[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self):
        return None


class FakeOpener:
    def __init__(self, routes):
        self.routes = routes

    def open(self, request, timeout=None):
        url = request.full_url
        if url not in self.routes:
            raise AssertionError(f"Unexpected URL: {url}")

        status, body, headers = self.routes[url]
        if isinstance(body, dict):
            body = json.dumps(body).encode("utf-8")
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "error", hdrs=None, fp=io.BytesIO(body))
        return FakeResponse(body, status, headers)
