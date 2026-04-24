from __future__ import annotations

import unittest
from pathlib import Path


class PyInstallerSpecTests(unittest.TestCase):
    def test_spec_collects_esptool_data_files_for_stub_flashers(self) -> None:
        spec = (Path(__file__).resolve().parents[1] / "packaging" / "buddy_parallel.spec").read_text(
            encoding="utf-8"
        )
        self.assertIn("collect_data_files", spec)
        self.assertIn('collect_data_files("esptool")', spec)
        self.assertIn("firmware_sources", spec)


if __name__ == "__main__":
    unittest.main()
