from __future__ import annotations

import unittest
from pathlib import Path


class BuildWindowsScriptTests(unittest.TestCase):
    def test_build_script_mentions_pyinstaller_and_spec(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("PyInstaller", script)
        self.assertIn("buddy_parallel.spec", script)
        self.assertIn("--distpath", script)
        self.assertIn("PythonExe", script)
        self.assertIn(".venv-build", script)
        self.assertIn("SkipFirmwareCheck", script)
        self.assertIn("boot_app0.bin", script)
        self.assertIn("Invoke-CheckedExternal", script)


if __name__ == "__main__":
    unittest.main()
