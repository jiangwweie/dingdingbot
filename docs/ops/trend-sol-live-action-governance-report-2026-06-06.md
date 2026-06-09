> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Trend/SOL Live Action Governance Report

Date: 2026-06-06

## Verdict

PASS_WITH_CONSTRAINT

The exact-scope Trend/SOL production action completed through the official API
path and is now closed on exchange exposure. Entry and take-profit are filled.
The authorization is consumed and retry is blocked. A remaining exchange stop
order/algo is still visible in stop-order reads after the position is flat, so
post-live cleanup/final-review is required before another action.

## Scope

- Carrier: `TF-001-live-readonly-v0`
- Symbol: `SOL/USDT:USDT`
- Side: `long`
- Quantity: `0.1`
- Max notional: `20`
- Leverage: `1`
- Protection: `single_tp_plus_sl`
- Authorization: `auth-8e591fb066af43578094c27064ede55f`
- Intent: `intent-e6ec405fa0fe4ba1bc82d3b246a6c9ef`

## Server Credential Preflight

Server-side Binance credential preflight passed before execution:

- canonical credentials present: `EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET`
- `TRADING_ENV=live`
- `EXCHANGE_TESTNET=false`
- reading enabled: true
- futures enabled: true
- withdrawals enabled: false
- IP restricted: true and compatible with the Tokyo server
- pre-execute SOL active position count: 0
- pre-execute SOL open order count: 0
- pre-execute SOL stop order count: 0

No credential value or raw secret was printed or written to evidence.

## Execution Result

- Entry exchange order: `218766349737`
- Entry status: `FILLED`
- Entry filled quantity: `0.1`
- Entry observed price: `62.38`
- TP exchange order: `218766349863`
- TP status: `FILLED`
- TP filled quantity: `0.1`
- TP observed price: `63.0`
- SL order/algo id: `4000001500443218`
- Review record: `review-auth-8e591fb066af43578094c27064ede55f`
- Execution result status: `executed`
- Protection result at execution time: `protected`

## Current Live State

Read-only exchange evidence after execution:

- active SOL position count: 0
- ordinary open order count: 0
- stop order count: 1
- visible stop id: `4000001500443218`

Interpretation: the position is flat after TP fill. The remaining stop order is
an orphan-protection artifact until a separate scoped cleanup/final-review task
handles it. This report does not cancel, replace, flatten, or retry protection.

## PG Evidence

Read-only PG evidence:

- authorization rows: 1
- authorization consumed: true
- execution intent rows: 1
- execution intent status: `completed`
- local order rows: 3
- execution result rows: 1
- scoped runtime safety clearance rows: 2
  - `gks`
  - `startup_guard`

Local PG orders recorded:

- entry local order: `c51b913e-ab69-4233-82cf-9af8e1f43130`, `MARKET`, `FILLED`, exchange `218766349737`
- TP local order: `6426f4d0-7edc-4513-8020-71eb864338b1`, `LIMIT`, PG status `OPEN`, exchange `218766349863`
- SL local order: `1632dfa6-e968-4d27-8414-c89e30719c60`, `STOP_MARKET`, PG status `OPEN`, exchange/algo `4000001500443218`

PG/exchange consistency constraints:

- Exchange shows TP `FILLED`, while PG still has TP local row as `OPEN`.
- Exchange shows no position, while PG still has SL local row as `OPEN`.
- This requires post-live review reconciliation; no manual PG patch was made.

## Retry Safety

Retry is blocked as expected:

- `authorization_already_consumed`
- `duplicate_execution_intent_for_authorization`
- `previous_intent_status_not_retryable:completed`

No duplicate execution occurred.

## Release And Deployment State

Production service:

- service: `brc-owner-console-backend.service`
- status: active
- health: `runtime_bound=true`, `live_ready=false`
- active port: `127.0.0.1:18080`
- temporary execute API port `18081`: stopped

Release repair performed:

- Previous attempted release path `trend-execute-bda6c1fa-min-20260606134340`
  was a symlink to `trading-console-v03-20260604145733`, not a real release
  directory.
- A real release directory was created:
  `/home/ubuntu/brc-deploy/releases/trend-sol-governance-8c6ddb9a-202606061415`
- `/home/ubuntu/brc-deploy/app/current` now points to that real release
  directory.
- The production process was not restarted. Its process cwd remains the old
  release inode:
  `/home/ubuntu/brc-deploy/releases/trading-console-v03-20260604145733`

Route availability:

- active production `GET /api/health`: 200
- active production new preflight/readiness routes: 404 until service restart
- disk `app/current` contains the new preflight/readiness code and scoped GKS
  clearance fix.

## Schema Drift Notes

Tokyo PG differs from the latest local ORM/API expectations:

- `orders.side` is missing.
- `brc_execution_results.authorization_id` is missing.

Evidence collection handled this dynamically and did not mutate PG. These gaps
should be addressed by a separate migration/release alignment task.

## Evidence Files

Server:

- `/home/ubuntu/brc-deploy/reports/trend-sol-governance-20260606/pg-state.json`
- `/home/ubuntu/brc-deploy/reports/trend-sol-governance-20260606/exchange-state.json`
- `/home/ubuntu/brc-deploy/reports/trend-sol-governance-20260606/exchange-orders.json`

Local copies:

- `reports/trend-sol-governance-20260606/pg-state.json`
- `reports/trend-sol-governance-20260606/exchange-state.json`
- `reports/trend-sol-governance-20260606/exchange-orders.json`

## Blocker Records

### BR-TREND-SOL-ORPHAN-SL-20260606

- stage: post-live protection review
- path: exchange stop-order read
- evidence: position count 0, ordinary open order count 0, stop order count 1,
  stop id `4000001500443218`
- severity: high
- bridge: preserve current order state, do not cancel in this governance task
- retry_condition: Owner-approved cleanup/final-review task that may cancel
  orphan protection through official path after fresh read-only evidence

### BR-TREND-SOL-PG-EXCHANGE-DRIFT-20260606

- stage: post-live reconciliation
- path: PG local orders vs exchange order reads
- evidence: exchange TP `FILLED`; PG TP and SL local rows remain `OPEN`
- severity: medium
- bridge: document drift and avoid manual PG patch
- retry_condition: scoped reconciliation/review task updates read model or PG
  status through audited service path

### BR-TREND-SOL-RELEASE-DRIFT-20260606

- stage: deployment governance
- path: release/symlink inspection
- evidence: previous release path was a symlink; active process cwd remains old
  release; `app/current` now points to repaired real release
- severity: medium
- bridge: created real release directory and repointed `app/current` without
  restarting production service
- retry_condition: planned service restart/deploy verification window after
  post-live orphan-protection state is resolved or explicitly accepted

### BR-TREND-SOL-SCHEMA-DRIFT-20260606

- stage: evidence capture
- path: Tokyo PG schema inspection
- evidence: `orders.side` and `brc_execution_results.authorization_id` missing
- severity: medium
- bridge: dynamic read-only evidence query; no PG mutation
- retry_condition: migration/release alignment task

## Safety Proof

- No new strategy action was started.
- No Volatility Expansion or Mean Reversion action support was expanded.
- No auto-execution was enabled.
- No cancel, replace, flatten, or retry protection was executed.
- No credential or secret values were printed.
- Production `18080` service was not restarted.
- Temporary `18081` API-only execute process was stopped.
- Current production health remains `runtime_bound=true`, `live_ready=false`.

## Local Version State

Relevant local commits:

- `bda6c1fa fix(brc): add server credential preflight readiness`
- `8c6ddb9a fix(brc): support scoped gks safety clearance`

Push status: not pushed.

## Next Task

Run a scoped Trend/SOL post-live final-review and orphan-protection cleanup task:

1. Re-read SOL position/open/stop orders.
2. Confirm position remains flat.
3. If the stop/algo order is still open, cancel only that orphan protection
   through an audited official cleanup path after explicit Owner approval.
4. Reconcile PG TP/SL local order statuses and review record without manual
   unaudited PG patching.
