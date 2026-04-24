from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from buddy_parallel.services.launching import LaunchSpec
from buddy_parallel.services.startup import StartupManager


class StartupManagerTests(unittest.TestCase):
    def test_apply_creates_and_removes_startup_script(self) -> None:
        startup_dir = Path("C:/BuddyParallelTest/Startup")
        manager = StartupManager(startup_dir=startup_dir)
        launch = LaunchSpec(
            command=["pythonw.exe", "C:/BuddyParallelTest/run_companion.py", "run"],
            working_dir=Path("C:/BuddyParallelTest"),
        )

        with patch("pathlib.Path.mkdir") as mkdir_mock, patch("pathlib.Path.write_text") as write_text_mock:
            manager.apply(True, launch)

        mkdir_mock.assert_called_once_with(parents=True, exist_ok=True)
        script = write_text_mock.call_args.args[0]
        self.assertIn("CreateObject", script)
        self.assertIn("run_companion.py run", script)
        self.assertIn("C:/BuddyParallelTest", script)

        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.unlink") as unlink_mock:
            manager.apply(False, launch)

        unlink_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
