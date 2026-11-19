"""Compare a downloaded file with the hash published by a registry.

A match means the file is the same one the registry advertised.
It does not mean the package is safe.
"""

import base64
import hashlib
import hmac
import re

from registry_connectors.errors import IntegrityError

_HEX_SHA1 = re.compile(r"^[A-Fa-f0-9]{40}$")
_HEX_SHA256 = re.compile(r"^[A-Fa-f0-9]{64}$")
_SUPPORTED_SRI = {"sha1", "sha256", "sha384", "sha512"}

VERIFIED = "verified"
UNAVAILABLE = "unavailable"

VERIFIED_NOTE = (
    "The downloaded file matches the hash published by the registry. "
    "This does not mean the package is safe."
)
UNAVAILABLE_NOTE = (
    "The registry did not provide a supported hash, so the file was not verified. "
    "This does not mean the package is safe."
)


def verify_npm(hashes, integrity, shasum):
    """Check npm dist.integrity first, then dist.shasum when integrity is absent."""

    if isinstance(integrity, str) and integrity.strip():
        if len(integrity) > 4096:
            raise IntegrityError("Integrity verification failure: registry integrity value is malformed.")
        tokens = _parse_sri(integrity)
        for algorithm, expected in tokens:
            actual = hashes[algorithm].digest()
            if hmac.compare_digest(actual, expected):
                return VERIFIED
        raise IntegrityError(
            "Integrity verification failure: the downloaded file does not match the npm integrity hash."
        )

    if isinstance(shasum, str) and shasum.strip():
        if not _HEX_SHA1.fullmatch(shasum):
            raise IntegrityError("Integrity verification failure: npm published a malformed shasum.")
        actual = hashes["sha1"].hexdigest()
        if hmac.compare_digest(actual.lower(), shasum.lower()):
            return VERIFIED
        raise IntegrityError(
            "Integrity verification failure: the downloaded file does not match the npm shasum."
        )

    return UNAVAILABLE


def verify_pypi(hashes, expected_sha256):
    """Check the SHA-256 digest PyPI published for the selected file."""

    if not isinstance(expected_sha256, str) or not expected_sha256.strip():
        return UNAVAILABLE

    if not _HEX_SHA256.fullmatch(expected_sha256):
        raise IntegrityError("Integrity verification failure: PyPI published a malformed SHA-256 digest.")

    actual = hashes["sha256"].hexdigest()
    if not hmac.compare_digest(actual.lower(), expected_sha256.lower()):
        raise IntegrityError(
            "Integrity verification failure: the downloaded file does not match the PyPI SHA-256 digest."
        )
    return VERIFIED


def safety_note(status):
    if status == VERIFIED:
        return VERIFIED_NOTE
    return UNAVAILABLE_NOTE


def _parse_sri(integrity):
    parsed = []
    for token in integrity.split():
        if "-" not in token:
            raise IntegrityError("Integrity verification failure: registry integrity value is malformed.")
        algorithm, encoded = token.split("-", 1)
        algorithm = algorithm.lower()
        if algorithm not in _SUPPORTED_SRI:
            continue
        try:
            digest = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise IntegrityError("Integrity verification failure: registry integrity value is malformed.") from exc
        expected_length = hashlib.new(algorithm).digest_size
        if len(digest) != expected_length:
            raise IntegrityError("Integrity verification failure: registry integrity value is malformed.")
        parsed.append((algorithm, digest))

    if not parsed:
        raise IntegrityError("Integrity verification failure: unsupported integrity algorithm.")
    return parsed
