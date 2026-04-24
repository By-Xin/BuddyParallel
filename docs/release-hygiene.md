# Release Hygiene

## Goal

Turn the current developer-friendly BuddyParallel checkout into a Windows build that users can install and run without Python, pip, Anaconda, or extra helper pages.

## Current shape

- the tray companion is the primary host-side entrypoint
- settings and dashboard can already run as separate windows
- Feishu helper runs as a secondary internal process when that notice source is enabled
- runtime state lives under `%APPDATA%\BuddyParallel`

## Packaging constraints

- ship one BuddyParallel app family, even if helper processes still exist internally
- keep tray, settings, dashboard, and helper launches on unified commands
- preserve `%APPDATA%\BuddyParallel` as the durable config and log location
- ensure only one runtime-owning BuddyParallel instance is active at a time
- make startup integration point to the packaged app, not a repo checkout
- avoid requiring users to install Python dependencies manually

## Current build skeleton

- PyInstaller spec: `companion/packaging/buddy_parallel.spec`
- build venv bootstrap: `companion/scripts/prepare_build_env.ps1`
- build script: `companion/scripts/build_windows.ps1` (fails if firmware artifacts are missing unless `-SkipFirmwareCheck` is used)
- release zip script: `companion/scripts/package_release_zip.ps1`
- first-run board setup: `buddy-parallel setup`
- command-line board flasher: `buddy-parallel flash-board --port COMx`
- shared launch helper: `companion/app/buddy_parallel/services/launching.py`
- packaging notes: `buddy-parallel packaging-notes`
- current slimming strategy: explicitly exclude unrelated scientific, notebook, Qt, and test toolchains from the frozen build
- firmware bundle: PyInstaller includes `bootloader.bin`, `partitions.bin`, `boot_app0.bin`, and `firmware.bin` when the local PlatformIO build outputs exist

## Preferred build flow

1. build or refresh firmware artifacts under `firmware/.pio/build/m5stickc-plus`
2. `powershell -ExecutionPolicy Bypass -File companion/scripts/prepare_build_env.ps1`
3. `powershell -ExecutionPolicy Bypass -File companion/scripts/build_windows.ps1 -Clean`
4. inspect `dist/BuddyParallel/BuddyParallel.exe`
5. `powershell -ExecutionPolicy Bypass -File companion/scripts/smoke_packaged_windows.ps1`
6. run `BuddyParallel.exe setup` on a clean Windows machine and verify bundled firmware is found
7. smoke-test core device behavior from the packaged build
8. `powershell -ExecutionPolicy Bypass -File companion/scripts/package_release_zip.ps1 -Version 0.1.0-alpha.1`

## Immediate checklist

- verify first-run setup opens before the tray runtime starts on a clean config
- verify setup refuses to flash without an explicit confirmation
- verify setup saves the selected COM port under `%APPDATA%\BuddyParallel`
- verify a second BuddyParallel launch exits instead of competing for COM or notice bridge resources
- verify packaged tray launch
- verify standalone settings and dashboard launch from the packaged build
- verify startup shortcut creation
- verify USB serial operation on the main board path after flashing
- verify the chosen notice transport end-to-end on a clean Windows machine
- use `BUDDY_PARALLEL_APP_DIR` for packaged smoke tests that must not touch the user's real config
- verify logs and config exports do not leak secrets
