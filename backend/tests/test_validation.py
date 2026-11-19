"""Tests for package name and version checks."""

import unittest

from registry_connectors.errors import InvalidPackageError
from registry_connectors.validation import validate_request


class ValidationTests(unittest.TestCase):
    def test_accepts_npm_and_pypi_names(self):
        self.assertEqual(
            validate_request("npm", " express ", " 4.18.2 "),
            ("npm", "express", "4.18.2"),
        )
        self.assertEqual(
            validate_request("pypi", "Requests", "2.31.0"),
            ("pypi", "Requests", "2.31.0"),
        )
        self.assertEqual(
            validate_request("npm", "@types/node", "20.11.0"),
            ("npm", "@types/node", "20.11.0"),
        )

    def test_rejects_unsafe_names_and_versions(self):
        rejected = [
            ("maven", "express", "4.18.2"),
            ("npm", "../express", "4.18.2"),
            ("npm", "express/../../x", "4.18.2"),
            ("npm", "bad name", "4.18.2"),
            ("pypi", "requests", "../1.0.0"),
            ("pypi", "requests", "1.0.0;rm"),
            ("npm", "", "1.0.0"),
            ("npm", "express", ""),
        ]
        for ecosystem, name, version in rejected:
            with self.assertRaises(InvalidPackageError):
                validate_request(ecosystem, name, version)

    def test_error_message_is_explicit(self):
        with self.assertRaisesRegex(InvalidPackageError, "Invalid package name or version"):
            validate_request("npm", "express", "../4")


if __name__ == "__main__":
    unittest.main()
