---
title: STRATEGYGROUP_RUNTIME_PILOT_OVERLAY
status: CURRENT_CANON_OVERLAY
authority: owner-decision-2026-06-14 + branch-scope-audit
last_verified: 2026-06-15
applies_to:
  - /Users/jiangwei/Documents/final
  - codex/strategygroup-runtime-pilot
supersedes_when_conflict:
  - historical per-deploy chat confirmation language
  - historical per-order chat confirmation language inside the official runtime path
  - evidence-packet-as-owner-interface workflow language
---

# StrategyGroup Runtime Pilot Overlay

This overlay narrows current BRC constraints for the active StrategyGroup
runtime pilot. It does not weaken FinalGate, Operation Layer, auditability, or
fund-movement red lines.

---

## 1. Current Pilot Objective

The active product objective is:

```text
Owner selects a StrategyGroup
-> system admits or rejects the group with clear reasons
-> system creates or attaches a bounded StrategyRuntimeInstance
-> system observes the market automatically
-> system prepares candidates only from fresh strategy signals
-> system executes only through FinalGate + Operation Layer when action-time facts pass
-> system finalizes, reconciles, settles budget, and records review
```

The Owner-facing goal is not to read evidence packets or manually confirm every
runtime step. Evidence packets are machine / agent / audit artifacts. The
console or agent report must translate them into Owner-readable state:

- what is being observed;
- whether the strategy group is armed, waiting, blocked, or in review;
- why a candidate can or cannot approach funds;
- what the next automatic recovery or waiting condition is;
- whether the condition is a market wait, missing fact, deployment issue, or
  hard safety stop.

---

## 2. Standing Authorizations For This Pilot

Within this branch and active pilot scope, the following are standing
authorized and must not be turned into new chat-confirmation blockers:

| Area | Standing authorization | Required boundary |
| --- | --- | --- |
| Branching | Create focused `codex/*` branches from `program/live-safe-v1` | Report cwd, branch, HEAD, and scope |
| Local commits | Commit bounded, verified stages locally | Report tests and touched authority |
| Tokyo deploy apply | Deploy current pilot commits when deployment is part of the active stage | Generate or verify deploy packet / manifest, preserve secrets, report rollback surface |
| Tokyo / live facts | Run read-only account, position, open-order, protection, budget, and next-gate validation | GET-only or configured read-only environment for fact collection |
| Development cleanup | Repair, reset, archive, compress, or remove stale development artifacts | Do not delete secrets or active safety evidence needed for current reconciliation |
| Side workers | Use bounded non-core side workers | Task-card scope, no core execution-chain drift |
| Strategy observation | Start or continue watcher / runtime observation after StrategyGroup selection | No exchange write merely from observation |
| Real order action | Submit a real order only if the official runtime / Operation Layer action path and action-time FinalGate pass | No bypass, no stale facts, no missing protection, no duplicate-submit risk |

Deploy apply and official in-boundary real order action must not wait for a
fresh chat phrase every time during this project-development phase. They still
must produce auditable evidence and stop on hard safety failures.

---

## 3. Hard Stops That Remain

These remain prohibited and are not softened by this overlay:

- withdrawal or transfer actions;
- secret, credential, or live-profile permission changes;
- order-sizing default expansion or runtime-boundary expansion outside the
  accepted pilot profile;
- Operation Layer bypass;
- FinalGate bypass;
- unauditable exchange write;
- using stale or missing account / position / open-order facts as allow
  signals;
- missing concrete protection for a protected strategy action;
- unresolved duplicate-submit risk;
- conflicting active position or open order that cannot be reconciled;
- strategy self-elevation into higher budget, leverage, autonomy, or wider
  symbols without the admission path.

Changing the project from development-stage pilot to production operations will
require a later Owner decision and a new constraint baseline.

---

## 4. Gate Behavior

Gates must be liveness-preserving. A gate may block unsafe execution, but it
must not become an opaque all-AND wall that prevents project progress.

Every blocker report must classify itself as one of:

| Class | Meaning | Required behavior |
| --- | --- | --- |
| `waiting_for_market` | No fresh signal exists | Continue observation and notify only on material change |
| `missing_fact` | Required fact is absent or stale | Collect, repair, or downgrade where safe |
| `deployment_issue` | Tokyo or local deployed state is behind current code | Prepare deploy packet or apply standing-authorized deploy when in scope |
| `active_position_resolution` | Position / open order / protection state must be reconciled | Resolve before any fresh candidate approaches funds |
| `hard_safety_stop` | Action would violate FinalGate, Operation Layer, protection, idempotency, or fund-movement boundaries | Stop execution path and report the specific safety reason |
| `review_only_warning` | Evidence is weak, sample is low, or strategy economics are unproven | Disclose, record for review, and do not treat as a live-safety blocker by itself |

FinalGate is an action-time safety gate. It is not a research-alpha proof gate.
Weak strategy evidence can restrict budget, leverage, autonomy, or review
classification, but after Owner acceptance of small-capital right-tail
experimentation it must not block observation or bounded pilot wiring by itself.

---

## 5. StrategyGroup Handoff Contract

Strategy research may hand off StrategyGroups through structured Markdown,
JSON, or both. YAML is not mandatory unless a specific validator requires it.

A handoff is sufficient for runtime-pilot intake when it provides:

- `strategy_group_id`;
- supported symbols and sides;
- activation / signal-ready rule;
- required facts and freshness;
- missing / stale fact behavior;
- risk defaults;
- hard stops;
- sample signal, no-signal, stale, and conflict packets.

The main controller owns runtime admission, watcher scope, RequiredFacts
readiness, candidate preparation, FinalGate, Operation Layer, post-submit
finalize, and review-loop integration.

---

## 6. Branch Handling For This Pilot

The active pilot branch is:

```text
codex/strategygroup-runtime-pilot
```

It must be cut from:

```text
program/live-safe-v1
```

The prior watcher branch is a side branch. Its useful P0 capabilities may be
selectively replayed or cherry-picked after review. Its large document
compression / deletion changes are a separate docs-governance integration item
and must not be mixed into the StrategyGroup runtime pilot branch merely
because they exist.

---

## 7. Owner Interface Rule

The Owner should see a Strategy Control Board / concise agent report, not raw
evidence packet archaeology.

Required Owner-facing state:

| Surface | Required fields |
| --- | --- |
| StrategyGroup row | id, role, status, signal state, facts state, risk profile, hard stop state, next action |
| Candidate row | fresh signal id, symbol, side, candidate state, blocker, FinalGate status, Operation Layer status |
| Runtime row | runtime id, budget, attempts, active position, open order, protection, next gate |
| Review row | outcome, MFE / MAE / R multiple when available, promote / keep observing / revise / park / kill |

Evidence packets remain the audit trail underneath these surfaces.

---

## 8. Implemented Pilot Surface

The current pilot implementation surface is:

| Layer | Current artifact | Purpose |
| --- | --- | --- |
| Packet builder | `scripts/build_strategygroup_runtime_pilot_status.py` | Merge StrategyGroup intake, live-facts readiness, and watcher evidence into Owner-readable pilot status |
| Trading Console API | `GET /api/trading-console/strategygroup-runtime-pilot-status` | Expose `blocked_at`, `blocked_reason`, `next_recover_condition`, `automatic_recovery_action`, `downgrade_mode`, `dual_freshness`, and `gate_failure_ledger` |
| Console page | `/pilot` | Show selected StrategyGroup, selected universe, tiny risk profile, signal state, runtime facts, dual freshness, gate ledger, candidate state, FinalGate / Operation Layer status |

Default pilot selection remains:

```text
MPG-001 unless TEQ-001 has strictly better engineering readiness.
```

Current expected no-signal state is:

```text
status: waiting_for_market
blocked_at: watcher_signal
blocked_reason: no_fresh_strategy_signal
automatic_recovery_action: continue_watcher_observation_and_notify_on_material_change
downgrade_mode: observe_only
```

Progressive facts such as candidate-specific protection, budget, and
next-attempt gate may remain pending before a fresh signal. They must be
resolved before candidate preparation or real submit, but they must not be
reported as the top-level Owner blocker while the system is only waiting for a
market signal.

The pilot status packet must distinguish:

| Field | Meaning | Current no-signal expectation |
| --- | --- | --- |
| `dual_freshness.strategy_signal` | Whether the strategy signal itself is fresh inside the StrategyGroup watcher window | `status: missing` |
| `dual_freshness.action_time_facts` | Whether action-time facts have reached the FinalGate boundary | `status: not_reached_waiting_for_signal` |
| `gate_failure_ledger` | Owner-readable gate ledger for strategy handoff, account facts, signal, RequiredFacts, FinalGate, and Operation Layer | first visible blocker is `strategy_signal: waiting`; `RequiredFacts` may be `progressive_pending` |
