from __future__ import annotations

import unittest
from pathlib import Path


class PackageReleaseZipScriptTests(unittest.TestCase):
    def test_release_zip_script_uses_packaged_app_and_versioned_name(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "package_release_zip.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("BuddyParallel.exe", script)
        self.assertIn("BuddyParallel-v$Version-$Platform.zip", script)
        self.assertIn("boot_app0.bin", script)
        self.assertIn("package_vsix.ps1", script)
        self.assertIn("vscode-extension", script)
        self.assertIn("Compress-Archive", script)


if __name__ == "__main__":
    unittest.main()
