from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from buddy_parallel.core.aggregator import PendingPrompt, StateAggregator


@dataclass
class PendingPermission:
    request_id: str
    session_id: str
    tool_name: str
    hint: str
    handler: Any


class PermissionBridge:
    def __init__(self, aggregator: StateAggregator):
        self.aggregator = aggregator
        self.pending: dict[str, PendingPermission] = {}

    def register(self, handler: Any, payload: dict) -> str:
        request_id = str(payload.get("request_id") or f"req_{len(self.pending) + 1}")
        session_id = str(payload.get("session_id") or "default")
        tool_name = str(payload.get("tool_name") or "Unknown")
        hint = self._build_hint(payload.get("tool_input"))
        self.pending[request_id] = PendingPermission(request_id, session_id, tool_name, hint, handler)
        self.aggregator.pending_prompt = PendingPrompt(id=request_id, tool=tool_name, hint=hint, session_id=session_id)
        return request_id

    def resolve_from_device(self, request_id: str, decision: str) -> bool:
        entry = self.pending.pop(request_id, None)
        if entry is None:
            return False
        self.aggregator.pending_prompt = None
        body = json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "deny" if decision == "deny" else "allow"}}}).encode("utf-8")
        entry.handler.send_response(200)
        entry.handler.send_header("Content-Type", "application/json")
        entry.handler.send_header("Content-Length", str(len(body)))
        entry.handler.end_headers()
        entry.handler.wfile.write(body)
        return True

    def clear_for_session(self, session_id: str) -> None:
        doomed = [key for key, value in self.pending.items() if value.session_id == session_id]
        for key in doomed:
            self.pending.pop(key, None)
        if self.aggregator.pending_prompt and self.aggregator.pending_prompt.session_id == session_id:
            self.aggregator.pending_prompt = None

    @staticmethod
    def _build_hint(tool_input: Any) -> str:
        if isinstance(tool_input, dict):
            if isinstance(tool_input.get("command"), str):
                return tool_input["command"][:64]
            if isinstance(tool_input.get("file_path"), str):
                return tool_input["file_path"][:64]
        return ""
