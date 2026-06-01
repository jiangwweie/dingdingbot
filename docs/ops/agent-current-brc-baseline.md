# Agent Current BRC Baseline

Last updated: 2026-06-01
Status: CURRENT_AGENT_BASELINE

This file is the current agent-facing baseline for Codex, Claude, skills,
handoff templates, and prompt libraries. It overrides older instruction text
that frames the project as research-only, read-only, signal-detection-only, or
permanently barred from execution/testnet paths.

## Project Objective

The project is a BRC fast small-capital live trial system.

It is not:

- a long-term automated profit system;
- a research-only signal detector;
- an infinite readiness gate system;
- a generic uncontrolled trading terminal.

Current core chain:

```text
StrategyFamily
-> Carrier
-> Owner risk acknowledgement
-> BoundedLiveTrialAuthorization
-> hard safety gates
-> entry / protection / record / exit / review
```

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
