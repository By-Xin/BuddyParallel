# Status

## Current phase

Bootstrap

## Completed

- created clean local checkout from `git@github.com:By-Xin/BuddyParallel.git`
- confirmed remote repository was empty
- created initial repository skeleton
- imported upstream official firmware into `firmware/`
- created durable architecture / roadmap / status docs
- created GitHub milestone `M1 - Companion Core`
- created bootstrap tracking issues:
  - #1 Epic: bootstrap BuddyParallel companion architecture
  - #2 Import upstream firmware into firmware/ and keep device behavior stable
  - #3 Build Python companion shell with config, state, logging, tray, settings, updates
  - #4 Implement event ingest for Claude hooks and API workflows
  - #5 Implement canonical state aggregation and permission bridge
  - #6 Implement device transports and active transport arbitration
- created Python companion package skeleton and first runtime modules

## In progress

- flesh out the companion shell from the current scaffolding
- validate the permission round-trip against a live board button press through the running companion
- replace placeholder tray/settings surfaces with real desktop UI

## Recent progress

- created and pushed the bootstrap baseline commit
- added a first runnable companion runtime skeleton
- added event normalization for hook/API events
- added runtime.json output for local service discovery
- expanded serial transport into a reusable handshake/status/heartbeat helper
- added a CLI entrypoint with `run`, `headless`, `status`, and `hooks` modes
- replaced the hook installer placeholder with a working `~/.claude/settings.json` updater
- made the repo-local companion launch scripts runnable without pre-installing the package
- switched the runtime from one-shot serial writes to a persistent serial session with background device reads
- validated that the runtime now captures device `status` replies into `runtime.json`
- rewired PermissionRequest handling so the HTTP hook stays pending until a device decision resolves it

## Latest smoke-test results

- `python -m compileall companion/app` passed after the permission bridge changes
- `python companion/scripts/run_companion.py status` returned a valid snapshot directly from the checkout
- `python companion/scripts/run_companion.py headless` opened a persistent session on `COM3`
- posting a local `/state` event updated the runtime heartbeat and `runtime.json`
- the runtime captured a valid `{"ack":"status",...}` device reply from the attached board on `COM3`
- in-process permission smoke tests returned `{"hookSpecificOutput":{"permissionDecision":"allow"}}` for a simulated board `once` response
- in-process permission smoke tests returned `{"hookSpecificOutput":{"permissionDecision":"deny"}}` for a simulated board `deny` response
- `python -m buddy_parallel.cli hooks` successfully installed BuddyParallel hooks into `~/.claude/settings.json`
- serial discovery currently sees `COM3` as the likely attached buddy device
- live board-button permission validation through the running companion is still pending

## Known decisions

- Python-first companion
- USB + BLE support, but one active writer at a time
- official firmware kept as device-side truth
- docs + GitHub issues/milestones are required handoff surfaces

## Known open questions

- final Windows BLE library choice for the companion
- whether first BLE transport milestone will be fully functional or scaffolded behind an interface
