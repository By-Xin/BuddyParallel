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
- connect tray/headless startup to the shared runtime loop
- replace placeholder hook installation with a working settings.json updater

## Recent progress

- created and pushed the bootstrap baseline commit
- added a first runnable companion runtime skeleton
- added event normalization for hook/API events
- added runtime.json output for local service discovery
- expanded serial transport into a reusable handshake/status/heartbeat helper
- added a CLI entrypoint with `run`, `headless`, `status`, and `hooks` modes
- replaced the hook installer placeholder with a working `~/.claude/settings.json` updater
- smoke-tested the companion CLI and hook installation path locally

## Latest smoke-test results

- `python -m compileall companion/app` passed
- `python -m buddy_parallel.cli status` returned a valid snapshot
- `python -m buddy_parallel.cli hooks` successfully installed BuddyParallel hooks into `~/.claude/settings.json`
- serial discovery currently sees `COM3` as the likely attached buddy device

## Known decisions

- Python-first companion
- USB + BLE support, but one active writer at a time
- official firmware kept as device-side truth
- docs + GitHub issues/milestones are required handoff surfaces

## Known open questions

- final Windows BLE library choice for the companion
- whether first BLE transport milestone will be fully functional or scaffolded behind an interface
