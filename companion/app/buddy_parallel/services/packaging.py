from __future__ import annotations

from textwrap import dedent

from buddy_parallel import __version__
from buddy_parallel.runtime.config import APP_DIR, CONFIG_PATH, LOG_PATH, RUNTIME_PATH
from buddy_parallel.services.launching import is_frozen


def build_notes() -> str:
    mode = "frozen bundle" if is_frozen() else "source checkout"
    return dedent(
        f"""
        BuddyParallel packaging notes
        ============================

        Version: {__version__}
        Current runtime mode: {mode}

        Core entrypoints
        ---------------
        - `buddy-parallel` -> tray companion
        - `buddy-parallel headless` -> background runtime without tray
        - `buddy-parallel settings` -> standalone settings window
        - `buddy-parallel dashboard` -> standalone dashboard window
        - `buddy-parallel feishu-helper --api-port <port>` -> hidden Feishu bridge helper

        Local runtime files
        -------------------
        - app dir: {APP_DIR}
        - config: {CONFIG_PATH}
        - state/runtime logs: {LOG_PATH}
        - runtime snapshot: {RUNTIME_PATH}

        Packaging expectations
        ----------------------
        - ship a single Windows-facing BuddyParallel app entrypoint
        - bundle Python dependencies so users do not need pip or Anaconda
        - preserve the companion app dir contract under `%APPDATA%\\BuddyParallel`
        - keep tray, settings, dashboard, and helper launches on the same executable family
        - include optional tray extras plus any enabled notice bridge dependencies

        Release checklist
        -----------------
        - verify tray launch, dashboard launch, and settings launch from the packaged build
        - verify startup shortcut creation points to the packaged app, not a repo script
        - verify serial transport on the primary USB board path
        - verify the chosen notice transport end-to-end on a clean machine
        - verify logs do not expose secrets and config migration still works
        """
    ).strip()
