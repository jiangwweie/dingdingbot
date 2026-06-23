---
title: AI_AGENT_CONSTRAINTS
status: CURRENT
authority: docs/current/AI_AGENT_CONSTRAINTS.md
last_verified: 2026-06-23
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

Strategy evaluation uses the experiment-value contract in
`docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`. Do not reject or
stall a strategy merely because it has not proven a fixed `100%` return target.
Do not treat `5x` or any other leverage value as an automatic quality failure.
Leverage is a scenario to evaluate through liquidation buffer, path risk, loss
unit, attempt cap, protection, and pause rules. Runtime leverage authority still
comes only from the selected profile and action-time exchange facts.

Strategy tradeability uses `docs/current/TRADEABILITY_VERDICT_CONTRACT.md`.
Agents must not stop at "research absorbed", "packet ready", or
"waiting_for_market" when a strategy still cannot trade. Every active selected,
admitted, or newly absorbed candidate must expose:

- whether it can trade now;
- if not, the first blocker;
- whether the blocker is engineering, Owner policy, market, runtime,
  strategy-review, or safety;
- the exact next action;
- the state expected after that action.

Do not classify a candidate as `not_tradable_market_wait` unless asset
admission, scoped Owner policy, runtime observation scope, and non-live
readiness are already closed. A strategy such as a research-side short
candidate may be `tiny_live_intake_candidate` and still have the first blocker
`asset_admission`.

## Global Authority Model

Agents must preserve this split:

```text
Owner controls policy.
System executes process.
Runtime decides actionability.
Review updates strategy governance.
```

Owner policy includes StrategyGroup enable/pause/resume, promote/downshift,
park/kill, scoped risk acceptance, capital/profile/scope changes, and
production-stage transition.

System process includes observation, RequiredFacts mapping, fresh signal
detection, candidate/auth evidence, action-time FinalGate, official Operation
Layer, protection, reconciliation, settlement, and review capture.

Owner scoped risk acceptance may advance `trial_eligible` or tier eligibility.
It must not set `actionable_now=true` and must not bypass execution safety or
authority hard stops.

Do not convert StrategyGroup governance into Owner manual operation. Do not ask
the Owner to manually judge RequiredFacts, fresh signal, candidate/auth,
FinalGate, Operation Layer, replay samples, no-action rows, or ordinary
in-boundary execution steps.

If the remaining gap is engineering work, fact mapping, classifier repair,
replay coverage, monitor integration, or runtime readiness, continue the
engineering path. Escalate only for Owner policy, tier, capital/profile/scope,
pause/resume, promote/downshift/park/kill, production transition, or abnormal
intervention.

## Capability-Closure Discipline

Goal-mode tasks must not stop at explanation. Each task must close one
engineering problem class, unlock one concrete capability, and expose the next
engineering bottleneck.

Required Evidence Packet fields for non-trivial work:

- `closed_engineering_problem`;
- `capability_unlocked`;
- `next_engineering_bottleneck`;
- validation proving the capability works or the bottleneck is
  machine-checkable.

Do not mark a task complete when it only says a capability is missing. Convert
the missing capability into code, tests, generated checks, monitor integration,
or a precise next bottleneck. Use `partial` if the task only produced a packet,
summary, or diagnosis.

For strategy-admission work, the capability unlocked must be stated in
tradeability language. Examples:

| Capability | Meaning |
| --- | --- |
| `verdict_ready` | Each active candidate has a current tradeability verdict |
| `trial_asset_admission_candidate` | A research intake candidate has a final-owned admission proposal |
| `admitted_trial_asset` | Registry, policy, and tier surfaces recognize the trial asset without submit authority |
| `armed_observation_ready` | Runtime can observe the scoped asset without real-order authority |
| `tiny_live_ready` | Non-executing readiness is closed and only action-time gates remain |

Small-capital execution frictions are engineering lifecycle branches before
they are live blockers. Implement coarse cost estimates, submit/reject/partial/
timeout handling, protection failure handling, reconciliation shape, and Review
Ledger feedback paths locally where possible. Live outcomes calibrate these
branches; they should not be used as generic reasons to stop engineering.

## Phased Gate Discipline

Gate checks must identify which surface they block:

| Surface | Blocks | Must not block |
| --- | --- | --- |
| `rehearsal` | Broken local proof, fixture inconsistency, unsafe simulated lifecycle | Non-executing dry-run, simulation, packet generation, cost estimate, or recovery modeling because no live signal exists |
| `shadow` | Misleading candidate/readiness evidence or tier state | Read-only observation, replay, classifier repair, RequiredFacts mapping, or monitor integration |
| `live_submit` | Real exchange write when FinalGate, Operation Layer, protection, scope, account, or exchange facts fail | Non-executing engineering closure that keeps `actionable_now=false` |
| `review` | Claims that lack supporting evidence | Negative evidence, simulated outcomes, and rough cost/PnL as non-authority review input |

Do not require live signal, live fill, or live PnL before closing pre-live
engineering branches. Dry-run, simulation, paper Operation Layer, and
post-submit lifecycle rehearsal should be used to close submit/reject/partial/
timeout/protection/reconciliation/review shapes before live validation.

The boundary is authority, not progress. Rehearsal may unlock the next
engineering bottleneck, but it must not set `actionable_now=true`, fabricate
live RequiredFacts, bypass FinalGate or Operation Layer, or create exchange
writes.

When the system is healthy but waiting for market opportunity, agents should
not treat `waiting_for_market` as a blocker. Non-market-dependent progress
should happen through replay, synthetic signal fixtures, paper/simulator
operation-layer lifecycle tests, post-submit simulation, and cost/slippage
review inputs. Synthetic and replay signals must never be represented as live
market signals and must never feed a real Operation Layer submit.

After the P0 runtime path is live-ready, the main non-market work is
StrategyGroup learning, not report decoration. Agents should turn high-priority
no-action and would-enter observations into replay-to-review decisions:

```text
observation
-> reason codes
-> replay coverage
-> classifier / facts / freshness / cost / tier gap
-> StrategyGroup keep / revise / promote / park / kill / go-live boundary decision
```

Use `docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md` as the current
compatibility path for the minimal StrategyGroup Decision Ledger. It is
local/read-only decision support and must keep real-order authority false. It
is not a full opportunity log: records enter the main control layer only when
they change one of these decisions: `go_live`, `do_not_go_live`,
`keep_observing`, `revise`, `park`, `kill`, `promote`, or
`block_for_safety`.

Decision rows that use `promote` must include `promotion_scope`. Valid scopes
include `intake_only`, `trial_admission`, `armed_observation`,
`tiny_live_ready_review`, and `l4_eligibility_review`. Generic promote wording
is too ambiguous for new artifacts.

## Global Source Discipline

Agents must follow `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md` when
choosing sources. In short:

```text
Docs explain.
Registry defines strategy assets.
Policy records Owner-authorized control.
Runtime stores current system state.
Generated views summarize.
Archives preserve provenance.
```

StrategyGroup semantics belong in reviewed handoff packs and the registry
contract. Dynamic actionability belongs to runtime state. Owner risk acceptance
belongs to explicit Owner policy or current scoped decisions. Generated monitor,
replay, and ledger outputs are checkpoint evidence; they must not be hand-edited
into authority.

Strategy-research artifacts from `/Users/jiangwei/Documents/final-strategy-research`
must not become unconditional runtime monitor dependencies. Main control should
first copy, normalize, or absorb the research package into a final-owned
snapshot or structured intake artifact, then generate verdict and admission
outputs from final-owned inputs.

Goal-mode work must follow `docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md`.
Architecture direction should enter execution as one bounded Goal Packet, and
execution must return an Evidence Packet before the next architectural verdict.

## P0 / P0.5 Execution Discipline

P0 has priority over P0.5. P0.5 is an accelerator for opportunity discovery and
strategy quality; it is not a substitute for the first `MPG-001`
allocated-subaccount live closure.

Agents must obey these constraints:

| Constraint | Required behavior |
| --- | --- |
| Fresh signal preempts local work | If a real fresh selected StrategyGroup signal appears, pause P0.5 work and return to RequiredFacts -> candidate/auth -> FinalGate -> Operation Layer |
| Local/deployed/planned split | Every status summary must distinguish deployed Tokyo capability, local committed capability, and planned work |
| Decision-ledger requirement | P0.5 artifacts are useful only if they change `go_live`, `do_not_go_live`, `keep_observing`, `revise`, `park`, `kill`, `promote`, or `block_for_safety` |
| Replay/proxy boundary | Replay, synthetic fixtures, proxy facts, and opportunity ledger rows must never become live signal, live RequiredFacts, FinalGate input, Operation Layer evidence, or submit authority |
| Deploy threshold | Do not deploy for isolated wording, single report fields, or one-off local artifacts; deploy only after a stage-worthy closed local checkpoint or explicit Owner request |
| Entry-point control | Prefer extending the local monitor sequence, replay lab, opportunity decision loop, or opportunity ledger producer over adding permanent standalone scripts |

New P0.5 scripts or artifacts must satisfy at least one of:

- produce or consume minimal StrategyGroup Decision Ledger rows;
- feed the local monitor sequence;
- replace and reduce older entry points;
- create a bounded one-time migration or validation artifact with no long-term
  mainline role.

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

Gate scope must be explicit. A live-submit gate may block only real exchange
write or live actionability. It must not block local dry-run, simulation,
paper/simulator Operation Layer, post-submit lifecycle rehearsal, rough
cost/PnL estimation, or monitor/review shape work when those artifacts remain
non-executing and non-authoritative.

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
