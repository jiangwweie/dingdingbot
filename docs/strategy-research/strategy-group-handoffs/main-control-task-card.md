# Main-Control Task Card: StrategyGroup Handoff Batch

Status: READY_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-16

## Goal

Review and consume the current Strategy Research v3 StrategyGroup handoff batch
as main-control inputs for Strategy Picker, observable runtime admission,
watcher scope, RequiredFacts readiness, and observe-only signal review.

## Why

Owner wants strategy research to become practical strategy-group candidates
without making the research window responsible for FinalGate, Operation Layer,
real execution, settlement, or Console implementation.

This batch converts twelve research candidates into stable handoff contracts.
The original armed-observation / observe-only group contains:

1. `MPG-001`
2. `FBS-001`
3. `TEQ-001`
4. `PMR-001`
5. `SOR-001`

The added observe-only handoff drafts contain:

1. `VCB-001`
2. `RSR-001`
3. `NLPD-001`
4. `DMI-001`
5. `SCF-001`
6. `MASS-001`
7. `UO-001`

## Inputs

| Artifact | Purpose |
| --- | --- |
| `strategy-group-handoffs/main-control-handoff-index.md` | Entry point and batch summary. |
| `strategy-group-handoffs/handoff-validation-report.md` | Validation result and boundary proof. |
| `strategy-group-handoffs/*/handoff.md` | Human-readable strategy-group semantics. |
| `strategy-group-handoffs/*/handoff.json` | System-readable StrategyGroup handoff contract. |
| `scripts/validate_strategy_group_handoffs.py` | Reproducible validation script. |
| `tests/unit/test_strategy_group_handoff_validator.py` | Focused validator tests. |

## Main-Control Responsibilities

1. Decide whether each strategy group enters the Strategy Picker as a candidate.
2. Map `supported_symbols` to current exchange availability and exchange rules.
3. Map `required_facts` to runtime readiness checks.
4. Decide observe-only versus armed-observation mode.
5. Connect sample packets to watcher and candidate-preparation semantics.
6. Keep FinalGate, Operation Layer, budget, settlement, and review boundaries in
   the main-control window.

## StrategyGroup Batch

| Strategy Group | Default Mode | Main-Control Handling |
| --- | --- | --- |
| `MPG-001` | `armed_observation` | Admit as momentum-persistence observer; 5x disabled and 3x stress-only. |
| `FBS-001` | `armed_observation` | Admit as derivatives stress observer plus TEQ negative-funding long candidate. |
| `TEQ-001` | `armed_observation` | Admit as long-side equity-like momentum observer with concentration and session facts required. |
| `PMR-001` | `observe_only` | Start as PMR short/overlay observer; upgrade only when session/mark facts are present. |
| `SOR-001` | `armed_observation` | Admit branch-by-branch; do not treat as broad opening-range alpha. |
| `VCB-001` | `observe_only` | Start as volume-compression breakout observer; true/false breakout labels remain research targets, not runtime facts. |
| `RSR-001` | `observe_only` | Start as relative-strength scorer; use as TEQ support context, not standalone execution logic. |
| `NLPD-001` | `observe_only` | Start as low-history listing/event observer; block executable activation until cohort and product-risk facts improve. |
| `DMI-001` | `observe_only` | Start as ADX / DMI directional-ignition observer; narrow long-side equity/ETF role only. |
| `SCF-001` | `observe_only` | Start as session-confluence observer; use as structure-confirmed TEQ momentum support. |
| `MASS-001` | `observe_only` | Start as range-expansion reversal observer; require bulge-and-reversal confirmation before candidate preparation. |
| `UO-001` | `observe_only` | Start as Ultimate Oscillator bullish-divergence observer; generic UO, midline persistence, and short-side branches are blocked. |

## Hard Stop For Main-Control Review

Stop review if any handoff is interpreted as:

1. Real order authorization.
2. Runtime registration by the research window.
3. FinalGate input.
4. Operation Layer request.
5. Exchange write.
6. Deploy request.
7. Live profile mutation.
8. Credential or order-sizing default mutation.

## Verification

Run:

```bash
python3 scripts/validate_strategy_group_handoffs.py --markdown
/opt/homebrew/bin/pytest tests/unit/test_strategy_group_handoff_validator.py -q
git diff -- src/application/order_lifecycle_service.py src/application/execution_orchestrator.py src/application/position_projection_service.py src/application/capital_protection.py src/infrastructure/exchange_gateway.py src/application/reconciliation.py src/application/startup_reconciliation_service.py
```

Expected result:

```text
Validated handoffs: 12
Passed: 12
Failed: 0
8 passed
core execution-chain diff is empty
```

## Done When

Main-control has enough information to:

1. Show the current strategy groups as Owner-selectable or observe-only
   candidates.
2. Start observe-only or armed-observation flows without asking Owner to write
   market analysis manually.
3. Prepare candidate packets only from fresh signal packets.
4. Preserve official FinalGate and Operation Layer boundaries for any later
   execution path.
