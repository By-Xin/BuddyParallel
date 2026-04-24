from __future__ import annotations

import unittest
from pathlib import Path


class SmokePackagedScriptTests(unittest.TestCase):
    def test_smoke_script_checks_packaged_runtime_surfaces(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "smoke_packaged_windows.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("BUDDY_PARALLEL_APP_DIR", script)
        self.assertIn("BuddyParallel.exe", script)
        self.assertIn("Second headless process stayed alive", script)
        self.assertIn("BuddyParallel is already running", script)
        self.assertIn("settings", script)
        self.assertIn("dashboard", script)


if __name__ == "__main__":
    unittest.main()
