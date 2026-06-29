# Batch 1085 Evidence - Owner Console Owner State Projection Helper

## Status

`in_progress`

This batch follows the Owner validation direction: preserve the main
StrategyGroup trading lifecycle chain, stop broad production refactor, rebuild
staging from selected paths only, and keep optional evidence out of the default
commit.

## Batch Acceptance

| Field | Value |
| --- | --- |
| closed_engineering_problem | Trading Console still owned repeated hand-written Owner state projection dictionaries for `temporarily_unavailable`, `waiting_for_opportunity`, and `running`, making the Owner readmodel shape harder to verify as a non-authority projection. |
| capability_unlocked | Owner Console owner-state output now has a typed projection helper, so the readmodel shape is centralized while remaining a projection of runtime/Owner state rather than a live-submit or can-trade authority. |
| next_engineering_bottleneck | Merge-ready staging must continue with lean default plus selected evidence only. Do not open broad production refactor unless a current-boundary validation scan finds a concrete regression. |
| files_changed | `src/application/readmodels/owner_projection.py`; `src/application/readmodels/trading_console.py`; `tests/unit/test_trading_console_readmodels.py`; this evidence file; `NEXT_QUEUE.md`; `FINAL_EVIDENCE_PACKET.md` |
| tests_run | `python3 -m pytest tests/unit/test_trading_console_readmodels.py -q` -> `77 passed, 1 skipped`; `git diff --cached --check && git diff --check` -> passed; `python3 -m compileall src scripts tests migrations -q` -> passed; current-boundary scans -> frontend/static `0`, active top-level packet/bridge/verdict scripts `0`, broad residual `19` retained/protected, production/runtime `real_order_authority=true` `0`, reconciliation/config TODO `0`; post-staging `python3 -m pytest tests/unit -q` -> `3124 passed, 1 skipped, 1 warning in 55.70s` |
| why_this_batch_enables_deeper_refactor | It removes a small duplicated Owner readmodel shape from Trading Console without adding a new authority layer, keeping Owner Runtime State as a projection of the main lifecycle instead of another judgment path. |

## Added / Retained / Deleted

| Category | Detail |
| --- | --- |
| added | `OwnerConsoleOwnerStateProjection` and `owner_console_owner_state_projection(...)` in `src/application/readmodels/owner_projection.py`; focused characterization assertions for default and explicit Owner-action projection shapes. |
| retained | Owner Console state remains non-authority readmodel output. `Tradeability Decision` remains the can-trade readmodel; `Runtime Safety State` remains live-submit readiness/safety; `Execution Attempt` remains the lifecycle entry object. |
| deleted_this_batch | Repeated inline Owner state dict literals in `_owner_console_owner_state(...)`. |
| planned_deletion_or_downgrade | Continue only with narrow readmodel/projection glue compression if validation finds duplicated current-boundary shapes. Do not add a broad dashboard schema, packet layer, bridge layer, or compatibility fallback. |
| legacy_fallback_exit_condition | No legacy fallback was added. The only production `automatic_recovery_action` hit remains cleanup-only removal in `owner_projection.py`, not an action authority source. |

## Owner Validation Boundaries

| Boundary | Status |
| --- | --- |
| Signal Observation / Tradeability Decision / Runtime Safety State / Strategy Asset State / Review Outcome State / Execution Attempt | preserved |
| broad production refactor | not opened |
| real index direct commit | avoided; staging uses explicit selected paths only |
| lean default + selected evidence | applied for this batch |
| optional evidence | not staged |
| FinalGate | untouched |
| Operation Layer | untouched |
| RequiredFacts | untouched |
| exchange write / real order | untouched |
| live profile / sizing / secrets | untouched |
| push / deploy | not performed |
| `/Users/jiangwei/Documents/final` | untouched |

## Validation Detail

```text
python3 -m pytest tests/unit/test_trading_console_readmodels.py -q
77 passed, 1 skipped in 7.34s

git diff --check
passed

python3 -m compileall src scripts tests migrations -q
passed

current-boundary scans
broad_residual_count=19
packet_bridge_verdict_top_level_count=0
frontend_static_current_boundary_count=0
production_real_order_authority_true_count=0
reconciliation_config_todo_count=0

python3 -m pytest tests/unit -q
3124 passed, 1 skipped, 1 warning in 55.70s
```

## Staging Rebuild Note

This batch does not reuse a pre-existing broad index. The commit staging set is
explicitly limited to the three touched code/test files plus selected evidence
and closeout pointers. Untracked runtime artifacts and optional historical
evidence remain outside default staging.
