from __future__ import annotations

import threading
import time
import tempfile
import unittest
from pathlib import Path

from buddy_parallel.core.companion_runtime import CompanionRuntime
from buddy_parallel.runtime.config import AppConfig
from buddy_parallel.runtime.state import StateStore


class VsCodeBridgeTests(unittest.TestCase):
    def test_vscode_permission_request_resolves_allow_from_device(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = CompanionRuntime(
                config=AppConfig(transport_mode="mock"),
                state_store=StateStore(Path(temp_dir) / "state.json"),
            )

            result: dict = {}

            def worker() -> None:
                result.update(
                    runtime.on_vscode_permission_request(
                        {
                            "session_id": "vscode-test",
                            "tool_name": "Workspace Edit",
                            "tool_input": {"file_path": "C:/tmp/demo.py"},
                            "timeout_seconds": 2,
                        }
                    )
                )

            thread = threading.Thread(target=worker)
            thread.start()

            deadline = time.time() + 1.0
            while runtime.aggregator.pending_prompt is None and time.time() < deadline:
                time.sleep(0.01)

            self.assertIsNotNone(runtime.aggregator.pending_prompt)
            request_id = runtime.aggregator.pending_prompt.id
            self.assertTrue(runtime.permission_bridge.resolve_from_device(request_id, "once"))

            thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result["decision"], "allow")
            self.assertTrue(result["allowed"])

    def test_vscode_permission_request_times_out_to_ask(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = CompanionRuntime(
                config=AppConfig(transport_mode="mock"),
                state_store=StateStore(Path(temp_dir) / "state.json"),
            )

            result = runtime.on_vscode_permission_request(
                {
                    "session_id": "vscode-test",
                    "tool_name": "Workspace Edit",
                    "tool_input": {"file_path": "C:/tmp/demo.py"},
                    "timeout_seconds": 0.05,
                }
            )

            self.assertEqual(result["decision"], "ask")
            self.assertFalse(result["allowed"])


if __name__ == "__main__":
    unittest.main()
