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

## 8. Strategy Control Board State Contract

The Strategy Control Board is the Owner-facing operating surface. Its job is to
translate runtime evidence packets into simple product states, blockers, and
next actions. It must not become a packet browser, research document index, raw
watcher log viewer, manual RequiredFacts assembly tool, or manual signal
freshness judge.

Each visible row represents one selected or available StrategyGroup runtime
unit.

Required StrategyGroup row fields:

| Field | Meaning |
| --- | --- |
| `strategy_group` | StrategyGroup identifier and display name |
| `runtime_state` | Owner-facing state such as `observing` or `blocked` |
| `signal_state` | `no_signal`, `fresh`, `stale`, or `conflict` |
| `required_facts` | `pass`, `missing`, `stale`, or `not_applicable` |
| `risk_profile` | Current bounded risk profile or risk tier |
| `hard_stop` | Current hard-stop status and reason, if any |
| `next_action` | Product action such as `continue`, `prepare_candidate`, or `block` |
| `review_outcome` | Latest lifecycle decision when available |

Owner-facing state contract:

| Owner state | Backend evidence | Owner message | System action |
| --- | --- | --- | --- |
| `not_selected` | No selected StrategyGroup runtime | No StrategyGroup selected | Wait for selection |
| `selected` | StrategyGroup selected but runtime not observing | Selected, not observing yet | Admit or block with reason |
| `observing` | Watcher is healthy and no fresh signal exists | Watching market conditions | Continue watcher cadence |
| `signal_ready` | Fresh signal is present and not stale or conflicted | Fresh signal detected | Check RequiredFacts |
| `blocked` | Missing facts, stale evidence, hard stop, conflict, or safety blocker | Blocked with a short reason | Do not approach funds |
| `candidate_ready` | Candidate, runtime grant, and authorization evidence are ready | Candidate ready for gate checks | Run action-time gate path |
| `finalgate_ready` | Official action-time FinalGate passed | Gate passed | Use official Operation Layer only |
| `submitted` | Operation Layer submitted an auditable action | Action submitted | Finalize and reconcile |
| `reconciling` | Post-submit facts are being checked | Reconciling result | Settle budget and attempt state |
| `settled` | Reconciliation and budget settlement are complete | Attempt settled | Capture review outcome |

Notify the Owner when deployment state changes, watcher health regresses, a
fresh signal appears, a candidate becomes ready, FinalGate blocks or passes,
Operation Layer submits, post-submit reconciliation fails or settles, a hard
stop triggers, or a review outcome is needed.

Stay quiet when all selected runtimes remain observing, all signals are
`no_signal`, the only change is a repeated no-action watcher tick, and no
safety regression exists.

Review results must use:

| Outcome | Meaning |
| --- | --- |
| `promote` | Boundary looks more credible; increase observation priority or admissible scope |
| `keep_observing` | Evidence is insufficient; continue observation |
| `revise` | Change RequiredFacts, freshness, hard stops, conflict policy, or cadence |
| `park` | Current regime is unsuitable; pause or downgrade the StrategyGroup |
| `kill` | Logic is invalid, unreproducible, lookahead-tainted, or risk is uncontrollable |

`promote` must not mean automatic position-size increase. Any risk expansion
must remain bounded and explicit.

---

## 9. Watch Branch Intake Decision

The useful P0 content from `codex/runtime-signal-watcher-feishu` has been
selectively carried into this pilot branch in one of two forms:

| Watch branch content | Pilot branch status |
| --- | --- |
| Feishu watcher notification and readiness packets | carried through watcher readiness / resume-pack code and Tokyo watcher configuration |
| Deployment readiness and deploy apply standing authorization | carried through deploy plan, deploy executor, deploy packets, and tests |
| Post-signal auto-resume metadata | carried through watcher tick and readiness-pack `post_signal_auto_resume` |
| Owner-facing Strategy Control Board contract | folded into this canon overlay and Trading Console pilot page |
| Short current SSOT / AI constraints / Control Board docs | carried into `docs/current/*` as narrow entry files pointing back to this overlay |
| Ready-signal resume dispatch record | carried through `scripts/runtime_signal_watcher_resume_dispatcher.py` and tests |
| Broad docs reset / historical compression | not carried; separate docs-governance integration item |

The watch branch must not be merged wholesale into this pilot branch because
its tree deletes or replaces large parts of `docs/canon`, `docs/ops`, ADRs,
product docs, schemas, and historical evidence. That cleanup can still be done
later as a dedicated docs-governance integration item.

---

## 10. Implemented Pilot Surface

The current pilot implementation surface is:

| Layer | Current artifact | Purpose |
| --- | --- | --- |
| Packet builder | `scripts/build_strategygroup_runtime_pilot_status.py` | Merge StrategyGroup intake, live-facts readiness, and watcher evidence into Owner-readable pilot status |
| Watcher auto-resume decision | `scripts/runtime_signal_watcher_tick.py` field `post_signal_auto_resume` | Translate each watcher tick into waiting / non-executing prepare / action-time FinalGate / hard stop status without placing orders |
| Resume-pack propagation | `scripts/build_runtime_signal_watcher_readiness_pack.py` field `post_signal_auto_resume` | Carry the watcher decision into `post-signal-resume-pack.json` so follow-up automation can resume without reading raw tick packets |
| Trading Console API | `GET /api/trading-console/strategygroup-runtime-pilot-status` | Expose `blocked_at`, `blocked_reason`, `next_recover_condition`, `automatic_recovery_action`, `downgrade_mode`, `dual_freshness`, and `gate_failure_ledger` |
| Console page | `/pilot` | Show selected StrategyGroup, selected universe, tiny risk profile, signal state, runtime facts, auto-resume status, dual freshness, gate ledger, candidate state, FinalGate / Operation Layer status |
| Runtime bridge check | `runtime_bridge` in the pilot status packet | Prove the selected StrategyGroup has a semantics binding and evaluator route before the watcher is treated as valid observation |

Selected useful content from `codex/runtime-signal-watcher-feishu` is allowed
inside this branch only when it preserves this overlay. The Feishu watcher,
deployment readiness, resume-pack, standing authorization, and control-board
translation capabilities are in scope. The watch branch's broad docs deletion /
compression remains a separate docs-governance integration item.

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
| `watcher_scope_alignment` | Whether the active watcher is actually monitoring the selected StrategyGroup universe / side | `status: aligned` or a visible `blocked_runtime_scope_mismatch` |
| `runtime_bridge` | Whether the selected StrategyGroup has runtime semantics binding plus evaluator route | `status: configured`; otherwise visible `blocked_runtime_bridge_missing` |
| `dual_freshness.strategy_signal` | Whether the strategy signal itself is fresh inside the StrategyGroup watcher window | `status: missing` |
| `dual_freshness.action_time_facts` | Whether action-time facts have reached the FinalGate boundary | `status: not_reached_waiting_for_signal` |
| `gate_failure_ledger` | Owner-readable gate ledger for strategy handoff, account facts, signal, RequiredFacts, FinalGate, and Operation Layer | first visible blocker is `strategy_signal: waiting`; `RequiredFacts` may be `progressive_pending` |

If watcher evidence shows active runtimes outside the selected pilot universe /
side and no selected pilot runtime is being monitored, the status must be
`blocked_runtime_scope_mismatch`, not `waiting_for_market`. The automatic
recovery action is to create or attach the selected StrategyGroup runtime and
constrain watcher scope before any auto-prepare setting is enabled.

If the selected StrategyGroup lacks either `StrategyImplementationBinding` or a
configured runtime evaluator route, the status must be
`blocked_runtime_bridge_missing`, not `waiting_for_market`. The recovery action
is to add the semantics binding and evaluator route before creating or attaching
that StrategyGroup runtime.

The watcher tick packet must also expose `post_signal_auto_resume`. This field
must map each tick to one safe automatic recovery action:

| `post_signal_auto_resume.status` | Meaning | Allowed automatic action |
| --- | --- | --- |
| `waiting_for_market` | No fresh signal exists | Continue watcher observation without Owner chat |
| `ready_for_non_executing_prepare` | Fresh signal exists but prepare records are not complete | Continue only to non-executing prepare / shadow planning records |
| `ready_for_fresh_submit_authorization` | Shadow candidate / handoff evidence is ready but fresh submit authorization binding is not complete | Call the official non-executing fresh-submit-authorization binding API |
| `waiting_for_fresh_authorization` | The bridge is parked at fresh authorization binding | Continue the same official non-executing binding recovery |
| `ready_for_action_time_final_gate` | Candidate / prepared authorization evidence exists | Run official action-time FinalGate preflight; do not place an order merely because this status exists |
| `blocked_hard_safety_stop` | Watcher evidence contains forbidden effects | Stop and investigate |

`post_signal_auto_resume` is decision metadata. It must not itself bypass
FinalGate, bypass Operation Layer, call OrderLifecycle, place exchange orders,
mutate runtime budget, or create withdrawal / transfer actions.

Current expected dispatcher liveness after a fresh signal is:

```text
fresh signal
-> non-executing prepare evidence
-> official fresh-submit-authorization binding
-> official action-time FinalGate GET preflight
-> finalgate_ready or blocked with an Owner-readable reason
```

The dispatcher may chain the binding call into the FinalGate GET preflight in a
single `--execute-preflight` run after the official binding API returns a fresh
submit authorization id. This remains a prepare / preflight path only. It must
not call the official submit endpoint or create an exchange order.
