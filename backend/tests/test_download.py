"""Downloader tests with mocked registry responses."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.fakes import FakeOpener
from registry_connectors.artifacts import display_filename
from registry_connectors.errors import (
    DownloadTooLargeError,
    IntegrityError,
    NetworkError,
    NoDistributionError,
    PackageNotFoundError,
    VersionNotFoundError,
)
from registry_connectors.http_client import MAX_DOWNLOAD_BYTES, ensure_allowed_url
from registry_connectors.npm import parse_npm_metadata
from registry_connectors.pypi import parse_pypi_metadata
from registry_connectors.service import download_package


NPM_METADATA = "https://registry.npmjs.org/express/4.18.2"
NPM_TARBALL = "https://registry.npmjs.org/express/-/express-4.18.2.tgz"
PYPI_VERSION = "https://pypi.org/pypi/requests/2.31.0/json"
PYPI_PACKAGE = "https://pypi.org/pypi/requests/json"
PYPI_MISSING_PACKAGE = "https://pypi.org/pypi/not-a-real-package/json"
PYPI_MISSING_VERSION = "https://pypi.org/pypi/requests/9.9.9/json"
PYPI_FILE = "https://files.pythonhosted.org/packages/ab/cd/requests-2.31.0.tar.gz"


def npm_document(content, integrity=None, shasum=None, tarball=NPM_TARBALL):
    import base64
    import hashlib

    dist = {"tarball": tarball}
    if integrity is not False:
        digest = base64.b64encode(hashlib.sha512(content).digest()).decode("ascii")
        dist["integrity"] = integrity or f"sha512-{digest}"
    if shasum is not False:
        dist["shasum"] = shasum or hashlib.sha1(content).hexdigest()
    return {"dist": dist}


class DownloadTests(unittest.TestCase):
    def test_npm_download_saves_a_verified_file_without_using_the_registry_name(self):
        content = b"fake-npm-tarball"
        opener = FakeOpener({
            NPM_METADATA: (200, npm_document(content), {}),
            NPM_TARBALL: (200, content, {"Content-Length": str(len(content))}),
        })

        with TemporaryDirectory() as temp_dir:
            result = download_package("npm", "express", "4.18.2", opener, temp_dir)
            saved = list(Path(temp_dir).iterdir())

            self.assertEqual(result["artifact_filename"], "express-4.18.2.tgz")
            self.assertEqual(result["artifact_type"], "tarball")
            self.assertEqual(result["file_size_bytes"], len(content))
            self.assertEqual(result["integrity_verification_status"], "verified")
            self.assertEqual(result["registry_download_url"], NPM_TARBALL)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].name, f"{result['saved_artifact_id']}.tgz")
            self.assertEqual(saved[0].read_bytes(), content)
            self.assertNotIn("safe", result["integrity_verification_status"])

    def test_integrity_mismatch_deletes_the_download(self):
        content = b"fake-npm-tarball"
        import base64
        import hashlib

        wrong = base64.b64encode(hashlib.sha512(b"other").digest()).decode("ascii")
        opener = FakeOpener({
            NPM_METADATA: (200, npm_document(content, integrity=f"sha512-{wrong}"), {}),
            NPM_TARBALL: (200, content, {}),
        })

        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(IntegrityError, "Integrity verification failure"):
                download_package("npm", "express", "4.18.2", opener, temp_dir)
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_npm_reports_missing_package_and_version(self):
        missing_package = FakeOpener({
            NPM_METADATA: (404, {"error": "Not found"}, {}),
        })
        missing_version = FakeOpener({
            NPM_METADATA: (404, {"error": "version not found: express@4.18.2"}, {}),
        })

        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(PackageNotFoundError, "Package not found"):
                download_package("npm", "express", "4.18.2", missing_package, temp_dir)
            with self.assertRaisesRegex(VersionNotFoundError, "Version not found"):
                download_package("npm", "express", "4.18.2", missing_version, temp_dir)

    def test_pypi_prefers_sdist_and_checks_sha256(self):
        import hashlib

        content = b"fake-sdist"
        opener = FakeOpener({
            PYPI_VERSION: (200, {
                "urls": [
                    {
                        "filename": "requests-2.31.0-py3-none-any.whl",
                        "packagetype": "bdist_wheel",
                        "url": "https://files.pythonhosted.org/packages/ab/cd/requests-2.31.0-py3-none-any.whl",
                        "digests": {"sha256": "b" * 64},
                        "size": 10,
                    },
                    {
                        "filename": "requests-2.31.0.tar.gz",
                        "packagetype": "sdist",
                        "url": PYPI_FILE,
                        "digests": {"sha256": hashlib.sha256(content).hexdigest()},
                        "size": len(content),
                    },
                ]
            }, {}),
            PYPI_FILE: (200, content, {}),
        })

        with TemporaryDirectory() as temp_dir:
            result = download_package("pypi", "requests", "2.31.0", opener, temp_dir)
            self.assertEqual(result["artifact_type"], "sdist")
            self.assertEqual(result["artifact_filename"], "requests-2.31.0.tar.gz")
            self.assertEqual(result["integrity_verification_status"], "verified")
            self.assertTrue(result["sha256"])

    def test_pypi_uses_a_wheel_when_no_sdist_exists(self):
        metadata = parse_pypi_metadata({
            "urls": [
                {
                    "filename": "demo-1.0.0-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "url": "https://files.pythonhosted.org/packages/aa/bb/demo-1.0.0-py3-none-any.whl",
                    "digests": {"sha256": "c" * 64},
                    "size": 4,
                }
            ]
        }, "demo", "1.0.0")
        self.assertEqual(metadata.artifact_type, "wheel")

    def test_pypi_distinguishes_missing_package_from_missing_version(self):
        missing_package = FakeOpener({
            "https://pypi.org/pypi/not-a-real-package/0.0.1/json": (404, {"message": "Not Found"}, {}),
            PYPI_MISSING_PACKAGE: (404, {"message": "Not Found"}, {}),
        })
        missing_version = FakeOpener({
            PYPI_MISSING_VERSION: (404, {"message": "Not Found"}, {}),
            PYPI_PACKAGE: (200, {"info": {"name": "requests"}}, {}),
        })

        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(PackageNotFoundError):
                download_package("pypi", "not-a-real-package", "0.0.1", missing_package, temp_dir)
            with self.assertRaises(VersionNotFoundError):
                download_package("pypi", "requests", "9.9.9", missing_version, temp_dir)

    def test_pypi_without_a_file_is_an_error(self):
        with self.assertRaises(NoDistributionError):
            parse_pypi_metadata({"urls": []}, "demo", "1.0.0")

    def test_download_stops_when_the_file_is_larger_than_50_mb(self):
        opener = FakeOpener({
            NPM_METADATA: (200, npm_document(b"small", tarball=NPM_TARBALL), {}),
            NPM_TARBALL: (200, b"x" * 10, {"Content-Length": str(MAX_DOWNLOAD_BYTES + 1)}),
        })
        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(DownloadTooLargeError, "Download too large"):
                download_package("npm", "express", "4.18.2", opener, temp_dir)
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_stream_limit_stops_a_response_without_content_length(self):
        import registry_connectors.http_client as http_client

        opener = FakeOpener({
            NPM_METADATA: (200, npm_document(b"small"), {}),
            NPM_TARBALL: (200, b"x" * 9, {}),
        })
        original_limit = http_client.MAX_DOWNLOAD_BYTES
        http_client.MAX_DOWNLOAD_BYTES = 8
        try:
            with TemporaryDirectory() as temp_dir:
                with self.assertRaises(DownloadTooLargeError):
                    download_package("npm", "express", "4.18.2", opener, temp_dir)
                self.assertEqual(list(Path(temp_dir).iterdir()), [])
        finally:
            http_client.MAX_DOWNLOAD_BYTES = original_limit

    def test_registry_filename_and_url_cannot_escape_storage(self):
        self.assertEqual(display_filename("../../etc/passwd", "tarball"), "package.tgz")
        self.assertEqual(display_filename("..", "sdist"), "package.tar.gz")
        with self.assertRaises(NetworkError):
            ensure_allowed_url("https://example.com/passwd", {"registry.npmjs.org"})
        with self.assertRaises(NetworkError):
            ensure_allowed_url("http://registry.npmjs.org/express.tgz", {"registry.npmjs.org"})
        with self.assertRaises(NetworkError):
            parse_npm_metadata({
                "dist": {"tarball": "https://evil.example/express.tgz", "integrity": "sha512-aaaa"}
            }, "express", "4.18.2")


if __name__ == "__main__":
    unittest.main()
