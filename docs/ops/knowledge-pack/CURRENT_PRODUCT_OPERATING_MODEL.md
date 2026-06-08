---
title: CURRENT_PRODUCT_OPERATING_MODEL
status: CURRENT_CANON
authority: owner-correction
last_verified: 2026-06-08
source_of_truth:
  - Owner 2026-06-08 direction correction
  - docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md
  - docs/ops/agent-current-brc-baseline.md
  - docs/ops/trading-console-owner-action-flow-v1-deploy-governance-report-2026-06-07.md
  - docs/ops/mr-eth-review-ledger-budgeted-autonomy-v0-design-2026-06-08.md
---

# CURRENT_PRODUCT_OPERATING_MODEL.md

This is the current product and execution-model canon.
It supersedes older wording that treats the project, Trading Console, or Owner
Console as only a read-only dashboard, research dashboard, enum display, or
PG/read-model browser.

---

## 1. Current Product Definition

The current BRC target is an Owner-facing productized bounded-live trading
operations system for fast small-capital trial-and-review Campaigns.

It is not:

- a read-only console;
- a passive status dashboard;
- a research-only signal detector;
- a raw PG/read-model browser;
- a documentation surface;
- a generic uncontrolled trading terminal;
- a strategy self-improvement system.

The console is the Owner's daily operating surface for:

- understanding current system and account state;
- selecting or reviewing `ActionCandidate` records;
- seeing `BudgetEnvelope` availability;
- seeing hard blockers, warnings, and recovery conditions;
- authorizing bounded live actions through the official path;
- checking `FinalGate` results;
- monitoring active position and TP/SL protection;
- pausing or revoking autonomy or budget;
- reviewing completed trades through `Review Ledger`;
- feeding Review outcomes back into promote / revise / park decisions.

Older research-only and read-only documents are historical or scope-limited.
They do not override this current product model.

---

## 2. Current Operating Chain

The current product chain is:

```text
StrategyFamily / Carrier
-> ActionCandidate
-> Owner risk understanding
-> Owner authorization or BudgetEnvelope authorization
-> ActionSpec
-> FinalGate
-> Operation Layer
-> official bounded live action
-> active position / TP/SL protection monitoring
-> close / TP / SL
-> Review Ledger
-> promote / revise / park
```

The execution engine should validate the action spec, scope, budget, account
facts, protection, runtime safety, and auditability. It should not need to know
strategy research internals.

---

## 3. Console Design Rule

Design the console around Owner questions, not backend modules.

Within 5-10 seconds, the Owner should be able to answer:

- Is the system safe right now?
- Is there an active position?
- Is protection complete?
- Is budget available?
- Is autonomy active, waiting, paused, blocked, or actionable?
- What is the next action candidate or required review?
- Why can't the system trade, if blocked?
- What can be safely done now?
- Is Review required?
- Is recovery required?

Bad current-product interpretation:

- panels named only after internal services;
- raw JSON or enum strings as primary UI copy;
- disabled buttons without reasons;
- blocker codes without human explanation;
- strategy IDs without action meaning;
- a status dashboard with no decision path.

Good current-product interpretation:

- summary first;
- clear safety state;
- active position and protection state;
- budget and action-candidate state;
- blocker and recovery explanations;
- review queue;
- clear controls with confirmations when an action is wired.

Do not create fake buttons. If an action is not wired, render it as unavailable
and explain why. If an action is wired, the flow must be scoped, confirmed,
auditable, and routed through the official Operation Layer / FinalGate path.

---

## 4. Admission And Candidate Policy

Admission classifies and explains; it is not primarily an execution blocker.

Use these levels:

| Level | Meaning |
| --- | --- |
| L0 | Archive / rejected / paused / historical only |
| L1 | Candidate that can be displayed and explained |
| L2 | `ActionCandidate` proposal that may not be executable |
| L3 | Owner-confirmed bounded live candidate after Owner confirmation and `FinalGate` |
| L4 | Budgeted autonomy candidate inside explicit `BudgetEnvelope` scope |

Current focus is L1 -> L2 -> L3 and existing budgeted-autonomy foundation work.
Do not overbuild L4 general automation unless explicitly required.

Strategy evidence weakness is usually a warning, not a hard blocker. Missing
authorization, scope mismatch, incorrect symbol/side/quantity/leverage, missing
protection, PG/exchange disagreement, runtime guard blocks, and Operation Layer
or FinalGate bypass attempts are hard blockers.

---

## 5. Execution And FinalGate Policy

Execution must be unified around:

```text
StrategyFamilySpec
-> CarrierSpec
-> ActionCandidate
-> ActionSpec
-> FinalGate
-> Operation Layer
-> official execute
-> protection
-> Review
```

Do not create a custom execution path per strategy.

`ActionSpec` should carry the exact carrier, strategy family, symbol, side,
quantity or notional, max notional, leverage, protection mode, TP/SL or
protection template, max attempts, budget reference, review requirement, risk
disclosure, and evidence references.

`FinalGate` is a hard execution gate, not a research proof gate. It should
verify Owner or BudgetEnvelope authorization, environment, account/subaccount,
symbol, side, quantity/notional, leverage, budget remaining, attempts remaining,
active-position conflict, open-order conflict, fresh account and reconciliation
facts, market rules, protection plan, GKS/runtime guard state, and use of the
Operation Layer.

`FinalGate` should not hard-block merely because strategy evidence is imperfect,
fee/funding/slippage accounting is not perfect, Review analytics are not
sophisticated, the historical sample is not ideal, or admission metadata is
incomplete but not execution-critical. Those are warnings or Review
requirements unless they directly affect live safety.

---

## 6. Review And Recovery Policy

Review is part of the operating loop, not a research appendix.

Every bounded live trial should produce enough Review information to decide:

- promote;
- revise;
- park;
- continue observing.

`Review Ledger` should capture entry and exit facts, symbol, side, notional,
prices, TP/SL outcome, rough PnL where available, holding time, strategy family,
carrier, warnings present at entry, blockers avoided or cleared, and outcome
classification. Missing fee, funding, slippage, or advanced attribution should
be shown as `not_available`, not fabricated and not treated as a live-safety
hard blocker by itself.

Recovery must be visible and actionable in the console. PG/exchange drift,
orphan TP/SL, missing TP, missing SL, protection-without-position,
position-without-protection, failed execute, failed protection placement, stale
account facts, stale reconciliation, external flat, credential blocker,
runtime/server version drift, and migration mismatch must be surfaced with what
is wrong, why it matters, danger level, whether new entry is blocked, retry
availability, clearing condition, Owner-action requirement, and available system
action.

---

## 7. Engineering And Deployment Policy

The current engineering scope is not limited to frontend read-only changes.
When required by a scoped task, Codex may modify frontend UI, frontend
routing/state/query layers, backend APIs, cockpit aggregation read models,
domain models, application services, repositories, PG models, Alembic
migrations, tests, deployment scripts, service wiring, server deployment state,
and operational docs.

Preferred shape:

```text
Backend product-oriented aggregation layer
-> product-oriented response
-> frontend product UI
```

Do not force the frontend to assemble trading state from many raw low-level
APIs.

When a task includes deployment, completion requires inspecting local/server
version drift, preserving server-only changes before overwrite, reconciling
local/server code, applying migrations if required, restarting services if
required, and verifying deployed backend, frontend, and cockpit/action APIs.
If deployment is blocked, record the exact blocker and required Owner action.

---

## 8. Hard Safety Boundaries

Maximum engineering freedom does not remove hard safety boundaries.

Never do:

- withdrawal;
- transfer;
- credential modification or disclosure;
- Operation Layer bypass;
- FinalGate bypass;
- unbudgeted live entry;
- unscoped symbol, side, leverage, or notional expansion;
- infinite retry;
- infinite add-to-position;
- strategy self-elevation;
- hidden live order placement;
- live action from a fake UI affordance.

Fail closed when uncertain about environment, account/subaccount, symbol, side,
quantity, notional, leverage, active position, open orders, protection status,
or PG/exchange consistency.

If PG and exchange facts disagree, block new live entry until reconciled. If an
active position's protection is missing or unknown, block new live entry.

---

## 9. How To Read Older Documents

Documents that say a specific namespace, endpoint set, report, or Gate 2
handoff is read-only may still be accurate for that specific artifact.

They must not be generalized into:

- "Trading Console is only read-only";
- "Owner Console is only a dashboard";
- "no PG mutation is ever allowed";
- "no deployment is allowed";
- "no exchange access is allowed";
- "read-model output is the product boundary".

The current product boundary is bounded live operations through explicit Owner
or BudgetEnvelope authorization, hard `FinalGate`, official Operation Layer,
TP/SL protection, and Review Ledger.
