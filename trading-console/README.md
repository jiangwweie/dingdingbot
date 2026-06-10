# Trading Console Frontend

Owner-facing React frontend for the Trading Console Gate 2 handoff.

## Runtime Contract

- Truth source: `GET /api/trading-console/*`, plus the explicit
  non-executing strategy shadow-plan POST listed below.
- Forbidden truth sources: `/api/brc/*`, `/api/runtime/*`, `/api/dev/testnet/brc/*`
- The frontend proxy forwards `GET /api/trading-console/*` to the configured backend.
- The frontend proxy also forwards only
  `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/strategy-signal-shadow-plans`.
  This endpoint may create shadow SignalEvaluation / OrderCandidate planning
  records only; it is not execution authority.
- Other non-GET requests to the proxy are rejected with `405`.
- Action slots are displayed as disabled future/deferred states only.

## Local Run

1. Install dependencies:

   ```bash
   npm install
   ```

2. Start the local backend read-model server.

3. Configure the frontend proxy target:

   ```bash
   export TRADING_CONSOLE_API_BASE="http://127.0.0.1:8000"
   ```

4. Run the frontend:

   ```bash
   npm run dev
   ```

The frontend is served at `http://localhost:3000` by default.
