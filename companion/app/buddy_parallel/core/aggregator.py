from __future__ import annotations

from dataclasses import dataclass
from time import time

from buddy_parallel.core.session_registry import SessionSnapshot


@dataclass
class PendingPrompt:
    id: str
    tool: str
    hint: str
    session_id: str = "default"


@dataclass
class TransientEntry:
    message: str
    entries: list[str]
    expires_at: float


class StateAggregator:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionSnapshot] = {}
        self.pending_prompt: PendingPrompt | None = None
        self.transient_entries: list[TransientEntry] = []
        self.tokens = 0
        self.tokens_today = 0
        self.last_completed_at = 0.0

    def apply_event(self, payload: dict) -> None:
        session_id = payload.get("session_id") or "default"
        state = payload.get("state") or "idle"
        session = self.sessions.get(session_id) or SessionSnapshot(session_id=session_id)
        session.state = state
        session.message = payload.get("message") or payload.get("msg") or session.message or f"{session_id}: {state}"
        session.running = bool(payload.get("running", state in {"thinking", "working", "busy"}))
        session.waiting = bool(payload.get("waiting", state == "attention"))
        session.updated_at = time()
        entries = payload.get("entries")
        if isinstance(entries, list):
            session.entries = [str(item) for item in entries[:8]]
        self.sessions[session_id] = session

        if isinstance(payload.get("tokens"), int):
            self.tokens = payload["tokens"]
        if isinstance(payload.get("tokens_today"), int):
            self.tokens_today = payload["tokens_today"]
        if payload.get("completed"):
            self.last_completed_at = time()

        prompt = payload.get("prompt")
        if isinstance(prompt, dict) and isinstance(prompt.get("id"), str):
            self.pending_prompt = PendingPrompt(
                id=prompt["id"],
                tool=str(prompt.get("tool") or "Unknown"),
                hint=str(prompt.get("hint") or ""),
                session_id=session_id,
            )
        elif payload.get("clear_prompt"):
            self.pending_prompt = None

    def post_transient(self, message: str, entries: list[str] | None = None, ttl_seconds: float = 45.0) -> None:
        expires_at = time() + max(1.0, ttl_seconds)
        line_items = [str(item) for item in (entries or [])[:8]]
        self.transient_entries.append(TransientEntry(message=message, entries=line_items, expires_at=expires_at))
        self._prune_transients()

    def build_heartbeat(self) -> dict:
        self._prune_transients()
        sessions = sorted(self.sessions.values(), key=lambda item: item.updated_at, reverse=True)
        running = sum(1 for session in sessions if session.running)
        waiting = 1 if self.pending_prompt else sum(1 for session in sessions if session.waiting)
        entries: list[str] = []
        if self.pending_prompt:
            entries.append(f"approve: {self.pending_prompt.tool}")
        for transient in self.transient_entries:
            if transient.message and transient.message not in entries:
                entries.append(transient.message)
            for line in transient.entries:
                if line not in entries:
                    entries.append(line)
            if len(entries) >= 8:
                break
        for session in sessions:
            if session.message and session.message not in entries:
                entries.append(session.message)
            for line in session.entries:
                if line not in entries:
                    entries.append(line)
            if len(entries) >= 8:
                break
        heartbeat = {
            "total": len(sessions),
            "running": running,
            "waiting": waiting,
            "msg": entries[0] if entries else "No Claude connected",
            "entries": entries[:8],
            "tokens": self.tokens,
            "tokens_today": self.tokens_today,
            "completed": (time() - self.last_completed_at) < 4,
        }
        if self.pending_prompt:
            heartbeat["prompt"] = {
                "id": self.pending_prompt.id,
                "tool": self.pending_prompt.tool,
                "hint": self.pending_prompt.hint,
            }
        return heartbeat

    def _prune_transients(self) -> None:
        now = time()
        self.transient_entries = [entry for entry in self.transient_entries if entry.expires_at > now]
