# AI Studio Frontend Task

## Goal

Generate a runnable frontend project scaffold for a read-only trading console.

## Product Scope

This is a read-only console for Sim-1 observation and research review.

Two domains:

1. Runtime
2. Research

## Must Build

### Runtime

- Overview
- Signals
- Execution
- Health

### Research

- Candidates
- Candidate Detail
- Replay

## Constraints

- Read-only only
- Manual refresh only
- No config editing
- No runtime hot reload
- No websocket
- No candidate review write-back
- Replay is Replay Context, not kline playback
- Local / intranet only
- Use mock data only
- Do not call any real backend

## Tech Stack

- React
- TypeScript
- TailwindCSS

## UI Direction

- Dashboard / console style
- Dense, scannable, operational
- No landing page
- No marketing sections
- First screen should be the real console UI
- Clear status colors and badges
- Loading / empty / error states required

## Required Deliverables

- App shell
- Router
- Layout
- Navigation
- Page components
- Shared UI components
- Mock API layer
- Mock fixture data
- TypeScript type definitions
- README for local run and mock usage

## Important Notes

### Runtime / Overview must include

- profile
- version
- hash
- frozen
- symbol
- timeframe
- mode
- exchange / pg / webhook health
- breaker count
- reconciliation summary
- backend summary
- server_time
- last_runtime_update_at
- last_heartbeat_at
- freshness_status

### Runtime / Health must separate

- breaker_summary
- recovery_summary

Do not merge them into one number.

### Research / Replay

First version is Replay Context only.

It should show:

- reproduce_cmd
- metadata
- resolved_request
- runtime_overrides

It should **not** become a candlestick playback tool in the first version.
