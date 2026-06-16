---
title: OWNER_CONSOLE_BACKEND_SOURCE_HANDOFF
status: CURRENT_PILOT_SUPPLEMENT
authority: docs/current/OWNER_CONSOLE_BACKEND_SOURCE_HANDOFF.md
last_verified: 2026-06-16
---

# Owner Console Backend Source Handoff

## Purpose

This handoff is produced by the isolated Owner Console frontend/API worktree for
the main runtime worktree.

The goal is to let the main runtime window produce a source-readiness
confirmation artifact for the Owner Runtime Console without redefining the
Owner-facing UI or widening the live trading path.

## Worktree Boundary

| Window | Worktree | Responsibility |
| --- | --- | --- |
| Owner Console window | `/Users/jiangwei/Documents/final-owner-console` | Product projection, frontend, source-health contract, UI acceptance |
| Main runtime window | `/Users/jiangwei/Documents/final` | Runtime repositories, watcher state, live/read-only facts, account/order/position/protection source readiness |

The main runtime window should not decide visual layout, menu structure, or
homepage product vocabulary. It should confirm whether each backend source is
readable and what state it currently reports.

## Current Finding From Owner Console

The current local Owner Console endpoint is reachable:

```text
GET /api/health -> status ok, read_only true, live_ready false
```

But the product projection currently reports:

```text
strategies = []
fundPool.budget = 未声明
fundPool.available = 未声明
dataFreshnessLabel = 数据状态未知
systemLabel = 暂不可用
```

The source diagnostic split found:

| Source | Current Owner Console result | Product impact |
| --- | --- | --- |
| Strategy runtime repository | unavailable, persistent PG facts required | StrategyGroups disappear because runtime rows are empty |
| Watcher readmodel | `not_live_connected` | Data freshness cannot be called healthy |
| Pilot readmodel | `warning` | Strategy runtime pilot state is not healthy |
| Live facts readmodel | `warning` | Account/fact readiness cannot be trusted as healthy |
| Operations cockpit | present | Some read-only operation summary exists |
| Operation audit repository | unavailable, persistent Operation Layer required | Audit/action history cannot be shown as ready |
| Account funds source | not wired into product projection | Fund pool can only show `未声明` |

## Main Runtime Confirmation Artifact

The main runtime window should create this confirmation artifact:

```text
/Users/jiangwei/Documents/final/docs/current/OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION.md
```

The artifact must state the exact branch, commit, local environment profile, and
timestamp used for confirmation. It must not include credentials, secret values,
raw account keys, or exchange write authorization material.

## Required Confirmation Matrix

Use this matrix in the confirmation artifact.

| Source | Required status | Confirmation evidence | Owner product mapping |
| --- | --- | --- | --- |
| StrategyGroup catalog | ready | MPG-001, TEQ-001, FBS-001, SOR-001, PMR-001 are discoverable from current handoff/admission SSOT | StrategyGroups must remain visible even if runtime source is unavailable |
| Strategy runtime repository | ready / degraded / unavailable | PG runtime repository read succeeds or fails with exact sanitized error | Runtime overlay for each StrategyGroup |
| Runtime admission/binding | ready / degraded / unavailable | Current admission and trial-binding facts are readable | Enables or disables StrategyGroup rows |
| Watcher status | ready / degraded / unavailable | Watcher status source reports active, paused, stale, or missing | Top data freshness and per-strategy automation state |
| Live facts readiness | ready / degraded / unavailable | Required account/order/position/protection facts are fresh or stale | Funds/orders/positions/protection health |
| Account funds | ready / degraded / unavailable | Read-only account facts are readable; include only sanitized numeric summary | Fund pool budget, available amount, locked state |
| Local orders | ready_empty / ready_nonempty / unavailable | Local order repository read succeeds and count is known | `暂无订单`, `有订单处理中`, or `订单状态暂不可用` |
| Local positions | ready_empty / ready_nonempty / unavailable | Local position repository read succeeds and count is known | `暂无持仓`, `有持仓处理中`, or `持仓状态暂不可用` |
| Protection state | ready / degraded / unavailable | Protection records can be reconciled for active positions/orders | `保护正常`, `保护未就绪`, or `保护状态暂不可用` |
| Reconciliation state | ready / degraded / unavailable | Last reconciliation summary is readable | `系统正常`, `处理中`, or `需要介入` |
| Operation audit | ready / degraded / unavailable | Operation repository list/detail read succeeds or sanitized error is shown | Detail/audit history only; not required for StrategyGroup visibility |

## Status Definitions

| Status | Meaning |
| --- | --- |
| `ready` | Source is reachable and returns current, interpretable data |
| `ready_empty` | Source is reachable and has no current orders or positions |
| `ready_nonempty` | Source is reachable and has active orders or positions |
| `degraded` | Source is reachable but stale, partial, warning, or missing freshness proof |
| `unavailable` | Source cannot be read from the current environment |

Do not collapse `ready_empty` into `unavailable`. Empty orders or positions are
normal product states when the repository itself is readable.

## Environment Confirmation

The main runtime window should confirm these items without copying secrets into
this repository:

| Item | Confirmation requirement |
| --- | --- |
| Runtime PG env | Whether the main worktree has the PG env needed by Strategy runtime repositories |
| Read-only account env | Whether `.env.local.readonly` or equivalent can read account facts without exchange writes |
| Runtime profile | Which profile is used for the confirmation |
| Tokyo/live read-only source | Whether current watcher/live facts are local, Tokyo, or another read-only source |
| Owner Console env handoff | Whether the Owner Console backend should load env from main worktree, receive an ignored readonly env file, or call a main-runtime read-only service |

The confirmation must mask secret-bearing variables. It can report presence as
boolean, for example:

```json
{
  "PG_DATABASE_URL": true,
  "RUNTIME_PROFILE": true,
  "READONLY_ACCOUNT_ENV": true
}
```

## Suggested Read-Only Checks

The main runtime window can use equivalent commands or scripts. These commands
are examples, not a requirement to use exact filenames.

```bash
pwd
git branch --show-current
git rev-parse --short HEAD
```

```bash
PYTHONPATH=. /opt/homebrew/bin/python3 - <<'PY'
import os, json

keys = [
    "PG_DATABASE_URL",
    "DATABASE_URL",
    "CORE_DATABASE_URL",
    "RUNTIME_PROFILE",
]
print(json.dumps({key: bool(os.getenv(key)) for key in keys}, indent=2))
PY
```

The main runtime window should then run the current project-native read-only
probes for:

- Strategy runtime repository list.
- StrategyGroup admission/binding state.
- Watcher status.
- StrategyGroup live facts readiness.
- Account funds snapshot through read-only facts.
- Local open orders.
- Local active positions.
- Protection/reconciliation summary.
- Operation audit list/detail.

## Confirmation Artifact Template

Use this structure for the main runtime artifact.

```markdown
---
title: OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION
status: CURRENT_PILOT_EVIDENCE
authority: docs/current/OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION.md
last_verified: YYYY-MM-DD
---

# Owner Console Source Readiness Confirmation

## Scope

- Worktree:
- Branch:
- Commit:
- Runtime profile:
- Confirmation timestamp:
- Read-only only: yes

## Executive Result

| Source | Status | Evidence | Owner Console impact |
| --- | --- | --- | --- |
| StrategyGroup catalog |  |  |  |
| Strategy runtime repository |  |  |  |
| Runtime admission/binding |  |  |  |
| Watcher status |  |  |  |
| Live facts readiness |  |  |  |
| Account funds |  |  |  |
| Local orders |  |  |  |
| Local positions |  |  |  |
| Protection state |  |  |  |
| Reconciliation state |  |  |  |
| Operation audit |  |  |  |

## Sanitized Errors

List sanitized errors only. Do not paste credentials, DSNs, account ids, or raw
exchange secrets.

## Required Owner Console Changes

List only changes needed in `/Users/jiangwei/Documents/final-owner-console`.

## Main Runtime Changes Needed

List only changes needed in `/Users/jiangwei/Documents/final`.

## Not Authorized

- No real order placement.
- No exchange write action.
- No FinalGate bypass.
- No Operation Layer bypass.
- No credential or secret mutation.
- No live profile expansion.
- No order-sizing default expansion.
```

## Owner Console Acceptance Rules After Confirmation

After the main runtime confirmation exists, the Owner Console worktree should
implement these product rules:

| Condition | Required Owner Console behavior |
| --- | --- |
| StrategyGroup catalog ready but runtime source unavailable | Show MPG, TEQ, FBS, SOR, PMR as visible rows with `暂不可用` and one plain reason |
| Account funds ready | Show sanitized fund pool numbers from the read-only source |
| Account funds unavailable | Show `资金状态暂不可用`, not `未声明` as if no account exists |
| Local orders ready empty | Show `暂无订单` |
| Local orders unavailable | Show `订单状态暂不可用` |
| Local positions ready empty | Show `暂无持仓` |
| Local positions unavailable | Show `持仓状态暂不可用` |
| Watcher degraded or stale | Show one data freshness warning at the system level |
| Operation audit unavailable only | Keep StrategyGroups visible; hide or degrade audit/detail history |

## Forbidden Scope For This Handoff

This handoff does not authorize:

- real trading actions;
- new submit paths;
- credential or secret changes;
- live profile expansion;
- order-sizing changes;
- bypassing official runtime, safety, or operation boundaries;
- turning internal evidence terms into Owner homepage labels.
