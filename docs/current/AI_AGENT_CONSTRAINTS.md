---
title: AI_AGENT_CONSTRAINTS
status: CURRENT
authority: docs/current/AI_AGENT_CONSTRAINTS.md
last_verified: 2026-06-18
---

# AI Agent Constraints

This is the short current entry for agents working on the StrategyGroup runtime
pilot. If this file conflicts with historical archive material, this file wins.

## Objective

The project objective is:

```text
Owner enables a StrategyGroup
-> system observes market conditions
-> system runs all required checks inside official safety boundaries
-> system executes only through the official real-order path when allowed
-> system protects, reconciles, settles, notifies, and records
-> Owner supervises status and intervenes only on abnormal states
```

The Owner should not need to read raw evidence packets to operate the system.
Evidence packets are audit artifacts under the Owner-facing control board.

The global business objective is profitability through a small-capital
right-tail StrategyGroup experimentation system. During the current stage,
profit is not the engineering acceptance test. Engineering work is valuable
only when it improves opportunity discovery, runtime capture, execution
quality, risk-capital governance, or the review loop.

The project is aggressive inside explicit constraints. The Owner-provided
subaccount allocation is already the risk-control result and may be treated as
loss-capable experiment capital. Agents must not add hidden conservatism on top
of that allocation by lowering leverage, reducing exposure, shrinking notional,
or slowing eligible submits merely because the trade is risky. Risk is not the
first-order blocker in this project; missed right-tail opportunity is also a
core failure mode.

The hard boundaries are operational and authority boundaries, not a mandate to
be cautious. They prevent wrong-account actions, stale-fact execution,
duplicate submits, missing protection, conflicting active exposure, Operation
Layer bypass, FinalGate bypass, withdrawals, transfers, credential mutation,
and live-profile or sizing-default mutation outside explicit Owner direction.
Inside the selected StrategyGroup, selected symbol/side universe, allocated
subaccount capital, and configured leverage/notional profile, the system should
prefer fast opportunity capture over additional discretionary de-risking.

When the system is healthy but waiting for market opportunity, agents should
not treat `waiting_for_market` as a blocker. Non-market-dependent progress
should happen through replay, synthetic signal fixtures, paper/simulator
operation-layer lifecycle tests, post-submit simulation, and cost/slippage
review inputs. Synthetic and replay signals must never be represented as live
market signals and must never feed a real Operation Layer submit.

Testnet is not a mainline value layer for this project. If used at all, it is a
temporary API-shape diagnostic tool. Meaningful execution-quality evidence comes
from the official live path with selected StrategyGroup, allocated subaccount
risk budget, fresh signal, RequiredFacts, candidate/authorization evidence,
action-time FinalGate, and official Operation Layer all passing.

## Owner Supervisor Constraint

The Owner is a supervisor, not an execution operator.

Owner-facing product UI must answer:

- which StrategyGroups are enabled;
- which are running, waiting, processing, paused, or unavailable;
- whether funds, orders, positions, protection, and reconciliation are normal;
- whether the Owner needs to intervene;
- what one-line reason explains an unavailable or intervention state.

Owner-facing product UI must not make the Owner drive internal execution steps.
Do not turn these internal names into main UI labels, navigation, table columns,
primary cards, or action buttons:

```text
FinalGate
Operation Layer
RequiredFacts
candidate
authorization
preflight
proof
route
refId
blocker code
runtime grant
```

Allowed main UI language is deliberately small:

```text
未启用
运行中
等待机会
处理中
暂不可用
需要介入
已暂停
已完成
无需操作
资金正常
订单正常
持仓正常
保护正常
```

Internal gate names and evidence details may appear only in audit, detail, or
developer surfaces after the Owner asks to expand them.

## Standing Authorization

During this development-stage pilot, do not create new chat-confirmation
blockers for:

- focused `codex/*` branches;
- bounded local commits;
- Tokyo deploy apply inside the active stage;
- read-only Tokyo/live fact validation;
- watcher observation after StrategyGroup selection;
- StrategyGroup runtime bootstrap / attach through the official API path when
  it only creates admission, binding, and shadow runtime records;
- official in-boundary real order action after action-time FinalGate and
  Operation Layer pass.

This does not authorize FinalGate bypass, Operation Layer bypass, withdrawals,
transfers, credential changes, live-profile expansion, order-sizing default
expansion, stale-fact execution, missing protection, duplicate-submit risk, or
conflicting active position/open order execution.

This also does not authorize agents to reinterpret the Owner's allocated
subaccount budget as needing additional risk cuts. If a live profile, leverage,
notional, exposure, or sizing default is already selected by the Owner or by the
current official profile, agents should preserve and use it rather than reduce
it for caution. Changes to those defaults still require explicit Owner
direction because they are authority changes, not routine safety fixes.

Do not deploy to Tokyo for every small local change. Routine status review
should use local cache or local goal-progress artifacts first, then at most one
L1 read-only Tokyo snapshot when cache is missing, stale, or schema-stale.
Bounded Tokyo deploy apply should be reserved for a stage-worthy fix,
deployable milestone, fresh-signal unblock, safety regression repair, or
explicit Owner request.

## StrategyGroup Runtime Bootstrap

`scripts/bootstrap_strategygroup_runtime_pilot.py` is the current bounded bridge
from StrategyGroup picker state to observable runtime instances.

Default mode is plan-only. `--execute` may be used during this development
stage under standing authorization when the packet shows no inventory blocker.
The script may create StrategyFamily, StrategyFamilyVersion, Admission,
TrialBinding, risk acceptance, promotion confirmation, and shadow
StrategyRuntimeInstance records through official API surfaces.

It must not create candidate records, ExecutionIntents, orders, withdrawals,
transfers, exchange submit actions, or Operation Layer bypasses.

## Gate Behavior

Every blocker must classify itself as one of:

| Class | Meaning |
| --- | --- |
| `waiting_for_market` | No fresh signal exists |
| `missing_fact` | Required fact or evidence is absent or stale |
| `deployment_issue` | Tokyo or local deployment is behind current code |
| `monitor_refresh_needed` | Local monitor cache is missing, stale, schema-stale, or tied to an old runtime head |
| `active_position_resolution` | Position, open order, or protection state needs resolution |
| `hard_safety_stop` | Execution would violate the safety boundary |
| `review_only_warning` | Strategy evidence is weak but not a live-safety blocker |

Gates exist to preserve bounded real-funds safety. They must not become opaque
all-AND project blockers.

Monitor cache freshness is not a live-trading safety blocker. Cache missing,
stale cache age, stale cache schema, or runtime-head mismatch must be classified
as `monitor_refresh_needed`. These states may emit `NOTIFY` to trigger a local
or one-shot L1 refresh, but they must not populate `checks.blockers`, must not
be reported as `hard_safety_stop`, and must not flip P0 from
`waiting_for_market` to blocked when the runtime chain itself remains ready.

Gate classes are internal safety classifications. The main Owner UI should map
them to one terse product sentence, for example:

| Internal condition | Owner-facing sentence |
| --- | --- |
| stale or missing facts | 事实不可用，暂不能使用 |
| monitor cache missing/stale/schema/head stale | 监控状态需刷新 |
| open order conflict | 有订单处理中，暂不能使用 |
| active position conflict | 有持仓处理中，暂不能使用 |
| missing protection | 保护未就绪，暂不能使用 |
| reconciliation mismatch | 订单结果不一致，等待系统处理 |
| `hard_safety_stop` | `需要介入` |
| `review_only_warning` | `运行中` (audit/detail available, not an Owner blocker) |

## Watch Branch Intake

Useful P0 content from `codex/runtime-signal-watcher-feishu` is carried
selectively. The broad docs reset has been completed on this branch through the
2026-06-15 docs-governance compression.

## Historical Docs

Historical docs are compressed into:

```text
docs/history-archive-2026-06-15-pre-governance.tar.gz
```

They are recovery material only. They must not be used as current product truth
or as a source of new chat-confirmation blockers.
