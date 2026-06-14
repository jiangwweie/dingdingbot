# Strategy Group Handoff Main-Control Intake

Status: INTAKE_IMPLEMENTED_LOCAL
Last updated: 2026-06-14

## Source Anchor

| Field | Value |
| --- | --- |
| Strategy research workspace | `/Users/jiangwei/Documents/final-strategy-research` |
| Strategy research branch | `codex/strategy-research-20260613-goal` |
| Handoff batch commit | `d8a5c5f4` |
| Main-control semantics commit | `05f616b0` |
| Main-control handoff dir | `docs/strategy-research/strategy-group-handoffs/` |

## Intake Scope

The main-control workspace consumes the StrategyGroup handoff batch as a
read-only research handoff. It can power:

1. Strategy Picker display.
2. RequiredFacts readiness matrix.
3. Watcher scope review.
4. Armed-observation intake review.
5. Post-signal resume preparation after a fresh signal appears.

It does not authorize:

1. Runtime registration.
2. Candidate creation.
3. Runtime grant creation.
4. FinalGate input.
5. Operation Layer submit.
6. Exchange writes or real order placement.
7. PG mutation or budget mutation.

## Strategy Group Batch

| Strategy Group | Default Intake Mode | Main-Control Meaning |
| --- | --- | --- |
| `MPG-001` | `armed_observation` | First-batch momentum persistence observation candidate. |
| `TEQ-001` | `armed_observation` | Equity-like perpetual momentum observation candidate. |
| `FBS-001` | `armed_observation` | High-fact-threshold funding / basis stress observer. |
| `SOR-001` | `conditional_armed_observation` | Session-window and branch-specific observer. |
| `PMR-001` | `observe_only` | Precious-metal overlay and short/weakness context observer. |

## Main-Control Implementation

| Artifact | Purpose |
| --- | --- |
| `scripts/build_strategy_group_handoff_intake_packet.py` | Builds a read-only intake packet from handoff JSON files. |
| `GET /api/trading-console/strategy-group-handoff-intake` | Exposes the intake packet to Owner Console. |
| `trading-console/src/pages/StrategyGroupIntake.tsx` | Displays Strategy Picker intake, watcher scope, and RequiredFacts preview. |
| `tests/unit/test_strategy_group_handoff_intake_packet.py` | Verifies packet builder safety and readiness semantics. |
| `tests/unit/test_trading_console_readmodels.py` | Verifies the Console read-model envelope and no-action guarantee. |

## Runtime Boundary

The intake packet has explicit safety invariants:

```text
registers_runtime: false
creates_candidate: false
authorizes_execution: false
places_order: false
mutates_pg: false
```

Fresh signal handling remains blocked until main-control validates:

1. Exchange symbol rules.
2. Same-symbol active position and open order absence.
3. Market and derivatives fact freshness.
4. Protection plan presence.
5. Conflict policy.
6. Runtime grant and authorization evidence.
7. Action-time FinalGate.
8. Official Operation Layer path.

## Next Control Surface

The next main-control step is to use the intake packet as input for:

1. Exchange symbol availability / rules validation.
2. RequiredFacts readiness packet generation from trusted live facts.
3. Watcher scope wiring for selected strategy groups.
4. Fresh-signal resume to non-executing candidate preparation.
