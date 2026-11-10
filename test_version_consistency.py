"""Unit tests for the documentation/version inventory checker."""
import tempfile
import unittest
from pathlib import Path

import check_versions as checker


class ClassificationTests(unittest.TestCase):
    def test_current_documents(self):
        for name in checker.CURRENT_DOCS:
            self.assertEqual(checker.classify_doc(name), "current")

    def test_historical_phase_and_archive_paths(self):
        cases = (
            "README_UPDATE_PHASE86.md",
            "TEST_RESULTS_PHASE48.md",
            "docs/phases/phase-01-README.md",
            "docs/steps/step-01-chat-images.md",
            "docs/implementation/PHASE44_AUTH_SEPARATION.md",
            "docs/archive/legacy-notes.txt",
            "UPDATE-INSTRUCTIONS.txt",
        )
        for name in cases:
            with self.subTest(name=name):
                self.assertEqual(checker.classify_doc(name), "historical")

    def test_out_of_scope_documents(self):
        self.assertEqual(checker.classify_doc("android/README_ANDROID.md"), "out-of-scope")
        self.assertEqual(checker.classify_doc("DEPLOY.md"), "out-of-scope")

    def test_unknown_readme_is_not_silently_accepted(self):
        self.assertEqual(checker.classify_doc("misc/README_EXTRA.md"), "unclassified")

    def test_archive_notice(self):
        self.assertTrue(checker.has_archive_notice("ARCHIVE NOTICE\nold notes"))
        self.assertFalse(checker.has_archive_notice("# Current project\nold notes"))


class IntegrationTests(unittest.TestCase):
    def test_consistent_minimal_project_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "static").mkdir()
            (root / "VERSION").write_text("release=phase-90\ncache=laqino-v134\n", encoding="utf-8")
            (root / "static/sw.js").write_text('const V = "laqino-v134";\n', encoding="utf-8")
            for name in checker.CURRENT_DOCS:
                (root / name).write_text(
                    "# phase-90\ncache laqino-v134\n", encoding="utf-8"
                )
            errors, counts, release, cache = checker.run_check(root)
            self.assertEqual(errors, [])
            self.assertEqual(release, "phase-90")
            self.assertEqual(cache, "laqino-v134")
            self.assertEqual(counts["current"], 5)

    def test_missing_archive_notice_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "static").mkdir()
            (root / "docs" / "phases").mkdir(parents=True)
            (root / "VERSION").write_text("release=phase-90\ncache=laqino-v134\n", encoding="utf-8")
            (root / "static/sw.js").write_text('const V = "laqino-v134";\n', encoding="utf-8")
            for name in checker.CURRENT_DOCS:
                (root / name).write_text("# phase-90\ncache laqino-v134\n", encoding="utf-8")
            (root / "docs/phases/phase-01-README.md").write_text("# old phase\n", encoding="utf-8")
            errors, _, _, _ = checker.run_check(root)
            self.assertTrue(any("lacks archive notice" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
