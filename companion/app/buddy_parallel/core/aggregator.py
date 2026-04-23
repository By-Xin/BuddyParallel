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
    notice_id: str = ""
    notice_from: str = ""
    notice_body: str = ""
    notice_stamp: str = ""


class StateAggregator:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionSnapshot] = {}
        self.pending_prompt: PendingPrompt | None = None
        self.transient_entries: list[TransientEntry] = []
        self.weather: dict | None = None
        self.tokens = 0
        self.tokens_today = 0
        self.last_completed_at = 0.0

    def apply_event(self, payload: dict) -> None:
        session_id = payload.get("session_id") or "default"
        if payload.get("clear_session"):
            self.sessions.pop(session_id, None)
            if self.pending_prompt and self.pending_prompt.session_id == session_id:
                self.pending_prompt = None
            return
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

    def post_transient(
        self,
        message: str,
        entries: list[str] | None = None,
        ttl_seconds: float = 45.0,
        notice_id: str = "",
        notice_from: str = "",
        notice_body: str = "",
        notice_stamp: str = "",
    ) -> None:
        expires_at = time() + max(1.0, ttl_seconds)
        line_items = [str(item) for item in (entries or [])[:8]]
        self.transient_entries.append(
            TransientEntry(
                message=message,
                entries=line_items,
                expires_at=expires_at,
                notice_id=str(notice_id or "")[:40],
                notice_from=str(notice_from or "")[:16],
                notice_body=str(notice_body or "")[:160],
                notice_stamp=str(notice_stamp or "")[:24],
            )
        )
        self._prune_transients()

    def dismiss_notice(self, notice_id: str) -> bool:
        self._prune_transients()
        if notice_id:
            kept: list[TransientEntry] = []
            removed = False
            for entry in self.transient_entries:
                if not removed and entry.notice_id == notice_id:
                    removed = True
                    continue
                kept.append(entry)
            self.transient_entries = kept
            return removed

        for index, entry in enumerate(self.transient_entries):
            if entry.notice_body or entry.notice_from or entry.notice_stamp:
                del self.transient_entries[index]
                return True
        return False

    def set_weather(self, payload: dict | None) -> None:
        if not payload:
            self.weather = None
            return
        self.weather = {
            "location": str(payload.get("location") or "")[:40],
            "summary": str(payload.get("summary") or "")[:64],
            "board_summary": str(payload.get("board_summary") or "")[:23],
            "condition": str(payload.get("condition") or "")[:12],
            "weather_code": int(payload.get("weather_code") or 0),
            "current_temp_c": int(payload.get("current_temp_c") or 0),
            "high_c": int(payload.get("high_c") or 0),
            "low_c": int(payload.get("low_c") or 0),
            "precip_probability_pct": int(payload.get("precip_probability_pct") or 0),
            "updated_at": float(payload.get("updated_at") or 0.0),
        }

    def build_heartbeat(self) -> dict:
        self._prune_transients()
        sessions = sorted(self.sessions.values(), key=lambda item: item.updated_at, reverse=True)
        running = sum(1 for session in sessions if session.running)
        waiting = 1 if self.pending_prompt else sum(1 for session in sessions if session.waiting)
        entries: list[str] = []
        if self.pending_prompt:
            entries.append(f"approve: {self.pending_prompt.tool}")
        prominent_notice: TransientEntry | None = None
        notice_total = 0
        for transient in self.transient_entries:
            if transient.notice_body or transient.notice_from or transient.notice_stamp:
                notice_total += 1
                if prominent_notice is None:
                    prominent_notice = transient
            if len(entries) < 8 and transient.message and transient.message not in entries:
                entries.append(transient.message)
            for line in transient.entries:
                if len(entries) >= 8:
                    break
                if line not in entries:
                    entries.append(line)
        for session in sessions:
            if len(entries) >= 8:
                break
            if session.message and session.message not in entries:
                entries.append(session.message)
            for line in session.entries:
                if len(entries) >= 8:
                    break
                if line not in entries:
                    entries.append(line)
        heartbeat = {
            "total": len(sessions),
            "running": running,
            "waiting": waiting,
            "msg": entries[0] if entries else "No Claude connected",
            "entries": entries[:8],
            "tokens": self.tokens,
            "tokens_today": self.tokens_today,
            "completed": (time() - self.last_completed_at) < 4,
            "prompt": None,
            "notice": None,
            "weather": None,
        }
        if self.pending_prompt:
            heartbeat["prompt"] = {
                "id": self.pending_prompt.id,
                "tool": self.pending_prompt.tool,
                "hint": self.pending_prompt.hint,
            }
        if prominent_notice is not None:
            heartbeat["notice"] = {
                "id": prominent_notice.notice_id,
                "from": prominent_notice.notice_from,
                "body": prominent_notice.notice_body,
                "stamp": prominent_notice.notice_stamp,
                "index": 1,
                "total": notice_total,
            }
        if self.weather is not None and self.weather.get("board_summary"):
            heartbeat["weather"] = self.weather
        return heartbeat

    def _prune_transients(self) -> None:
        now = time()
        self.transient_entries = [
            entry
            for entry in self.transient_entries
            if (entry.notice_body or entry.notice_from or entry.notice_stamp) or entry.expires_at > now
        ]
