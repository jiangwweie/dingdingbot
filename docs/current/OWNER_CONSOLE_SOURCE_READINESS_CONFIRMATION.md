---
title: OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION
status: CURRENT_PILOT_EVIDENCE
authority: docs/current/OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION.md
last_verified: 2026-07-05
---

# Owner Console Source Readiness Confirmation

## Scope

This confirmation answers the backend-source questions from:

```text
/Users/jiangwei/Documents/final-owner-console/docs/current/OWNER_CONSOLE_BACKEND_SOURCE_HANDOFF.md
```

It does not redefine Owner product-client layout, primary Owner vocabulary, or
StrategyGroup product design.

| Field | Value |
| --- | --- |
| Worktree | `/Users/jiangwei/Documents/final` |
| Branch | `codex/owner-runtime-console-v1` |
| Commit | `e7c2f4000183e09bd61600d728f87ce30690db43` |
| Runtime profile used for confirmation | Tokyo current read-only runtime reports plus local tracked SSOT files |
| Confirmation timestamp UTC | `2026-06-16T03:18:44Z` |
| Confirmation timestamp CST | `2026-06-16T11:18:44+0800` |
| Read-only only | yes |

## Executive Result

| Source | Status | Evidence | Owner Console impact |
| --- | --- | --- | --- |
| StrategyGroup catalog | `ready` | Five tracked handoff files exist under `docs/current/strategy-group-handoffs/{MPG-001,TEQ-001,FBS-001,PMR-001,SOR-001}/handoff.json`; `main-control-handoff-index.md` lists all five groups. | Always show MPG / TEQ / FBS / PMR / SOR as catalog rows. Runtime-source problems must not make StrategyGroups disappear. |
| Strategy runtime repository | `ready` for Tokyo reports; `degraded` for local shell | Tokyo `strategygroup-runtime-pilot-status.json` reports active runtime rows and `status=waiting_for_market`; current local shell does not have PG env loaded. | Use Tokyo/read-only service as source for live runtime overlay. If local Owner Console backend lacks PG env, show catalog rows with `暂不可用`, not an empty catalog. |
| Runtime admission/binding | `ready` | `strategygroup-runtime-pilot-status.json` reports `runtime_binding=configured`; current control board counts: `total=5`, `observing=4`, `observe_only_ready=1`, `selected=1`. | StrategyGroup rows may show running/waiting states when readmodel is reachable. Admission unavailability should degrade row status only. |
| Watcher status | `ready` | `brc-runtime-signal-watcher.timer` is `active/enabled`; latest service run exited `SUCCESS`; latest `post-signal-resume-pack.json` reports `status=waiting_for_market`. | System freshness can be shown as running/waiting. Current user-facing state is `等待机会` / `无需操作`. |
| Live facts readiness | `ready` when PG fact snapshots are current | `strategy-group-live-facts-readiness.json` is now a PG-derived export from `brc_runtime_fact_snapshots`; it is not a runtime input file. | Funds/orders/positions/protection health can be displayed as current. Fresh signal is still required before candidate/action path. |
| Account funds | `ready` when PG `account_safe` snapshots prove account facts | `brc_runtime_fact_snapshots` stores account/budget facts; `strategy-group-live-facts-input.json` is retired and must not be read as the source. | Show sanitized fund pool status. Do not show API keys, account ids, raw secrets, or full wallet detail. |
| Local orders | `ready_empty` when PG account snapshots prove no open orders | `brc_runtime_fact_snapshots` stores open-order summary facts; no exchange write is called. | Show `暂无订单`, not `订单状态暂不可用`. |
| Local positions | `ready_empty` when PG account snapshots prove no active position | `brc_runtime_fact_snapshots` stores active-position summary facts. | Show `暂无持仓`, not `持仓状态暂不可用`. |
| Protection state | `ready` when PG account/protection snapshots prove the protection template is ready | Runtime fact snapshots carry protection readiness; candidate-specific protection is created only when a fresh candidate exists. | Show `保护正常` for observation state. |
| Reconciliation state | `degraded` | Current readiness reports prove no active position, no open order, no order creation, and no exchange write in the latest watcher cycle; no separate latest reconciliation summary was included in the source-readiness evidence set. | Homepage can show `系统正常` only for no-active-order/no-position observation. Detailed reconciliation panel should show `对账详情暂不可用` until a dedicated latest reconciliation source is wired. |
| Operation audit | `degraded` | Main runtime contains Operation Layer API/repository code (`/api/brc/operations`, `PgBrcOperationRepository`) and Trading Console operations cockpit endpoint, but the current watcher source-readiness evidence set does not include an authenticated operation-audit list probe. | Do not block StrategyGroup visibility. Hide or degrade audit/detail history with `审计详情暂不可用` until Owner Console has a read-only operation-audit source. |

## Evidence Paths

| Evidence | Path |
| --- | --- |
| External client handoff request | `/Users/jiangwei/Documents/final-owner-console/docs/current/OWNER_CONSOLE_BACKEND_SOURCE_HANDOFF.md` |
| StrategyGroup catalog SSOT | `/Users/jiangwei/Documents/final/docs/current/strategy-group-handoffs/main-control-handoff-index.md` |
| StrategyGroup handoff files | `/Users/jiangwei/Documents/final/docs/current/strategy-group-handoffs/*/handoff.json` |
| Tokyo runtime pilot status | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategygroup-runtime-pilot-status.json` |
| Tokyo live facts readiness | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategy-group-live-facts-readiness.json` |
| Tokyo live facts input | retired; runtime/readmodel source is `brc_runtime_fact_snapshots` |
| Tokyo watcher resume pack | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/post-signal-resume-pack.json` |
| Tokyo product refresh artifact | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/product-state-refresh-packet.json` |

## Sanitized Environment Confirmation

This confirmation did not copy, print, or commit secrets.

| Item | Status | Notes |
| --- | --- | --- |
| Local `.env.local.readonly` file | present | Presence only confirmed; values were not printed. |
| Local `.env.local` file | present | Presence only confirmed; values were not printed. |
| Local `live-config.env` file | present and untracked | Presence only confirmed; values were not printed. |
| Current shell `PG_DATABASE_URL` | not loaded | Local shell did not expose PG env. |
| Current shell `DATABASE_URL` | not loaded | Local shell did not expose database env. |
| Current shell `RUNTIME_PROFILE` | not loaded | Local shell did not expose runtime profile. |
| Current shell exchange key env | not loaded | No key values were read or printed. |
| Tokyo live fact precollect | retired | Product-state refresh no longer writes or consumes `strategy-group-live-facts-input.json`; account/public facts are PG-backed snapshots. |

## Owner Console Source Contract

### Required Fallback Rule

StrategyGroup catalog readiness and runtime readiness are separate.

| Condition | Required Owner Console behavior |
| --- | --- |
| Catalog `ready` and runtime source `ready` | Show StrategyGroups with live runtime overlay. |
| Catalog `ready` and runtime source `degraded` | Show StrategyGroups with `暂不可用` and one plain reason. |
| Catalog `ready` and runtime source `unavailable` | Show StrategyGroups with `暂不可用`; do not return `strategies=[]`. |
| Catalog unavailable | Show system-level `暂不可用`; this is a source failure, not an empty strategy list. |

### Empty Versus Unavailable

| Source | Empty state | Unavailable state |
| --- | --- | --- |
| Orders | `ready_empty` -> `暂无订单` | `unavailable` -> `订单状态暂不可用` |
| Positions | `ready_empty` -> `暂无持仓` | `unavailable` -> `持仓状态暂不可用` |
| Account funds | `ready` -> sanitized funds status | `unavailable` -> `资金状态暂不可用` |
| Operation audit | Empty audit list may be valid if source is readable | `degraded/unavailable` must not hide StrategyGroups |

## Required Owner Console Changes

These changes belong in:

```text
/Users/jiangwei/Documents/final-owner-console
```

1. Keep the StrategyGroup catalog visible from the handoff catalog even when
   runtime/PG source is unavailable.
2. Add `sourceHealth` semantics that distinguish `ready_empty` from
   `unavailable`.
3. Map `waiting_for_market` / `waiting_for_signal` to Owner language such as
   `等待机会` and `无需操作`.
4. Show account funds only as sanitized readonly status and bounded numeric
   summaries.
5. Treat Operation audit as a detail-source dependency, not a prerequisite for
   StrategyGroup visibility.

## Main Runtime Changes Needed

These changes belong in:

```text
/Users/jiangwei/Documents/final
```

1. Produce a stable machine-readable source-readiness artifact for Owner Console,
   derived from the same sources as this confirmation.
2. Add a read-only Operation audit list/detail probe to the source-readiness
   artifact.
3. Add a dedicated latest reconciliation summary source, separate from
   watcher/no-position/no-order inference.
4. Keep Tokyo signed GET-only live fact collection as the current account,
   order, position, protection, and budget source for the pilot.

## Not Authorized

- No real order placement.
- No exchange write action.
- No FinalGate bypass.
- No Operation Layer bypass.
- No credential or secret mutation.
- No live profile expansion.
- No order-sizing default expansion.
- No withdrawal or transfer action.

## Current Owner-Facing Summary

| Product area | Current Owner language |
| --- | --- |
| StrategyGroups | `可见` |
| Watcher | `运行中` |
| Market opportunity | `等待机会` |
| Account funds | `资金正常` |
| Orders | `暂无订单` |
| Positions | `暂无持仓` |
| Protection | `保护正常` |
| Reconciliation detail | `对账详情暂不可用` |
| Operation audit detail | `审计详情暂不可用` |
