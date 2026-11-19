"""Integrity checks using hashes, without talking to a real registry."""

import base64
import hashlib
import unittest

from registry_connectors.errors import IntegrityError
from registry_connectors.integrity import UNAVAILABLE, VERIFIED, safety_note, verify_npm, verify_pypi


def hashes_for(content):
    return {
        "sha1": hashlib.sha1(content),
        "sha256": hashlib.sha256(content),
        "sha384": hashlib.sha384(content),
        "sha512": hashlib.sha512(content),
    }


class IntegrityTests(unittest.TestCase):
    def test_npm_sha512_match_is_verified_but_not_called_safe(self):
        content = b"package-bytes"
        digest = base64.b64encode(hashlib.sha512(content).digest()).decode("ascii")
        status = verify_npm(hashes_for(content), f"sha512-{digest}", "0" * 40)

        self.assertEqual(status, VERIFIED)
        self.assertIn("does not mean the package is safe", safety_note(status))

    def test_npm_uses_shasum_when_integrity_is_missing(self):
        content = b"package-bytes"
        status = verify_npm(hashes_for(content), None, hashlib.sha1(content).hexdigest())
        self.assertEqual(status, VERIFIED)

    def test_npm_mismatch_is_an_error(self):
        content = b"package-bytes"
        wrong = base64.b64encode(hashlib.sha512(b"other").digest()).decode("ascii")
        with self.assertRaisesRegex(IntegrityError, "Integrity verification failure"):
            verify_npm(hashes_for(content), f"sha512-{wrong}", hashlib.sha1(content).hexdigest())

    def test_npm_without_a_hash_is_unavailable(self):
        status = verify_npm(hashes_for(b"package-bytes"), None, None)
        self.assertEqual(status, UNAVAILABLE)
        self.assertIn("does not mean the package is safe", safety_note(status))

    def test_pypi_sha256_match_and_mismatch(self):
        content = b"sdist-bytes"
        hashes = hashes_for(content)
        self.assertEqual(verify_pypi(hashes, hashlib.sha256(content).hexdigest()), VERIFIED)
        with self.assertRaisesRegex(IntegrityError, "Integrity verification failure"):
            verify_pypi(hashes, "a" * 64)

    def test_pypi_without_sha256_is_unavailable(self):
        self.assertEqual(verify_pypi(hashes_for(b"sdist-bytes"), None), UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
