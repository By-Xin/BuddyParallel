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

- prepare initial commit for the bootstrap state
- flesh out the companion shell from the current scaffolding

## Known decisions

- Python-first companion
- USB + BLE support, but one active writer at a time
- official firmware kept as device-side truth
- docs + GitHub issues/milestones are required handoff surfaces

## Known open questions

- final Windows BLE library choice for the companion
- whether first BLE transport milestone will be fully functional or scaffolded behind an interface
