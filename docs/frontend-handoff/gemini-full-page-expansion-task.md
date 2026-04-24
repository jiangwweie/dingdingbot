# Gemini Frontend Expansion Task

## Goal

Expand the existing frontend scaffold into a fuller read-only console with all pages
that will be needed in the near-term product flow.

This is still a **mock-data-first** implementation.

Do not connect to any real backend yet.

## Current Base

There is already an existing scaffold project:

- `gemimi-web-front/`

Gemini should **continue from that scaffold** instead of regenerating a totally
different project from scratch.

## Product Direction

The console has two main domains:

1. `Runtime`
2. `Research`

The UI is intended for:

- Sim-1 observation
- research candidate review
- replay context inspection
- later backtest comparison

## Constraints

- Read-only only
- Manual refresh only
- No config editing
- No runtime hot reload
- No websocket
- No review write-back
- No candidate promote action
- No public-internet assumptions
- No real backend calls

## Pages To Fully Build Now

### Runtime

1. `Runtime / Overview`
2. `Runtime / Signals`
3. `Runtime / Execution`
4. `Runtime / Health`

### Research

5. `Research / Candidates`
6. `Research / Candidate Detail`
7. `Research / Replay`
8. `Research / Backtests`
9. `Research / Compare`

## Important Clarifications

### Replay

Replay means **Replay Context / Reproduce Context**.

It is not a candlestick playback page in the current version.

### Health

`breaker_summary` and `recovery_summary` must remain semantically separate.

### Overview

`freshness_status` must remain highly visible because the UI uses manual refresh.

## What Gemini Should Improve

1. Keep the current project structure if it is workable.
2. Expand all planned pages.
3. Make mock data more realistic and closer to the project planning docs.
4. Improve page-level information density and consistency.
5. Add stronger empty / loading / error states.
6. Improve navigation consistency between Runtime and Research.
7. Add richer page sections for candidate review and backtest comparison.

## What Gemini Should Not Do

1. Do not invent editing workflows.
2. Do not add auth pages.
3. Do not add websocket/live subscription logic.
4. Do not add real API integrations.
5. Do not rebuild the project into a different stack.
6. Do not turn this into a landing page or marketing site.

## Required Deliverables

Gemini should update the existing frontend project and produce:

1. completed pages for all items above
2. improved mock service layer
3. richer fixture data
4. refined shared components
5. consistent page states
6. README explaining:
   - how to run
   - where mock data lives
   - how later real API replacement should work

## Acceptance Standard

The resulting frontend should feel like:

- a usable internal console
- information-dense but readable
- consistent with a trading / monitoring tool
- ready for humans to edit and wire to real APIs later
