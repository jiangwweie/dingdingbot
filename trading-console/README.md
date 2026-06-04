# Trading Console Frontend

Read-only React frontend for the Trading Console Gate 2 handoff.

## Runtime Contract

- Truth source: `GET /api/trading-console/*`
- Forbidden truth sources: `/api/brc/*`, `/api/runtime/*`, `/api/dev/testnet/brc/*`
- The frontend proxy forwards `GET /api/trading-console/*` to the configured backend.
- Non-GET requests to the proxy are rejected with `405`.
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
