from __future__ import annotations

import unittest
from pathlib import Path


class PrepareBuildEnvScriptTests(unittest.TestCase):
    def test_prepare_script_creates_venv_and_installs_editable_package(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "prepare_build_env.ps1").read_text(encoding="utf-8")
        self.assertIn(".venv-build", script)
        self.assertIn("-m venv", script)
        self.assertIn("pip install --editable", script)
        self.assertIn("Invoke-CheckedExternal", script)


if __name__ == "__main__":
    unittest.main()
