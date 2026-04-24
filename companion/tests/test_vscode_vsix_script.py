from __future__ import annotations

import unittest
from pathlib import Path


class VsCodeVsixScriptTests(unittest.TestCase):
    def test_vsix_script_packages_extension_manifest_and_runtime_files(self) -> None:
        script = (Path(__file__).resolve().parents[2] / "vscode-extension" / "scripts" / "package_vsix.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("extension.vsixmanifest", script)
        self.assertIn("[Content_Types].xml", script)
        self.assertIn("extension.js", script)
        self.assertIn("BuddyParallel-vscode-$version.vsix", script)


if __name__ == "__main__":
    unittest.main()
