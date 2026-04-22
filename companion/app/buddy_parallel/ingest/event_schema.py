from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CanonicalEvent:
    source: str
    event: str
    session_id: str = "default"
    session_title: str | None = None
    cwd: str = ""
    state: str = "idle"
    message: str = ""
    running: bool = False
    waiting: bool = False
    completed: bool = False
    tokens: int | None = None
    tokens_today: int | None = None
    prompt: dict[str, Any] | None = None
    entries: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
