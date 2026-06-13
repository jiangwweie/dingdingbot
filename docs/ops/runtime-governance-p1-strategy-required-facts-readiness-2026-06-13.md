# Runtime Governance P1 Strategy RequiredFacts Readiness - 2026-06-13

## Validation Scope

This document records the P1-B strategy runtime integration readiness guard.
It makes the strategy semantics catalog auditable before any strategy signal is
allowed to become a shadow candidate planning input.

The packet is not execution authority. It does not evaluate strategy alpha,
create a signal evaluation, create a shadow `OrderCandidate`, create an
`ExecutionIntent`, place an order, call `OrderLifecycle`, call exchange writes,
mutate runtime budget, or authorize withdrawals / transfers.

## Source Artifacts

| Source | Role |
|---|---|
| `src/domain/strategy_semantics.py` | Strategy semantics catalog and RequiredFacts contract |
| `src/application/strategy_runtime_fact_overlay_service.py` | Trusted read-only account / position / market fact overlay |
| `src/application/runtime_strategy_signal_planning_service.py` | Non-executing signal-to-shadow-candidate planning gate |
| `src/application/runtime_strategy_signal_scheduler_assembly.py` | Scheduler readiness gate for semantics and trusted fact sources |
| `scripts/build_runtime_strategy_required_facts_readiness_packet.py` | Operator readiness packet builder |
| `tests/unit/test_runtime_strategy_required_facts_readiness_packet.py` | Focused packet contract tests |

## Required Fact Source Contract

| Source key | Required role | Execution authority |
|---|---|---|
| `trusted_account_facts` | Read-only account and reconciliation facts | none |
| `trusted_runtime_boundary` | Runtime grant, budget, leverage, attempt gate | none |
| `trusted_position_projection` | Trusted local active-position projection | none |
| `trusted_market_facts` | Funding, open interest, crowding proxy | none |
| `strategy_market_structure_facts` | Closed candles and price-structure evidence | none |

## Strategy Status Contract

| Packet status | Meaning | Allowed operator action |
|---|---|---|
| `ready_for_non_executing_strategy_runtime_planning` | Candidate-capable strategy has fresh RequiredFacts source coverage | Continue to non-executing planning gates |
| `blocked_strategy_required_facts` | One or more required fact sources are missing, stale, or not read-only | Do not create candidate planning input |
| `blocked_strategy_semantics_missing` | Strategy family/version has no semantics binding | Register or correct semantics first |
| `observe_only_reference_semantics` | Selected strategies are classifier/backlog only | Use as context or backlog, not candidate authority |
| `blocked_forbidden_effect` | Input fact-source report claims an execution side effect | Stop and review side-effect evidence |

## Current Semantics Classification

| Strategy | Current role | Candidate mode |
|---|---|---|
| `CPM-RO-001` / `CPM-001` | Long price-action reference implementation | `shadow_order_candidate_allowed` |
| `BRF-001` | Conservative short-side price-action reference implementation | `shadow_order_candidate_allowed` |
| `BTPC-001` / `LSR-001` / `RBR-001` / `VCB-001` | Reference strategy semantics | `shadow_order_candidate_allowed` |
| `RMR-001` | Regime classifier evidence | `regime_classifier_only` |
| `FCO-001` | Funding / OI / crowding data backlog | `data_backlog_only` |

CPM and BRF remain reference implementations, not proven-alpha claims. RMR is
context evidence only. FCO remains blocked from trading semantics until its
funding / open-interest / crowding fact coverage is complete and fresh.

## Builder Command

```bash
python3 scripts/build_runtime_strategy_required_facts_readiness_packet.py \
  --strategy CPM-RO-001:CPM-RO-001-v0 \
  --strategy BRF-001:BRF-001-v0 \
  --fact-sources-json /tmp/brc-strategy-required-fact-sources.json \
  --output-json /tmp/brc-p1b-strategy-required-facts-readiness-packet.json
```

When fact-source JSON is omitted, the packet intentionally classifies
candidate-capable strategies as blocked by missing RequiredFacts source
coverage.

## Safety Invariants

| Invariant | Required value |
|---|---:|
| `packet_only` | `true` |
| `reads_local_semantics_only` | `true` |
| `reads_optional_json_reports_only` | `true` |
| `api_called_by_builder` | `false` |
| `pg_called_by_builder` | `false` |
| `exchange_called_by_builder` | `false` |
| `exchange_write_called_by_builder` | `false` |
| `order_lifecycle_called_by_builder` | `false` |
| `submit_endpoint_called_by_builder` | `false` |
| `strategy_evaluator_called_by_builder` | `false` |
| `runtime_state_mutated_by_builder` | `false` |
| `withdrawal_or_transfer_created_by_builder` | `false` |

## Operator Conclusion

P1-B now has an explicit pre-candidate checkpoint: strategy semantics must
declare RequiredFacts, and candidate-capable strategies must have fresh trusted
account, runtime-boundary, position, and market-structure facts before entering
non-executing planning. The packet keeps strategy research and runtime
execution separated by making fact coverage visible before any candidate path.
