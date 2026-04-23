from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from buddy_parallel.services.startup import StartupManager


class StartupManagerTests(unittest.TestCase):
    def test_apply_creates_and_removes_startup_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            startup_dir = Path(temp_dir) / "Startup"
            manager = StartupManager(startup_dir=startup_dir)
            target = Path(temp_dir) / "run_companion.py"
            target.write_text("print('buddy')\n", encoding="utf-8")

            manager.apply(True, target, ["run"], Path(temp_dir))

            self.assertTrue(manager.entry_path.exists())
            script = manager.entry_path.read_text(encoding="utf-8")
            self.assertIn("CreateObject", script)
            self.assertIn("run_companion.py run", script)
            self.assertIn(str(Path(temp_dir)), script)

            manager.apply(False, target, ["run"], Path(temp_dir))

            self.assertFalse(manager.entry_path.exists())


if __name__ == "__main__":
    unittest.main()
