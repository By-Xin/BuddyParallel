from __future__ import annotations

import unittest
from unittest.mock import patch

from buddy_parallel.ingest.install_hooks import cleanup_hooks, ensure_event_hooks, ensure_permission_hook


class InstallHooksTests(unittest.TestCase):
    def test_cleanup_removes_legacy_entries_and_dedupes_buddyparallel(self) -> None:
        settings = {
            "hooks": {
                "PreToolUse": [
                    {"hooks": [{"type": "command", "command": "node Downloads/HappyBuddy cc-hook.js"}]},
                    {"hooks": [{"type": "command", "command": 'python hook_cli.py # BuddyParallel hook_cli.py'}]},
                    {"hooks": [{"type": "command", "command": 'python hook_cli.py # BuddyParallel hook_cli.py'}]},
                ],
                "PermissionRequest": [
                    {"hooks": [{"type": "http", "url": "http://127.0.0.1:23333/permission"}]},
                    {"hooks": [{"type": "http", "url": "http://127.0.0.1:43111/permission"}]},
                    {"hooks": [{"type": "http", "url": "http://127.0.0.1:43111/permission"}]},
                ],
            }
        }

        with patch("buddy_parallel.ingest.install_hooks.build_permission_url", return_value="http://127.0.0.1:43111/permission"):
            cleanup_hooks(settings)

        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 1)
        self.assertEqual(len(settings["hooks"]["PermissionRequest"]), 1)

    def test_ensure_helpers_append_missing_entries_once(self) -> None:
        settings = {"hooks": {}}

        ensure_event_hooks(settings, "python hook_cli.py {event} # BuddyParallel hook_cli.py")
        ensure_event_hooks(settings, "python hook_cli.py {event} # BuddyParallel hook_cli.py")
        ensure_permission_hook(settings, "http://127.0.0.1:43111/permission")
        ensure_permission_hook(settings, "http://127.0.0.1:43111/permission")

        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 1)
        self.assertEqual(len(settings["hooks"]["PostToolUse"]), 1)
        self.assertEqual(len(settings["hooks"]["Notification"]), 1)
        self.assertEqual(len(settings["hooks"]["Stop"]), 1)
        self.assertEqual(len(settings["hooks"]["SubagentStop"]), 1)
        self.assertEqual(len(settings["hooks"]["PermissionRequest"]), 1)


if __name__ == "__main__":
    unittest.main()
