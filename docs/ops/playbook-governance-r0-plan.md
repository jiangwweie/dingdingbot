# Playbook Governance R0 Plan

Date: 2026-05-25
Status: ACCEPTED_WITH_AMENDMENTS / PAPER_ONLY

## Role

This document records the accepted planning direction after the PLC roadmap
review: insert Playbook Governance before Strategy Contract implementation.

It is a planning artifact. It is not a runtime spec, trading permission,
Strategy Contract promotion, playbook activation, paper/testnet authorization,
or real-live authorization.

## Accepted Verdict

Owner verdict:

`ACCEPT_PLAYBOOK_GOVERNANCE_R0_WITH_AMENDMENTS`

Meaning:

- accept Playbook Governance R0 as the next PLC planning phase;
- keep it paper-only and docs-governance only;
- insert Playbook Governance before Human Arm Gate and Strategy Contract
  execution infrastructure;
- preserve Phase 5 execution-safety evidence, but move the execution branch to
  reserved/deferred status;
- keep real live blocked.

## Updated Layering

The updated conceptual chain is:

`Data Ingestion -> Market State / Feature Builder -> Strategy Detector -> Mode Router -> Playbook Governance -> Human Arm Gate -> Strategy Contract -> Trade Intent -> Risk-Aware Order Builder -> Execution + Order Lifecycle -> Position / Campaign / Profit Protection Control`

Playbook Governance is not a Strategy Contract replacement.

- Playbook Governance governs the human decision to operate, switch, pause, or
  remain in observe-only mode.
- Strategy Contract governs deterministic trading mechanics only after a
  strategy is frozen, reviewed, and explicitly promoted to a later stage.

## Why R0 Comes Next

Current evidence does not support a runtime-eligible strategy candidate. The
highest current risk is therefore not unsafe execution of a validated strategy.
The highest current risk is ungoverned human switching among weak, parked,
observe-only, or discretionary playbooks.

R0 addresses that risk without runtime work.

## R0 Scope

Allowed:

- playbook registry planning;
- playbook entry schema planning;
- playbook switch decision log schema planning;
- switching gate rules;
- cooldown and review rules;
- CPV0_2 continuity rules across playbooks;
- dry-run review of current posture.

Forbidden:

- exchange API connection;
- runtime implementation;
- order path;
- strategy implementation;
- position, leverage, sizing, or order advice;
- paper/testnet/tiny-live/live wrapping of playbook work;
- parked strategy resurrection without new evidence and Owner review;
- commit/push unless separately requested.

## R0 Deliverables

R0 should create these docs/schema artifacts in later implementation work:

1. `docs/governance/playbook-registry-v0.md`
2. `docs/schemas/playbook/playbook_entry.schema.json`
3. `docs/governance/decision-log-spec-v0.md`
4. `docs/schemas/playbook/playbook_switch_decision.schema.json`
5. `docs/governance/switching-gate-rules-v0.md`
6. `docs/governance/campaign-guard-playbook-integration-v0.md`
7. `docs/governance/review-cooldown-governance-v0.md`
8. `docs/governance/playbook-governance-r0-dry-run.md`

The sprint report proposed six grouped deliverables; this plan keeps the same
scope but splits schemas from prose docs so validation assets are explicit.

## Initial Playbook Catalog

| ID | Status | Role | Notes |
| --- | --- | --- | --- |
| `PB-000-OBSERVE-ONLY` | DEFAULT_SAFE_STATE | No-order observation posture. | Always available; risk-reducing fallback. |
| `PB-001-DIRECTION-A-PAPER` | PAUSE_FRAGILE_OBSERVE_ONLY | Direction A paper/observation playbook. | No runtime, no paper account, no testnet. |
| `PB-002-SQ02-DOWNSIDE-PAPER` | DOCS_ONLY_SKELETON | SQ02 docs-only playbook. | No scanner, alert, runtime, paper, or testnet. |
| `PB-003-MANUAL-DISCRETIONARY` | HIGH_RISK_GOVERNED_MANUAL | Manual discretionary posture under campaign guard. | Highest-risk entry; never hidden automation. |

`PB-000-OBSERVE-ONLY` is not a normal strategy playbook. It is the safe default
state and the fallback when governance checks fail.

## Default Switching Rules

| Rule ID | Rule | Default |
| --- | --- | --- |
| `PG-LOSS-001` | After a loss cluster, no playbook switch. | 48h hard-lock; override requires rationale plus 24h delay. |
| `PG-PROFIT-001` | Profit-response risk increase requires review. | 7-day hold plus separate review. |
| `PG-HOLD-001` | Minimum playbook hold before switching. | 14 days. |
| `PG-NARRATIVE-001` | Narrative chasing switch frequency cap. | Max 3 switches per rolling 90 days. |
| `PG-EVIDENCE-001` | Every non-risk-reducing switch needs evidence refs. | Empty refs fail review. |
| `PG-PARKED-001` | Parked/rejected playbook resurrection. | Hard-locked until new evidence plus Owner review. |
| `PG-SAFE-001` | Risk-reducing move to observe-only. | Always allowed. |

## Required Decision Log Fields

R0 decision logs must be append-only and include at least:

- `switch_id`;
- `previous_playbook_id`;
- `new_playbook_id`;
- `switched_at_ms`;
- `decided_by`;
- `reason_category`;
- `reason_text`;
- `campaign_pnl_at_switch`;
- `days_since_last_switch`;
- `consecutive_loss_count`;
- `review_status`;
- `evidence_refs`;
- `risk_change_direction`;
- `cooldown_override_used`;
- `cooldown_override_reason`;
- `cpv0_2_state`;
- `playbook_hold_days`;
- `next_review_at_ms`.

## CPV0_2 Continuity

CPV0_2 is the campaign account-protection envelope for all playbooks.

Invariants:

- playbook switch does not reset campaign PnL;
- playbook switch does not reset loss count or loss-lock state;
- playbook switch during `profit_protecting` is blocked until close/review;
- playbook switch during `loss_locked` or `hard_locked` is blocked;
- missing protection or invariant breach remains campaign-level, not
  playbook-local;
- new playbook without a Strategy Contract remains observe-only.

## Deferred Work

Deferred:

- Track B account risk runtime implementation;
- Track C multi-symbol runtime foundation implementation;
- Track D Strategy Contract promotion implementation;
- Track E runtime evidence implementation;
- Phase 5H through Phase 8 runtime-oriented roadmap;
- Strategy Contract v2 implementation;
- LifecycleStrategy / ExitMonitor runtime;
- paper/testnet runtime for playbooks.

Not deferred:

- docs/schema work needed for Playbook Governance R0;
- CPV0_2 continuity rules;
- research evidence registry links;
- decision log and cooldown governance;
- current campaign state-machine evidence as governance backbone.

## Immediate Next Task

Next task:

`PLC-PG-R0-001 - Playbook Registry and Switch Decision Log schema`

Owner/Codex scope:

- create `docs/governance/playbook-registry-v0.md`;
- create `docs/schemas/playbook/playbook_entry.schema.json`;
- create `docs/governance/decision-log-spec-v0.md`;
- create `docs/schemas/playbook/playbook_switch_decision.schema.json`;
- no runtime, no exchange, no order path, no strategy implementation.

Claude can receive a bounded task card only after Codex freezes allowed files,
schema requirements, and validation expectations.
