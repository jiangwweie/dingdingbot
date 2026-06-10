# Strategy Signal Shadow Candidate Planning v1 Acceptance - 2026-06-10

Status: ACCEPTED_NON_EXECUTING

This record accepts the Strategy Signal -> Shadow Candidate Planning v1 stage
on the current runtime-governance release branch. It is a non-executing
acceptance only. It does not authorize real runtime submit, an executable
`ExecutionIntent`, local order registration, `OrderLifecycle`, exchange order
placement, withdrawals, transfers, or live runtime profile changes.

## Scope

Accepted:

- `RuntimeStrategySignalEvaluationService` is wired into the runtime strategy
  signal path for the current reference strategy set.
- CPM / BRF evaluator output must pass the semantics gate before any shadow
  candidate can be created.
- `READY_FOR_SEMANTIC_BINDING` can create only shadow `SignalEvaluation` and
  shadow `OrderCandidate` records through the B0 planning path.
- Candidate planning produces non-executing proposal facts:
  - entry price reference;
  - CPM long structure stop from pullback low or ATR fallback;
  - BRF short structure stop from rally high or ATR fallback;
  - notional / leverage / margin / max-loss preview;
  - TP1 1R partial plus runner/trailing metadata.
- Trusted account facts and trusted active-position facts are required before
  candidate creation. Missing trusted facts block planning before shadow records
  are created.
- RMR and FCO do not create trading candidates in this stage.
- Runtime-bounded automatic-attempt semantics are preserved as metadata and
  boundary checks, but no order submit path is enabled.

Not accepted / still forbidden:

- No real exchange order.
- No executable `ExecutionIntent` submit.
- No `OrderLifecycle` adapter call.
- No local order registration.
- No strategy self-authorization.
- No claim that CPM / BRF are proven-alpha production strategies.
- No frontend-only "ready" state without backend semantics.

## Code Evidence

Current branch:

```text
release/tokyo-runtime-governance-20260610
```

Current code identity:

```text
verify with: git rev-parse HEAD
```

Relevant implementation evidence:

- `src/application/runtime_strategy_signal_evaluation_service.py`
  - routes raw `StrategyFamilySignalInput` through pure evaluators;
  - blocks missing semantics binding, unsupported candidate mode, invalid
    evaluator output, side mismatches, and non-`WOULD_ENTER` signals;
  - never creates `SignalEvaluation`, `OrderCandidate`, `ExecutionIntent`,
    orders, `OrderLifecycle` calls, or exchange calls.
- `src/application/runtime_strategy_signal_planning_service.py`
  - evaluates raw signal input first;
  - requires `READY_FOR_SEMANTIC_BINDING`;
  - applies trusted runtime fact overlay;
  - checks RequiredFacts before shadow candidate creation;
  - builds entry / stop / TP1 / runner / notional / leverage / max-loss
    proposal;
  - creates only shadow `SignalEvaluation` and shadow `OrderCandidate`;
  - returns `execution_intent_created=false`, `order_created=false`,
    `order_lifecycle_called=false`, and `exchange_called=false`.
- `tests/unit/test_b0_runtime_strategy_signal_planning.py`
  - proves CPM long creates a shadow candidate with pullback-low stop,
    notional/leverage/margin/max-loss proposal, TP1 1R partial, and runner
    metadata;
  - proves BRF short creates a shadow candidate with rally-high stop and
    runner metadata;
  - proves CPM short-side mismatch, RMR/FCO non-trading modes, missing trusted
    account facts, and missing trusted active-position projection all block
    before shadow records are created.
- `src/application/strategy_semantics_shadow_binding_service.py`
  - creates the shadow records only after B0 strategy semantics checks pass;
  - preserves `not_order=true` and `not_execution_intent=true`.
- `src/application/runtime_strategy_signal_scheduler_planning_service.py`
  and `src/application/runtime_strategy_signal_scheduler_assembly.py`
  - keep scheduler handoff explicit and non-executing;
  - require readiness plus `allow_shadow_candidate_creation=true`.
- `src/interfaces/api_trading_console.py`
  - exposes the operator-auth non-executing shadow-plan surface;
  - does not expose a submit or order placement action for this stage.

## Test Evidence

Focused test command:

```bash
/opt/homebrew/bin/pytest -q \
  tests/unit/test_b0_runtime_strategy_signal_planning.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_reference_price_action_evaluators.py \
  tests/unit/test_brf_price_action_evaluator.py \
  tests/unit/test_strategy_candidate_semantics.py \
  tests/unit/test_b0_strategy_runtime_fact_overlay.py \
  tests/unit/test_b0_runtime_strategy_signal_scheduler_assembly.py \
  tests/unit/test_strategy_observation_shadow_planning_rehearsal.py
```

Result:

```text
49 passed
```

Local rehearsal command:

```bash
/opt/homebrew/bin/python3 scripts/verify_strategy_observation_shadow_planning_rehearsal.py --json
```

Result:

```text
status=rehearsal_passed
rehearsal_passed=true
database_connected=false
exchange_called=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
owner_bounded_execution_called=false
withdrawal_or_transfer_created=false
```

## Acceptance Notes

The strategy branch `codex/strategy-p1-p3-candidate-pack-v1` is an ancestor of
the current release branch, as are `codex/strategy-runtime-semantics-free-trading`
and `codex/sprint6-console-runtime-integration`. Therefore this acceptance is
based on integrated tracked code, not unmerged branch state.

The current deployed Tokyo backend is `1734b8cc`, which includes the
non-executing shadow planning code. This document commit may be newer than the
deployed service. A docs-only acceptance commit should not trigger a deploy
chase by itself.

## Remaining Gates

Before controlled runtime execution or real OrderLifecycle integration:

- Owner/Codex must confirm runtime profile values for any first real submit.
- BRF short-side profile must remain conservative and explicitly confirmed.
- First-real-submit gate must confirm attempt consumption, reservation/release,
  duplicate-submit blocking, protection failure behavior, active-position facts,
  account facts, stale-fact behavior, and deployment readiness.
- Real submit still requires separate explicit Owner authorization.
