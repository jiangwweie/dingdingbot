# BRC-R4 API Surface Cleanup Plan

Date: 2026-05-26
Status: DESIGN_REVIEW
Scope: backend API architecture planning only. No code changes, no runtime
profile changes, no exchange action, no testnet order, no real live authority.

## 1. Why This Plan Exists

BRC-R4 will add a local Web operator console. The frontend should not be built
against the current historical API surface as-is.

The current backend API has grown from multiple prior phases:

- legacy monitor/config/backtest endpoints in `src/interfaces/api.py`;
- runtime console endpoints in `src/interfaces/api_console_runtime.py`;
- research read endpoints in `src/interfaces/api_console_research.py`;
- research job mutation endpoints in `src/interfaces/api_research_jobs.py`;
- broad config/profile mutation endpoints in `src/interfaces/api_v1_config.py`
  and `src/interfaces/api_profile_endpoints.py`.

Because the project is still in development and historical API compatibility
is not required, BRC-R4 should define a smaller delivery-oriented API surface
before the Web UI is implemented.

## 2. Current API Inventory

Route counts from current source:

| File | Route count | Current role | BRC-R4 disposition |
| --- | ---: | --- | --- |
| `src/interfaces/api.py` | 79 | Legacy monolith: health, signals, config, backtest, strategies, orders, positions, optimize, profiles | Do not build new Web against this. Freeze, then replace BRC-needed pieces through new routers. |
| `src/interfaces/api_console_runtime.py` | 47 | Runtime read/control, Phase 5E test endpoints, BRC endpoints, LLM workflow endpoints | Split into BRC, runtime-read, runtime-control, and dev-testnet routers. |
| `src/interfaces/api_console_research.py` | 6 | Read-only research artifact console | Keep read-only for now; later replace with strategy-pool read model. |
| `src/interfaces/api_research_jobs.py` | 10 | Research job/candidate mutation control plane | Defer from BRC Web; later fold into strategy-pool governance if still useful. |
| `src/interfaces/api_v1_config.py` | 42 | Broad config mutation/import/export/history/rollback | Remove from BRC Web surface; deployment control needs a separate smaller operator-safe design. |
| `src/interfaces/api_profile_endpoints.py` | 8 | Profile CRUD/activation/import/export | Remove from BRC Web surface; runtime profile changes remain separately authorized. |

## 3. Architecture Decision

Create a BRC-first API surface and make the Web console depend only on that
surface.

The target structure should be:

```text
src/interfaces/
  api_app.py
  dependencies.py
  schemas/
    brc.py
    runtime.py
    operator.py
    control.py
  routers/
    brc_campaigns.py
    brc_operator.py
    brc_llm_workflows.py
    runtime_read.py
    runtime_control.py
    dev_testnet_brc.py
    research_read.py
```

`src/main.py` remains the only execution-runtime composition root under
ADR-0010. New routers should obtain services through FastAPI dependencies from
the bound `RuntimeContext`, not through module-global compatibility helpers.

## 4. Target API Surface For BRC Web Console

### 4.1 BRC Campaign Read / Review

| Method | Path | Purpose | Web usage |
| --- | --- | --- | --- |
| `GET` | `/api/brc/campaigns/current` | Current active BRC campaign, if any | Main dashboard. |
| `GET` | `/api/brc/campaigns/latest` | Latest campaign even if ended | Review screen. |
| `GET` | `/api/brc/evidence` | Latest evidence packet | Evidence tab. |
| `GET` | `/api/brc/review-packet` | Review packet with final inventory | Review tab. |
| `GET` | `/api/brc/next-eligibility` | Next-campaign gate | Next step panel. |
| `GET` | `/api/brc/review-decisions` | Review decision list | Audit/history. |
| `GET` | `/api/brc/review-decisions/latest` | Latest Owner review decision | Next gate summary. |
| `POST` | `/api/brc/review-decisions` | Persist Owner review decision only | Review decision form. |

Notes:

- Review decision is not an execution action.
- It must not create campaign, arm runtime, place order, transfer, withdraw, or
  authorize live.

### 4.2 BRC Operator

| Method | Path | Purpose | Web usage |
| --- | --- | --- | --- |
| `POST` | `/api/brc/operator/plan` | Convert Owner text into persisted action plan | Text input. |
| `GET` | `/api/brc/operator/actions` | List action ledger | Audit table. |
| `GET` | `/api/brc/operator/actions/{action_id}` | Read action detail | Detail drawer. |
| `POST` | `/api/brc/operator/actions/{action_id}/run` | Run confirmed read-only action | Confirmation modal. |

Notes:

- Keep compatibility `/operator/run` out of the Web contract.
- Web must never auto-fill `CONFIRM_READ_ONLY_BRC`.

### 4.3 BRC LLM Workflow

| Method | Path | Purpose | Web usage |
| --- | --- | --- | --- |
| `POST` | `/api/brc/llm/workflows` | Create workflow from Owner text | LLM action planner. |
| `GET` | `/api/brc/llm/workflows` | List workflow runs | Workflow history. |
| `GET` | `/api/brc/llm/workflows/{workflow_run_id}` | Read workflow detail | Detail drawer. |
| `POST` | `/api/brc/llm/workflows/{workflow_run_id}/confirm` | Resume confirmed workflow | Confirmation modal. |

Notes:

- Read-only actions require `CONFIRM_READ_ONLY_BRC`.
- Fixed testnet rehearsal requires `CONFIRM_BRC_TESTNET_REHEARSAL`.
- Web must not auto-fill either phrase.
- Testnet rehearsal remains fixed, server-owned, and profile-gated.

### 4.4 Runtime Read

| Method | Path | Purpose | Web usage |
| --- | --- | --- | --- |
| `GET` | `/api/runtime/overview` | Runtime summary | Status header. |
| `GET` | `/api/runtime/health` | Runtime health | Safety panel. |
| `GET` | `/api/runtime/positions` | Current positions | Inventory view. |
| `GET` | `/api/runtime/execution/orders` | Orders | Execution table. |
| `GET` | `/api/runtime/execution/intents` | Execution intents | Intent table. |
| `GET` | `/api/runtime/events` | Timeline | Event stream. |
| `GET` | `/api/runtime/inventory/brc` | BRC ETH/BTC exchange + PG flatness | Preflight/final flatness. |

Notes:

- This surface is read-only.
- It may expose status and evidence but must not perform cleanup.

### 4.5 Runtime Control

| Method | Path | Purpose | Web usage |
| --- | --- | --- | --- |
| `GET` | `/api/runtime/control/global-kill-switch` | Read GKS | Safety panel. |
| `GET` | `/api/runtime/control/startup-trading-guard` | Read startup guard | Safety panel. |
| `GET` | `/api/runtime/control/campaign-state` | Read runtime campaign state | Gate panel. |
| `GET` | `/api/runtime/control/campaign-state/replay-evidence` | Read replay proof | Audit panel. |

For BRC-R4 local console, mutation controls should remain hidden by default.
If exposed locally, they must stay under a separate "danger/control" section
and require explicit typed confirmation.

## 5. Endpoint Disposition

### Keep For BRC-R4 Web

- BRC campaign read/review/next eligibility endpoints.
- BRC operator plan/action ledger/read-only run endpoints.
- BRC LLM workflow endpoints.
- Runtime read endpoints for health, positions, orders, intents, events.
- GKS/startup/campaign-state read endpoints.
- BRC inventory flatness endpoint.

### Move To Dev/Testnet Router

- `/api/runtime/test/smoke/*`
- `/api/runtime/test/phase5e/*`
- `/api/runtime/test/brc/{symbol}/execute-controlled-entry`
- `/api/runtime/test/brc/{symbol}/execute-controlled-close`
- `/api/runtime/test/brc/{symbol}/arm-attempt`
- `/api/runtime/test/brc/mock-pnl`
- `/api/runtime/test/brc/finalize`

These are testnet/dev operator endpoints. They can remain available locally
under strict gates, but they should not be part of the default Web console
contract except through the fixed BRC LLM workflow confirmation.

### Freeze / Later Replace

- `src/interfaces/api_console_research.py` read-only research artifact views.
- `src/interfaces/api_research_jobs.py` research job and candidate mutation
  endpoints.

Future replacement should be the strategy-pool track:

`research artifact -> strategy pool entry -> Owner review -> optional Strategy Contract bridge`

### Delete / Exclude From BRC Web Surface

These are not necessarily deleted immediately, but BRC-R4 Web should not call
them:

- legacy strategy apply/strategy param mutation endpoints;
- config import/export/rollback/snapshot activation endpoints;
- profile CRUD/activation/import/export endpoints;
- optimizer endpoints;
- legacy order creation/cancel/position close/reconciliation mutation endpoints.

If any of these capabilities are needed later, they should return through a new
operator-safe design with auth, idempotency, replay protection, and explicit
Owner authorization.

## 6. Refactor Sequence

### Step 1: Contract Freeze

- Add this plan as the BRC-R4 API contract source.
- Add a frontend API adapter that calls only the target BRC Web surface.
- Do not change backend behavior yet.

### Step 2: Router Split Without Behavior Change

- Extract BRC request/response schemas from `api_console_runtime.py`.
- Move BRC campaign/operator/workflow endpoints into dedicated routers.
- Move runtime read endpoints into `runtime_read.py`.
- Move GKS/startup/campaign-state read/control into `runtime_control.py`.
- Move Phase5E/smoke/direct BRC testnet mutation endpoints into
  `dev_testnet_brc.py`.

### Step 3: Dependency Cleanup

- Replace `_load_api_module()` and `getattr(api_module, "_service")` reads in
  new routers with FastAPI dependencies.
- Dependencies should read `request.app.state.runtime`.
- If no `RuntimeContext` is bound, runtime/BRC endpoints fail closed with
  `503`, except explicitly allowed static/read-only shell endpoints.

### Step 4: Web Console Implementation

- Implement BRC-first pages in `gemimi-web-front`.
- Keep old runtime/research pages as hidden or legacy until explicitly
  retained.
- Web calls only target BRC-R4 API contract.

### Step 5: Pre-Deploy Security Gate

Before Feishu/cloud/Web mutation control:

- auth/session;
- CSRF/callback protection;
- request signing/timestamp window for Feishu;
- nonce/idempotency;
- confirmation bound to workflow/action id;
- secret manager;
- deployment preflight/runbook.

## 7. Acceptance Criteria For BRC-R4 API Cleanup

- Web adapter imports no legacy `/api/strategies`, `/api/strategy/params`,
  `/api/v3/orders`, `/api/v3/positions/{id}/close`, `/api/config/profiles`,
  or config rollback/import/export paths.
- New BRC router tests prove:
  - read endpoints work through `RuntimeContext`;
  - missing context returns fail-closed `503`;
  - read-only operator run cannot mutate;
  - workflow confirmation cannot run twice;
  - wrong confirmation blocks and persists state;
  - testnet rehearsal action remains fixed and profile/testnet gated.
- `api.py` remains available only as a legacy shell during transition.
- No real live/mainnet, withdrawal/transfer, strategy execution, automatic
  sizing/leverage/side decision, or generic order path is added.

## 8. Recommendation

Proceed with:

`BRC-R4-000 API Surface Cleanup`

before implementing the Web pages.

The first implementation slice should be router extraction and dependency
cleanup for BRC campaign/operator/workflow read surfaces only. Direct testnet
mutation endpoints should be moved last, because they are higher risk and
already have working gates.

