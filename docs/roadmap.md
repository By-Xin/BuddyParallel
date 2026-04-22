# Roadmap

## M0 — Bootstrap

- initialize empty BuddyParallel repo
- import upstream firmware into `firmware/`
- create Python companion package skeleton
- create durable docs and GitHub tracking issues

## M1 — Companion shell

- config persistence
- runtime state persistence
- logging
- tray shell
- settings window
- startup integration
- update checker skeleton

## M2 — Event ingest

- local hook relay CLI
- loopback HTTP server
- PermissionRequest endpoint
- API ingest endpoint for API workflows
- canonical event schema

## M3 — Aggregation and permissions

- session registry
- heartbeat builder
- pending permission lifecycle
- device-to-host approval resolution

## M4 — Device transports

- serial transport
- BLE transport
- active transport arbitration
- reconnect and failover behavior

## M5 — End-to-end loop

- hook events update device state
- API events update device state
- device approve/deny resolves host permissions
- status reporting visible in tray and logs

## M6 — Packaging and release hygiene

- Windows entrypoints
- packaging skeleton
- release/update docs
- keep docs and GitHub tracking in sync
