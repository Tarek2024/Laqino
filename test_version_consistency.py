"""Regression test for the single release/cache source and archived documentation labels."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class VersionConsistencyTests(unittest.TestCase):
    def test_repository_version_and_documentation_are_consistent(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "check_versions.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode, 0,
            msg=(result.stdout + "\\n" + result.stderr).strip(),
        )
        self.assertIn("VERSION, service worker and current docs agree", result.stdout)


if __name__ == "__main__":
    unittest.main()
