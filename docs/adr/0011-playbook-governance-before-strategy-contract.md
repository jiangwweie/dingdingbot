# ADR-0011 Playbook Governance Before Strategy Contract

## Status

Accepted

Date: 2026-05-25

Runtime effect: none

Trading permission effect: none

## Context

ADR-0008 accepted the Personal Leveraged Campaign business chain and placed
`Human Arm Gate -> Strategy Contract` before trade intent and risk-aware order
building.

The later PLC roadmap review found that this was directionally useful but still
too execution-forward for the current evidence state. The project has no
runtime-eligible strategy candidate. The immediate practical risk is not that a
validated Strategy Contract will be executed unsafely; it is that the Owner may
switch between weak, observe-only, parked, or discretionary playbooks without
stable evidence, cooldown, or decision audit.

Strategy Contract remains the correct object for deterministic entry, exit,
stop, and take-profit mechanics once a strategy is frozen and eligible for a
later stage. It is not the right object for governing the human decision to
switch operating playbooks.

## Decision

Insert a paper-only Playbook Governance layer before Strategy Contract
promotion and execution infrastructure.

The updated conceptual chain is:

`Data Ingestion -> Market State / Feature Builder -> Strategy Detector -> Mode Router -> Playbook Governance -> Human Arm Gate -> Strategy Contract -> Trade Intent -> Risk-Aware Order Builder -> Execution + Order Lifecycle -> Position / Campaign / Profit Protection Control`

Playbook Governance governs:

- which playbooks exist and what evidence state each has;
- when the Owner may switch playbooks;
- what decision evidence must be logged before a switch;
- cooldown and minimum-hold rules;
- hard-lock behavior for loss-response switching, profit-response risk
  escalation, narrative chasing, and parked/rejected playbook resurrection;
- CPV0_2 continuity across playbooks so campaign loss and protection state do
  not reset on switch.

Playbook Governance does not grant:

- runtime authority;
- exchange API authority;
- order placement, cancellation, sizing, leverage, or transfer authority;
- Strategy Contract promotion;
- paper/testnet/tiny-live/live authorization.

## Accepted R0 Direction

The next planning phase is `Playbook Governance R0`.

R0 is paper-only and docs-governance only. It may define registry, schema,
decision log, switching gate, cooldown, review, and CPV0_2 integration
artifacts. It must not implement runtime, connect to exchange APIs, create an
order path, implement strategies, stage/commit/push by default, or wrap
paper-only playbooks as testnet/tiny-live.

Default R0 catalog entries:

- `PB-000-OBSERVE-ONLY` - default safe state, always available.
- `PB-001-DIRECTION-A-PAPER` - pause-fragile observe-only playbook.
- `PB-002-SQ02-DOWNSIDE-PAPER` - docs-only skeleton playbook.
- `PB-003-MANUAL-DISCRETIONARY` - highest-risk discretionary playbook, allowed
  only as a governed paper/manual posture and never as hidden automation.

Default R0 switching constraints:

- loss cluster switch: 48h hard-lock, override requires written rationale and
  additional 24h delay;
- profit response risk increase: 7-day hold plus separate review;
- minimum playbook hold: 14 days;
- narrative chasing: maximum 3 switches per rolling 90 days;
- parked or rejected playbook resurrection: hard-locked until new evidence and
  separate Owner review exist;
- risk-reducing move to `PB-000-OBSERVE-ONLY`: always allowed.

## Consequences

- PLC execution-safety work from Phase 5 remains preserved as evidence, not
  discarded.
- The execution branch of the PLC roadmap is reserved until Playbook Governance
  R0 exists and a strategy later earns promotion.
- Tracks B-E runtime implementation, Phase 5H-8 runtime-oriented work,
  Strategy Contract v2 implementation, and further paper/testnet runtime are
  deferred.
- Docs/schema work for account risk, CPV0_2 continuity, evidence registry, and
  decision logs may continue when it directly supports Playbook Governance R0.
- ADR-0008 remains valid for the downstream execution chain, but this ADR
  amends it by inserting Playbook Governance before Human Arm Gate and Strategy
  Contract work.

## Execution Boundary

This ADR does not authorize runtime profile changes, paper/testnet execution,
exchange-connected work, real account reads, order placement, order
cancellation, transfer, withdrawal, real-funds deployment, LLM/agent autonomous
buy/sell/short/size/leverage decisions, or real live trading.
