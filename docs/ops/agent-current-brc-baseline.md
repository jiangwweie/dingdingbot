# Agent Current BRC Baseline

Last updated: 2026-06-12
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

Owner authorization as of 2026-06-12 permits real live trading and real-funds
order placement by default when the action goes through the official auditable
BRC runtime / Operation Layer path and current action-time gates pass.

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

This does not authorize withdrawals, transfers, credential changes, Operation
Layer bypasses, unauditable exchange writes, stale-fact execution, missing
protection, duplicate-submit risk, or runtime-boundary expansion.

## Gate Behavior

Classify blockers before stopping:

| Blocker scope | Required behavior |
| --- | --- |
| live / real-funds | proceed through auditable runtime / Operation Layer path when current action-time gates pass; stop on unauditable or uncontrolled execution |
| testnet / dev / profile-scoped | inspect scope, safely repair/reset/cleanup where bounded, then continue |
| unknown unsafe | investigate; block only if safety cannot be established |
| strategy evidence weakness | disclose as warning/evidence; do not hard-block after Owner acknowledgement |
| incomplete observation | disclose as warning/evidence; do not hard-block after Owner acknowledgement |
| UI/report incompleteness | fix or record as acceptance gap; do not treat as execution safety blocker |

## Hard Blockers

These remain hard blockers:

- missing auditable action evidence for real live trading or real-funds order;
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

These are warnings that require disclosure, but do not hard-block when the
auditable runtime boundary and action-time gates pass:

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

## Runtime Loop Correction

After a runtime authorization has a persisted
`RuntimeExecutionExchangeSubmitExecutionResult`, that authorization is
`consumed` / `replay-only` / `reviewable`. It must not be pushed back through
pre-submit rehearsal, local `CREATED` order checks, local order re-creation, or
another submit attempt.

Post-submit facts must move through a runtime-level finalize loop:

```text
ExchangeSubmitExecutionResult
-> SubmitOutcomeReview
-> AttemptOutcomePolicy
-> PostSubmitBudgetSettlement
-> reconciliation refresh
-> current position / protection status
-> closed-review requirement, if any
-> NextAttemptGate
```

New attempts must start from a new strategy signal chain:

```text
StrategySignal
-> SignalEvaluation
-> OrderCandidate
-> ExecutionIntent
-> fresh authorization / runtime grant evidence
```

Do not manually move evidence IDs as the default path. Services should resolve
durable evidence from runtime, authorization, order, and execution-result facts
where possible. Manual evidence input is an exception for audit/recovery, not
the normal runtime loop.

True live-safety risks in this stage are:

- reusing a consumed authorization and creating duplicate submit risk;
- failing to finalize post-submit state, causing inaccurate attempt or budget
  accounting;
- treating canceled/missing protection as safe without current exchange and
  local reconciliation evidence;
- allowing active-position facts to diverge from exchange/order facts.

The following are not live-safety blockers by themselves after a real submit
has already happened:

- missing manually supplied `runtime_submit_rehearsal_id`;
- local orders no longer being `CREATED`;
- existing `exchange_order_id` on local orders;
- strategy alpha being unproven after Owner acknowledged the experimental
  right-tail risk-capital objective.

## Execution-Chain Engineering Cadence

Execution-chain work must pass local node-level tests and a local dry-run flow
before Tokyo integration. Tokyo is for deployment, integration, live account /
order / position fact validation, and explicitly gated real exchange actions.
Tokyo must not be used as the first-pass debugging environment for a new
domain or application node.

Each execution-chain stage should produce artifacts in this order:

| Stage | Required artifact |
| --- | --- |
| Domain | model / policy / packet unit test |
| Application | service result test with fake repositories or fake gateway |
| API / script | local dry-run JSON response or report |
| Tokyo | integration probe or live-fact report path |
| Git | stage commit hash with path, branch, and deployment status |

This cadence is not a new readiness gate for its own sake. It is the default
way to keep small live-capital progress fast, auditable, and recoverable
without mixing code bugs, stale PG facts, consumed authorizations, and real
exchange state in one server-side debugging loop.

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
