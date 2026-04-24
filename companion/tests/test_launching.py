from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from buddy_parallel.services.launching import build_companion_command, is_frozen


class LaunchingTests(unittest.TestCase):
    def test_build_companion_command_uses_repo_script_in_source_mode(self) -> None:
        self.assertFalse(is_frozen())
        launch = build_companion_command("dashboard", windowed=False)
        self.assertGreaterEqual(len(launch.command), 3)
        self.assertTrue(launch.command[1].endswith("companion\\scripts\\run_companion.py"))
        self.assertEqual(launch.command[2], "dashboard")
        self.assertTrue(Path(launch.working_dir).name == "BuddyParallel")

    def test_build_companion_command_uses_executable_in_frozen_mode(self) -> None:
        executable = "C:/BuddyParallel/BuddyParallel.exe"
        with patch("sys.frozen", True, create=True), patch("sys.executable", executable):
            launch = build_companion_command("run", windowed=True)

        self.assertEqual(Path(launch.command[0]), Path(executable))
        self.assertEqual(launch.command[1], "run")
        self.assertEqual(str(launch.working_dir).replace("\\", "/"), "C:/BuddyParallel")


if __name__ == "__main__":
    unittest.main()
