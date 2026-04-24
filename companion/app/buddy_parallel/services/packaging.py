from __future__ import annotations

from textwrap import dedent

from buddy_parallel import __version__
from buddy_parallel.runtime.config import APP_DIR, CONFIG_PATH, LOCK_PATH, LOG_PATH, RUNTIME_PATH
from buddy_parallel.services.launching import companion_root, is_frozen, repo_root


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
        - `buddy-parallel setup` -> first-run board setup and firmware flashing window
        - `buddy-parallel flash-board --port <COMx>` -> command-line board flasher
        - `buddy-parallel feishu-helper --api-port <port>` -> hidden Feishu bridge helper

        Local runtime files
        -------------------
        - app dir: {APP_DIR}
        - config: {CONFIG_PATH}
        - state/runtime logs: {LOG_PATH}
        - runtime snapshot: {RUNTIME_PATH}
        - single-instance lock: {LOCK_PATH}

        Packaging expectations
        ----------------------
        - ship a single Windows-facing BuddyParallel app entrypoint
        - bundle Python dependencies so users do not need pip or Anaconda
        - preserve the companion app dir contract under `%APPDATA%\\BuddyParallel`
        - keep tray, settings, dashboard, and helper launches on the same executable family
        - bundle firmware flashing assets for first-run board setup
        - include optional tray extras plus any enabled notice bridge dependencies
        - use `BUDDY_PARALLEL_APP_DIR` only for isolated package smoke tests

        Release checklist
        -----------------
        - verify a second tray/headless launch exits cleanly instead of competing for COM ports
        - verify tray launch, dashboard launch, and settings launch from the packaged build
        - verify first-run setup can see the bundled firmware assets
        - verify a clean board can be flashed and then answers `status`
        - verify startup shortcut creation points to the packaged app, not a repo script
        - verify serial transport on the primary USB board path
        - verify the chosen notice transport end-to-end on a clean machine
        - verify logs do not expose secrets and config migration still works

        Build commands
        --------------
        - source diagnostics: `buddy-parallel packaging-notes`
        - prepare build venv: `powershell -ExecutionPolicy Bypass -File companion\\scripts\\prepare_build_env.ps1`
        - Windows build script: `powershell -ExecutionPolicy Bypass -File companion\\scripts\\build_windows.ps1`
        - packaged smoke script: `powershell -ExecutionPolicy Bypass -File companion\\scripts\\smoke_packaged_windows.ps1`
        - release zip script: `powershell -ExecutionPolicy Bypass -File companion\\scripts\\package_release_zip.ps1 -Version 0.1.0-alpha.1`
        - PyInstaller spec: `{companion_root() / "packaging" / "buddy_parallel.spec"}`
        - default output app: `{repo_root() / "dist" / "BuddyParallel" / "BuddyParallel.exe"}`
        """
    ).strip()
