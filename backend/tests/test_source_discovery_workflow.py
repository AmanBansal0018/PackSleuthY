import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import source_discovery.service as source


class SourceDiscoveryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.storage = root / "packages"
        self.sources = root / "sources"
        self.metadata = root / "metadata"
        self.storage.mkdir()
        self.sources.mkdir()
        self.metadata.mkdir()
        self.artifact_id = "a" * 32
        (self.storage / f"{self.artifact_id}.tgz").write_bytes(b"package")
        self.patches = [
            patch.object(source, "STORAGE_DIR", self.storage),
            patch.object(source, "SOURCE_DIR", self.sources),
            patch.object(source, "META_DIR", self.metadata),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_exact_version_tag_downloads_source_archive(self):
        commit = "b" * 40
        api_responses = [
            [{"name": "v1.2.3", "commit": {"sha": commit}}],
            [],
        ]

        def fake_download(url, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"source zip")
            return 10

        with patch.object(source, "_metadata_for", return_value=({"repository": "x"}, ["https://github.com/acme/demo"])), \
             patch.object(source, "_get_json", side_effect=api_responses), \
             patch.object(source, "_download_github_archive", side_effect=fake_download):
            result = source.discover_source("npm", "demo", "1.2.3", self.artifact_id)

        self.assertEqual(result["match_status"], "confirmed")
        self.assertEqual(result["matching_tag"], "v1.2.3")
        self.assertEqual(result["commit_sha"], commit)
        self.assertTrue((self.sources / f"{result['source_archive_id']}.zip").is_file())

    def test_missing_exact_tag_does_not_fall_back_to_default_branch(self):
        api_responses = [[], [{"tag_name": "latest"}]]
        with patch.object(source, "_metadata_for", return_value=({}, ["https://github.com/acme/demo"])), \
             patch.object(source, "_get_json", side_effect=api_responses):
            result = source.discover_source("npm", "demo", "1.2.3", self.artifact_id)

        self.assertEqual(result["match_status"], "uncertain")
        self.assertIsNone(result["source_archive_id"])
        self.assertFalse(list(self.sources.glob("*.zip")))


if __name__ == "__main__":
    unittest.main()
