# Status

## Current phase

- `M5 - End-to-end loop` is effectively operating on the primary USB path.
- `M7 - VS Code approval bridge` now has a real MVP slice in the repo.
- `M6 - Packaging and release hygiene` is the main remaining milestone before broader handoff or distribution.

## Completed

- imported the upstream-derived device firmware and kept the firmware heartbeat as the device-side truth
- built the Python companion shell with config, runtime state, logging, tray UI, settings UI, startup integration, and update checks
- implemented local ingest for Claude hooks, loopback API events, and host-side permission handling
- completed the core aggregation loop that turns sessions, approvals, weather, notices, and device telemetry into firmware heartbeats
- stabilized the primary serial transport with persistent sessions, live device status capture, hardware controls, and approval round-trips on the attached board
- expanded desktop surfaces beyond placeholders with grouped tray menus, a live dashboard window, and richer settings sections
- added seasonal themes and richer firmware rendering for special-day idle states
- added multiple notice-source paths: Telegram baseline, Feishu long-connection bridge, and an experimental MQTT/WSS bridge with shared notice normalization
- built the first VS Code bridge slice for board approvals plus Codex, workspace, terminal, and diagnostics mirroring
- expanded regression coverage across config, runtime, aggregator, tray, dashboard, and notice behavior

## In progress

- package the companion into a clean Windows distribution that does not depend on a live developer environment
- tighten release hygiene, local artifact cleanup, and user-facing documentation
- decide which non-Telegram notice transport should be treated as the default long-term path
- finish the BLE story from scaffolded support to a reliable secondary transport

## Recent progress

- added a real dashboard window for live runtime, hardware, and service status
- added festive idle themes for birthday, Christmas, and New Year rendering
- added notice-source switching in settings and tray state, with Telegram, Feishu, and MQTT-aware status summaries
- brought the Feishu bot bridge online through a tray-managed helper and normalized its message handling toward Telegram parity
- prototyped MQTT/WSS notice delivery, browser-assisted fallback behavior, and local diagnostics for hostile Windows network environments
- expanded the VS Code extension from approval-only behavior into ambient activity mirroring and workspace monitoring
- tightened notice dismissal and queue behavior so device acknowledgements and host-side notice rotation stay aligned

## Latest smoke-test results

- the primary tray companion and Feishu helper are both able to run together as the expected two-process shape
- recent real-device Feishu notices were delivered end-to-end and acknowledged by the board without getting stuck in the runtime queue
- serial runtime snapshots continue to report the attached board on the primary USB path
- the repo now contains targeted tests for config validation, dashboard modeling, tray menu grouping, runtime notice behavior, and aggregator theme logic

## Known decisions

- Python-first companion remains the source of truth on the host
- official firmware remains the device-side truth and heartbeat renderer
- USB remains the primary working transport; BLE stays secondary until it is proven reliable
- docs and local handoff surfaces must stay in sync with the actual codebase

## Recommended next steps

- package the companion into a user-ready Windows app with an isolated runtime
- clean up stale status/reporting edges, especially around retired MQTT attempts on machines that now use Feishu
- keep the Feishu path stable while deciding whether MQTT stays experimental or earns another round later
- continue BLE validation only after packaging and release hygiene stop being the bigger risk
