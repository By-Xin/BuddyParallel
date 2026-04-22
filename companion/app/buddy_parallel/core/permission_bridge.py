from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

from buddy_parallel.core.aggregator import PendingPrompt, StateAggregator


@dataclass
class PendingPermission:
    request_id: str
    session_id: str
    tool_name: str
    hint: str
    decision: str = "ask"
    resolved: threading.Event = field(default_factory=threading.Event)


class PermissionBridge:
    def __init__(self, aggregator: StateAggregator, default_timeout: float = 590.0):
        self.aggregator = aggregator
        self.default_timeout = default_timeout
        self.pending: dict[str, PendingPermission] = {}
        self._lock = threading.Lock()

    def register(self, payload: dict) -> PendingPermission:
        request_id = str(payload.get("request_id") or f"req_{len(self.pending) + 1}")
        session_id = str(payload.get("session_id") or "default")
        tool_name = str(payload.get("tool_name") or "Unknown")
        hint = self._build_hint(payload.get("tool_input"))
        entry = PendingPermission(request_id=request_id, session_id=session_id, tool_name=tool_name, hint=hint)
        with self._lock:
            self.pending[request_id] = entry
        self.aggregator.pending_prompt = PendingPrompt(id=request_id, tool=tool_name, hint=hint, session_id=session_id)
        return entry

    def wait_for_decision(self, request_id: str, timeout: float | None = None) -> str:
        with self._lock:
            entry = self.pending.get(request_id)
        if entry is None:
            return "ask"
        entry.resolved.wait(self.default_timeout if timeout is None else timeout)
        decision = self._normalize_decision(entry.decision)
        with self._lock:
            self.pending.pop(request_id, None)
        if self.aggregator.pending_prompt and self.aggregator.pending_prompt.id == request_id:
            self.aggregator.pending_prompt = None
        return decision

    def resolve_from_device(self, request_id: str, decision: str) -> bool:
        with self._lock:
            entry = self.pending.get(request_id)
        if entry is None:
            return False
        entry.decision = self._normalize_decision(decision)
        entry.resolved.set()
        if self.aggregator.pending_prompt and self.aggregator.pending_prompt.id == request_id:
            self.aggregator.pending_prompt = None
        return True

    def clear_for_session(self, session_id: str) -> None:
        with self._lock:
            doomed = [value for value in self.pending.values() if value.session_id == session_id]
        for entry in doomed:
            entry.decision = "ask"
            entry.resolved.set()
        if self.aggregator.pending_prompt and self.aggregator.pending_prompt.session_id == session_id:
            self.aggregator.pending_prompt = None

    def cancel_all(self) -> None:
        with self._lock:
            doomed = list(self.pending.values())
        for entry in doomed:
            entry.decision = "ask"
            entry.resolved.set()
        self.aggregator.pending_prompt = None

    @staticmethod
    def send_hook_response(handler: Any, decision: str) -> None:
        body = json.dumps({"hookSpecificOutput": {"permissionDecision": PermissionBridge._normalize_decision(decision)}}).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    @staticmethod
    def _normalize_decision(decision: str) -> str:
        normalized = str(decision or "ask").lower()
        if normalized in {"allow", "once", "always"}:
            return "allow"
        if normalized == "deny":
            return "deny"
        return "ask"

    @staticmethod
    def _build_hint(tool_input: Any) -> str:
        if isinstance(tool_input, dict):
            if isinstance(tool_input.get("command"), str):
                return tool_input["command"][:64]
            if isinstance(tool_input.get("file_path"), str):
                return tool_input["file_path"][:64]
        return ""
