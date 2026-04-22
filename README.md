# BuddyParallel

BuddyParallel keeps the official Hardware Buddy device firmware and UI experience, but replaces the event source with a companion we control.

## Goals

- preserve the official firmware heartbeat-driven UI and approval flow
- support API-driven and hook-driven Claude workflows
- run a single Python-first companion as the source of truth
- support USB and BLE device transports without double-writing state

## Repository layout

- `firmware/` — upstream-derived device firmware and protocol reference
- `companion/` — Python companion app, ingest pipeline, transports, tray, settings, updates
- `docs/` — architecture, roadmap, and current status for handoff between agents

## Current status

This repository is in initial bootstrap. See `docs/status.md` for progress and `docs/roadmap.md` for milestones.
