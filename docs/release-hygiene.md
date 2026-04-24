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
- make startup integration point to the packaged app, not a repo checkout
- avoid requiring users to install Python dependencies manually

## Current build skeleton

- PyInstaller spec: `companion/packaging/buddy_parallel.spec`
- build script: `companion/scripts/build_windows.ps1`
- shared launch helper: `companion/app/buddy_parallel/services/launching.py`
- packaging notes: `buddy-parallel packaging-notes`
- current slimming strategy: explicitly exclude unrelated scientific, notebook, Qt, and test toolchains from the frozen build

## Immediate checklist

- verify packaged tray launch
- verify standalone settings and dashboard launch from the packaged build
- verify startup shortcut creation
- verify USB serial operation on the main board path
- verify the chosen notice transport end-to-end on a clean Windows machine
- verify logs and config exports do not leak secrets
