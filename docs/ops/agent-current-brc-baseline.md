# Agent Current BRC Baseline

Last updated: 2026-06-08
Status: CURRENT_AGENT_BASELINE

This file is the current agent-facing baseline for Codex, Claude, skills,
handoff templates, and prompt libraries. It overrides older instruction text
that frames the project as research-only, read-only, signal-detection-only, a
passive dashboard, or permanently barred from execution/testnet paths.

Primary product-model canon:

- `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`

## Project Objective

The project is a BRC productized bounded-live operations system for fast
small-capital trial-and-review Campaigns.

It is not:

- a long-term automated profit system;
- a research-only signal detector;
- a read-only console;
- a PG/read-model browser;
- a passive status dashboard;
- an infinite readiness gate system;
- a generic uncontrolled trading terminal.

Current core chain:

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

Trading Console / Owner Console must be interpreted as the Owner's operating
surface for state understanding, ActionCandidate review, budget availability,
blockers/recovery, bounded authorization, FinalGate evidence, active
position/protection monitoring, pause/revoke controls, completed-trade review,
and Review Ledger learning. Read-only documents are scope-limited to the
specific endpoint set, report, or handoff they describe; they do not define the
whole product as read-only.

## Authorization Boundary

Real live trading and real-funds order placement require separate explicit
Owner authorization.

The following work does not require additional Owner authorization merely
because it touches controlled execution-readiness surfaces:

- code changes;
- tests;
- API / console updates;
- PG non-live changes;
- testnet readiness;
- testnet runtime checks;
- testnet controlled rehearsal;
- testnet order rehearsal;
- testnet/dev/profile-scoped cleanup, reset, or repair;
- architecture governance.

This does not authorize live orders, real-funds orders, withdrawals, transfers,
credential changes, or bypasses around the Operation Layer.

## Gate Behavior

Classify blockers before stopping:

| Blocker scope | Required behavior |
| --- | --- |
| live / real-funds | hard stop unless separate explicit Owner authorization exists |
| testnet / dev / profile-scoped | inspect scope, safely repair/reset/cleanup where bounded, then continue |
| unknown unsafe | investigate; block only if safety cannot be established |
| strategy evidence weakness | disclose as warning/evidence; do not hard-block after Owner acknowledgement |
| incomplete observation | disclose as warning/evidence; do not hard-block after Owner acknowledgement |
| UI/report incompleteness | fix or record as acceptance gap; do not treat as execution safety blocker |

## Hard Blockers

These remain hard blockers:

- missing explicit live authorization for real live trading or real-funds order;
- symbol / side / cap mismatch;
- profile / environment mismatch;
- protection impossible;
- exit / cleanup impossible;
- conflicting position / open order;
- GKS blocked;
- order / result logging unavailable;
- credential or secret safety issue;
- withdrawal / transfer request;
- Operation Layer bypass;
- strategy self-elevation.

## Strategy Warnings

These are warnings that require disclosure and Owner acknowledgement, but do
not hard-block after acknowledgement:

- evidence weak;
- forward review incomplete;
- observation sample low;
- regime uncertain;
- historical fragility.

## Execution Model

Execution work should converge on:

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

Do not create custom execution paths per strategy. `FinalGate` is a hard
execution gate, not a research-proof gate. It should verify exact
authorization, environment/account/symbol/side/quantity/notional/leverage,
budget, attempts, exposure conflicts, fresh account and reconciliation facts,
market rules, protection plan, GKS/runtime guard state, and Operation Layer
use. Imperfect evidence, incomplete fee/funding/slippage accounting, or
unsophisticated Review analytics are warnings unless they directly affect live
safety.

## Worker Output Rule

Codex and Claude worker outputs should report facts and final state. They
should not recommend the next task; the project controller decides sequencing.

Required worker closure shape:

- goal;
- what changed;
- files changed;
- tests / validation;
- final state;
- hard blockers, if any;
- safety proof.

Do not include sections named "Next recommended task", "Recommended next step",
or "What should we do next" in reusable task templates or worker return
formats.
