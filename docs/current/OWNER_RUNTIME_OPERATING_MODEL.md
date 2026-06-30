---
title: OWNER_RUNTIME_OPERATING_MODEL
status: CURRENT
authority: docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
last_verified: 2026-06-23
---

# Owner Runtime Operating Model

The Owner operating model is simple:

```text
enable StrategyGroup
-> system runs automatically inside official boundaries
-> Owner supervises status
-> Owner intervenes only when intervention is requested
-> Owner reviews outcomes later
```

## Authority Split

The global authority model is:

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade; Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

| Layer | Owner authority | System responsibility |
| --- | --- | --- |
| Strategy policy | Enable, pause, resume, promote, downshift, park, kill, or accept scoped strategy risk | Maintain registry, tier state, and decision evidence |
| Runtime scope | Allocate subaccount risk budget, profile, symbol/side scope, and production-stage transition | Enforce selected scope without hidden de-risking |
| Normal process | Supervise status and intervene only when requested | Observe, check, prepare, submit through official path, protect, reconcile, settle, and record |
| Runtime authority | Cannot hand-grant runtime trade/order authority | Produce Tradeability Decision from asset, policy, fact, signal, and gate inputs; produce Runtime Safety State from live-submit safety inputs |

The Owner can decide that a risky StrategyGroup deserves higher or lower tier
eligibility. The Owner should not be turned into the operator who manually
assembles facts, validates every signal, approves every in-boundary candidate,
or reads raw evidence artifacts before routine process execution can continue.

## Owner Decisions

The Owner decides:

- which StrategyGroup is enabled, paused, parked, or killed;
- the allocated subaccount risk budget and official runtime profile;
- whether to adjust risk or pause automation when an abnormal state appears;
- whether to keep, revise, promote, park, or kill a StrategyGroup after review;
- when the project moves from development-stage pilot to production operations.

The Owner-provided subaccount allocation is already the upstream risk-control
decision. Within that allocation and the selected official runtime profile, the
system should behave aggressively toward eligible right-tail opportunities. It
should not ask the Owner to re-confirm or re-risk-assess every in-boundary
opportunity, and it should not silently reduce leverage, notional, or exposure
because the opportunity is risky. A 100% loss of the allocated experiment
capital is within the project premise.

## System Responsibilities

The system handles:

- watcher observation;
- signed GET-only live fact precollection for account, position, open orders,
  budget coverage, protection templates, and next-attempt readiness;
- fresh signal detection;
- RequiredFacts readiness;
- candidate and authorization evidence;
- action-time FinalGate;
- official Operation Layer submission path;
- post-submit finalize, reconciliation, budget settlement, and review evidence.

Those are system responsibilities, not normal Owner workflow steps.

If the remaining gap is fact mapping, classifier repair, replay coverage,
monitor integration, runtime readiness, or a non-authority engineering defect,
the system and agents should continue engineering progress instead of escalating
ordinary process work to the Owner.

Execution frictions in the small-capital pilot are engineering lifecycle
branches first and live calibration questions second. Fill probability, coarse
slippage, reject handling, partial-fill handling, protection acceptance,
reconciliation, settlement, and PnL calculation should be modeled, tested, and
reviewed before the first real outcome. Live trading calibrates those branches;
it is not a generic reason to pause engineering.

Owner-facing readiness must separate pre-live closure from live validation:

| Layer | Meaning |
| --- | --- |
| `pre_live_rehearsal_ready` | Dry-run, simulation, local lifecycle, rough cost/PnL, reconciliation shape, and review shape are closed without exchange write |
| `live_submit_ready` | Fresh signal and action-time RequiredFacts/candidate/auth/FinalGate/Operation Layer/protection/account/exchange facts allow real submit |
| `live_outcome_calibrated` | Real fills, slippage, protection acceptance, settlement, and PnL have been observed and reviewed |

Missing `live_submit_ready` or `live_outcome_calibrated` must not erase
`pre_live_rehearsal_ready`. The system should keep moving through rehearsal
until the remaining gap is truly live-only.

The system's hard stops are operational boundaries: wrong account, out-of-scope
StrategyGroup/symbol/side/profile, stale facts, duplicate submit risk, missing
protection, conflicting active position or open order, FinalGate bypass,
Operation Layer bypass, withdrawal, transfer, credential mutation, or
unauthorized live-profile/sizing mutation. They are not generic reasons to make
the system reduce leverage, shrink notional, slow eligible submits, or avoid
right-tail opportunities after the Owner has allocated loss-capable capital.

Strategy evaluation follows
`docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`. High-return numbers
such as `100%` are right-tail aspiration anchors, not hard intake gates.
Leverage values such as `5x` are leverage scenarios, not automatic live
authorization and not automatic strategy disqualification. The system should
advance experiment-worthy strategy assets when their thesis, failure modes, risk
envelope, replay or paper evidence, and main-control absorption route are clear.

Strategy tradeability follows `docs/current/TRADEABILITY_DECISION_CONTRACT.md`.
The Owner-facing system must make the difference between these states explicit:

| State | Meaning | Owner role |
| --- | --- | --- |
| `trade_allowed_now` | Tradeability Decision and Runtime Safety State allow the official path to proceed | Supervise status |
| `market_wait` | Strategy is admitted and ready enough, but no fresh signal exists | No action |
| `asset_admission_gap` | Strategy is promising but not yet a final-owned trial/runtime asset | Review admission only when policy is needed |
| `policy_gap` | Capital, profile, symbol/side, leverage scenario, attempt cap, or tier decision is missing | Decide scoped policy |
| `facts_gap` | Fact source, RequiredFacts mapping, or freshness path is incomplete | No normal Owner action |
| `execution_gate_gap` | Runtime gate, protection, account, exchange, order, or position state blocks real submit | Usually no Owner action unless abnormal recovery is requested |
| `strategy_quality_gap` | Strategy is not experiment-worthy or its risk envelope cannot be expressed | Decide park, revise, or kill only at review level |
| `safety_stop` | A hard authority or safety boundary forbids execution | Intervene only if recovery or policy change is required |

The system should not show a promising short or mean-reversion candidate as
merely "waiting for market" when it has not yet passed asset admission or scoped
policy. It should say that it is pending admission, policy, facts, execution
gate, quality review, or safety resolution.

## Strategy Learning Mode

When the live path is healthy but waiting for a fresh market signal, the system
should continue improving StrategyGroup quality locally and through read-only
observation:

```text
no-action / would-enter observation
-> replay match or replay gap
-> classifier, facts, freshness, cost, or tier diagnosis
-> keep, revise, promote, park, kill, go-live, or block-for-safety decision
```

This is not Owner-operated trading. It is system learning. The Owner should not
manually interpret raw no-action evidence, replay files, or RequiredFacts gaps in
normal operation.

The current pre-live strategy-decision source is Strategy Asset State.
`docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md` is the current Strategy
Asset State pre-live evidence contract. The post-action record remains the
Review Ledger. Both are review artifacts; neither bypasses the official live
path. Pre-live evidence is not a general opportunity log; it records only
high-priority observations that change a StrategyGroup decision.

## Owner-Facing State

The Owner should see product states:

| State | Meaning |
| --- | --- |
| `not_enabled` | Owner has not enabled this StrategyGroup for runtime automation |
| `running` | StrategyGroup automation is enabled and healthy |
| `waiting_for_opportunity` | Automation is enabled and waiting for a usable market opportunity |
| `processing` | The system is handling signal, execution, protection, order, position, reconciliation, or settlement work |
| `temporarily_unavailable` | The StrategyGroup cannot be used right now; show one plain sentence |
| `needs_intervention` | Owner action is required, such as pause, risk adjustment, or recovery review |
| `paused` | Owner or system pause is active |
| `completed` | The latest run is settled and recorded |

Raw evidence artifacts remain available for audit but are not the Owner's daily
operating interface.

## Strategy Asset Layer

The StrategyGroup asset layer is the registry, not the runtime state. The
registry explains what a StrategyGroup eats, how it trades, what risks remain,
and what would promote, downshift, park, or kill it.

`trial_eligible`, Tradeability Decision, and Runtime Safety State must stay
separate:

| Boundary | Owner meaning |
| --- | --- |
| `trial_eligible` | This StrategyGroup may be considered for small-capital trial eligibility under scoped policy |
| Tradeability Decision | The only read model that answers whether the StrategyGroup can trade now and identifies the first blocker |
| Runtime Safety State | The only runtime safety read model that says whether the official live-submit path is currently safe enough to proceed |

No fresh signal makes the Tradeability Decision report market wait. It does not
automatically make the StrategyGroup a bad strategy or remove its trial
eligibility.

`tiny_live_intake_candidate` and `tiny_live_ready` must also stay separate:

| Field | Owner meaning |
| --- | --- |
| `tiny_live_intake_candidate` | Main control may review this as a small-capital experimental asset |
| `trial_asset_admission_candidate` | Main control is preparing registry, policy, facts, and risk-envelope admission |
| `admitted_trial_asset` | The strategy exists as a final-owned trial asset, still without action-time order authority |
| `armed_observation` | The system may observe it under scoped runtime rules |
| `tiny_live_ready` | Non-executing readiness is closed; a future fresh signal still needs action-time gates |

Owner approval may move a strategy through policy-dependent stages. It cannot
turn research evidence, intake status, or tiny-live readiness into current
runtime trade/order authority.

## Runtime Product State

During the StrategyGroup runtime pilot, the server should refresh Owner-readable
product state after each watcher tick:

```text
watcher tick
-> signed GET-only live facts
-> StrategyGroup readiness state
-> runtime pilot product state
-> notification only when state materially changes
```

If live facts are ready but no fresh signal exists, the correct product state is
`waiting_for_opportunity`. This is not an Owner blocker and should not ask for
chat confirmation.

## Product Language Rule

Main Owner screens should avoid internal gate names. Use terse language:

| Internal wording | Owner wording |
| --- | --- |
| RequiredFacts missing/stale | 事实不可用 |
| FinalGate / Operation Layer not reached | 系统自动处理中 |
| preflight / proof / route | Details only |
| blocker code | Details only |
| reconciliation mismatch | 订单结果不一致，等待系统处理 |

If everything is healthy, the Owner product surface should say `运行中`, `等待机会`, or `无需操作`.
Do not show a next-step prompt for healthy automation.

## Document Authority

This file is the current Owner-operating SSOT. The broader source-class and
authority rules live in `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`.
Historical docs compressed into
`docs/history-archive-2026-06-15-pre-governance.tar.gz` are recovery material
only and must not become current operating instructions.
