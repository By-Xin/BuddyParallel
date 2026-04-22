from __future__ import annotations

import json
from pathlib import Path

from buddy_parallel.runtime.config import RUNTIME_PATH


def write_runtime_config(payload: dict, path: Path = RUNTIME_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_runtime_config(path: Path = RUNTIME_PATH) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
