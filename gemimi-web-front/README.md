# Trading Console (Read-only)

This is a read-only trading console for Sim-1 observation and research review.

## Constraints & Behaviors incorporated:
- **Read-only interface**: No config editing or data write-backs, strictly observation.
- **Mock Data Layer**: Built to run entirely on simulated fixtures. It avoids connecting to a backend server.
- **No Websockets**: Designed with manual observation in mind. Note the "Manual Refresh" utility globally available in the app shell.
- **Freshness Evaluation**: The system heartbeat status rotates on every manual refresh (Fresh -> Stale -> Possibly Dead) for demonstration purposes. 
- **Separation of Concerns**: Health page strictly isolates Breaker Summary and Recovery Summary instead of muddling metrics.
- **Restrained Styling**: Engineered focusing on dense, legible presentation over decorative styling, matching the dark analytical aesthetic common to trading terminals.

## Setup

1. `npm install` (to fetch any required dependencies).
2. `npm run dev` (starts the local Vite server, typically on port `3000` assuming constraints).

## Structure
- `/src/pages/runtime`: Focuses on executing intent, live signals, and system health status.
- `/src/pages/research`: Focuses on evaluating generated candidates, reviewing Optuna artifacts, and observing replay context (i.e., not a historical candlestick playback).
- `/src/services/mockApi.ts`: Hosts the mock network layer. Edit here to adjust test data values.
