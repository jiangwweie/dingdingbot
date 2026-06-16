# Owner Runtime Console

New frontend surface for **Owner Runtime Console v1**.

The console is an Owner automation supervisor. It is not the legacy dashboard,
not a packet browser, and not a manual trading terminal.

## Scope

P1 integrates the frozen isolated frontend into the main runtime workspace:

- dark and light theme parity;
- Owner-safe product language;
- StrategyGroup runtime status;
- funds, orders, positions, and protection health;
- read-only source-readiness backend integration;
- explicit mock scenarios for UI acceptance only;
- visual QA across desktop and mobile viewports.

Real order actions are intentionally outside this frontend integration pass.
The app defaults to:

```text
GET /api/trading-console/owner-console-source-readiness
```

Mock data is opt-in and must be enabled explicitly with `VITE_OWNER_USE_MOCK=true`.

## Local Commands

```bash
npm run build
npm run smoke
npm run smoke:states
npm run smoke:real
```

## Data Mode

```bash
VITE_OWNER_USE_MOCK=false npm run dev
OWNER_RUNTIME_API_PROXY_TARGET=http://127.0.0.1:8000 VITE_OWNER_USE_MOCK=false npm run dev
VITE_OWNER_USE_MOCK=true npm run dev
```

## Mock Scenarios

```bash
VITE_OWNER_MOCK_SCENARIO=normal npm run dev
VITE_OWNER_MOCK_SCENARIO=processing npm run dev
VITE_OWNER_MOCK_SCENARIO=paused npm run dev
VITE_OWNER_MOCK_SCENARIO=intervention npm run dev
VITE_OWNER_MOCK_SCENARIO=stale npm run dev
VITE_OWNER_MOCK_SCENARIO=empty npm run dev
VITE_OWNER_MOCK_SCENARIO=error npm run dev
```

## Design Source

Primary contract:

```text
docs/current/OWNER_RUNTIME_CONSOLE_UI_VISUAL_GOVERNANCE.md
docs/current/OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT.md
docs/current/OWNER_CONSOLE_ISOLATED_FRONTEND_HANDOFF.md
```
