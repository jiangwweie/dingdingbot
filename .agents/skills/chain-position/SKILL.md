---
name: chain-position
description: Use when determining how far a live or recent signal progressed, why no Ticket or order appeared, what the first blocker is, or what single action advances real trading safely.
user-invocable: true
---

# Chain Position

## Required Authority

Read before acting:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`
- `docs/current/TRADEABILITY_DECISION_CONTRACT.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`

Use current PostgreSQL and exchange readonly facts. Generated reports and
historical files cannot establish current chain position.

## Chain

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

Find the first transition whose required object or authority is absent,
rejected, stale, occupied, or unresolved.

## Required Output

```text
strategy_group_id:
event_spec_id:
instrument:
position_side:
time_window:
last_proven_stage:
first_blocker:
evidence:
signal_event_id:
capacity_claim_id:
ticket_id:
command_id:
incident_id:
next_action:
stop_condition:
owner_action_required:
```

Use `none` only after checking the authoritative current table or exchange fact.

## Interpretation

| Missing or blocked object | Typical class |
| --- | --- |
| Observation coverage or required Fact | `observation_unavailable` |
| Fresh StrategySignal | `signal_absent` or `signal_invalid_or_stale` |
| Current scope/policy authority | `scope_or_policy_mismatch` |
| CapacityClaim | account mode, lane, domain, budget, or protection blocker |
| Ticket | Claim invalidation or global ENTRY serialization |
| Exchange Command result | rejection, unknown outcome, or runtime Incident |
| Protected lifecycle | protection or reconciliation blocker |
| Settlement/Review | terminal truth or exact economics not yet complete |

## Rules

- Give one first blocker and one next action, not a broad roadmap.
- `waiting_for_opportunity` is valid only after the blocker contract checklist
  proves every non-market prerequisite.
- Arbitration loss or a busy ENTRY lane is normal serialization, not a system
  failure.
- A protected Ticket is not terminal completion.
- Never infer exchange-write authority from replay, fixtures, documents, or
  readonly evidence.
