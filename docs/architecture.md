# Architecture

## Goal

BuddyParallel uses the official buddy firmware as the device-side renderer and introduces a Python-first companion as the single source of truth for host-side state.

## Core principles

1. The firmware remains the UI/state-machine truth for the device.
2. The companion is the only writer of live device state.
3. USB and BLE are both supported transports, but only one is active at a time.
4. Claude hooks and API workflows both feed a shared canonical event model.
5. Project state must be durable in repo docs and GitHub issues/milestones.

## Layers

### Firmware

Imported from the official upstream project under `firmware/`.

Important source-of-truth files:
- `firmware/src/main.cpp`
- `firmware/src/data.h`
- `firmware/src/xfer.h`
- `firmware/src/ble_bridge.cpp`
- `firmware/REFERENCE.md`

### Companion ingest

The companion ingests events from:
- Claude Code command hooks
- Claude Code PermissionRequest HTTP hooks
- a local API endpoint for API-driven clients

### Companion core

The core maintains canonical state:
- sessions
- running / waiting counts
- recent entries
- tokens / tokens_today
- pending permissions
- selected transport

It emits the official heartbeat-compatible JSON expected by the firmware.

### Transports

Transport implementations include:
- serial
- BLE NUS
- mock

The device manager chooses one active transport at a time.

## Ownership model

BuddyParallel assumes the companion owns the device transport. Claude Desktop’s built-in buddy bridge is not treated as a co-writer.

## Reference influences

- Official firmware repo: device behavior and protocol
- HappyBuddy-clean: host-side aggregator, permission bridge, tray/settings/update ideas

HappyBuddy-clean is reference material only, not a source of truth.
