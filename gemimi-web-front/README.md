# BRC Operator Console

Local Owner console for the Bounded Risk Campaign workflow.

The console is an operation-governance surface, not a trading panel. It should
answer:

- where the Owner is now;
- what can be done;
- why an action is available or blocked;
- what the next confirmation step is;
- whether the action can affect a real account.

## Local Testnet Acceptance

From the repository root:

```bash
scripts/start_brc_local_testnet.sh
```

The launcher uses local-only BRC testnet defaults:

- `EXCHANGE_TESTNET=true`
- `RUNTIME_PROFILE=brc_btc_eth_testnet_runtime`
- `RUNTIME_CONTROL_API_ENABLED=true`
- `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`

Then open:

```text
http://127.0.0.1:3000/guide
```

## Frontend Only

```bash
npm install
npm run dev
npm run build
npm run lint
```

By default the Vite dev server proxies same-origin `/api/*` requests to
`http://127.0.0.1:8000`, so the login cookie stays on the frontend origin.
Set `VITE_API_PROXY_TARGET` if the backend is on another local port.

## Boundaries

The local console must not expose real-live/mainnet, withdrawal/transfer,
automatic strategy execution, automatic sizing, or strategy-pool execution.
Controlled testnet rehearsal still goes through the fixed BRC workflow and
Owner confirmation.
