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

## ASCII buddies

Local gallery: [`docs/ascii-buddies.html`](docs/ascii-buddies.html)

Current firmware roster, with a quick human-style voice note for each buddy:

- `axolotl`: soft-spoken night-shift friend who quietly says, "Let's keep this gentle and figure it out one blink at a time."
- `blob`: sleepy optimist who sounds like, "I may look gooey, but I am emotionally available and surprisingly resilient."
- `cactus`: dry-humored protector who says, "I care a lot, I just come pre-equipped with boundaries."
- `capybara`: impossibly calm coworker who says, "Nothing here is worth panicking over; we can float through it."
- `cat`: mildly judgmental genius who says, "I already knew the answer, but I will allow you to discover it."
- `chonk`: big-hearted tank who says, "I believe in comfort, snacks, and shipping things that actually hold up."
- `dragon`: theatrical senior engineer who says, "Stand back, I can solve this elegantly or dramatically, possibly both."
- `duck`: cheerful chaos gremlin who says, "I have no long-term plan, but I do have momentum."
- `ghost`: polite lurker who says, "I am not haunting the project; I am just monitoring it with concern."
- `goose`: loud operations lead who says, "This is now my incident, and I will be honking until it is fixed."
- `mushroom`: cozy healer who says, "Come sit down; recovery is also part of the roadmap."
- `octopus`: multitasking coordinator who says, "I can hold eight threads at once, but I would still prefer a checklist."
- `owl`: late-night scholar who says, "The answer was always in the margins if you stayed up long enough."
- `penguin`: tidy teammate who says, "We do this with dignity, structure, and a very clean handoff."
- `rabbit`: high-energy sprinter who says, "I already started three versions, and one of them is definitely the winner."
- `robot`: precise builder who says, "Please clarify the requirement so I can be correct at industrial scale."
- `snail`: slow-and-steady craftsperson who says, "Fast is nice, but finished and well-shaped is nicer."
- `turtle`: dependable elder who says, "We are still moving, which means we are still winning."
