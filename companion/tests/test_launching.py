from __future__ import annotations

import unittest
from pathlib import Path

from buddy_parallel.services.launching import build_companion_command, is_frozen


class LaunchingTests(unittest.TestCase):
    def test_build_companion_command_uses_repo_script_in_source_mode(self) -> None:
        self.assertFalse(is_frozen())
        launch = build_companion_command("dashboard", windowed=False)
        self.assertGreaterEqual(len(launch.command), 3)
        self.assertTrue(launch.command[1].endswith("companion\\scripts\\run_companion.py"))
        self.assertEqual(launch.command[2], "dashboard")
        self.assertTrue(Path(launch.working_dir).name == "BuddyParallel")


if __name__ == "__main__":
    unittest.main()
