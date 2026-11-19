import unittest
from source_discovery.service import _repo_slug

class SourceDiscoveryTests(unittest.TestCase):
    def test_accepts_github_repository_urls(self):
        self.assertEqual(_repo_slug("git+https://github.com/expressjs/express.git"), "expressjs/express")
        self.assertEqual(_repo_slug("https://www.github.com/psf/requests"), "psf/requests")

    def test_rejects_non_github_or_malformed_urls(self):
        self.assertIsNone(_repo_slug("https://example.com/owner/repo"))
        self.assertIsNone(_repo_slug("https://github.com/owner"))
        self.assertIsNone(_repo_slug("javascript:alert(1)"))
        self.assertIsNone(_repo_slug("https://github.com.evil.test/owner/repo"))

if __name__=="__main__": unittest.main()
