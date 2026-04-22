from __future__ import annotations

import json
import sys
from urllib import request


def read_stdin_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: hook_cli.py <url> <event>")

    url = sys.argv[1]
    event = sys.argv[2]
    payload = read_stdin_payload()
    payload["event"] = event
    payload.setdefault("source", "hook")
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=0.5):
            pass
    except Exception:
        pass


if __name__ == "__main__":
    main()
