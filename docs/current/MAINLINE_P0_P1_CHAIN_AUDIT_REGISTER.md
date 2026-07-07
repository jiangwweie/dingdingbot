# Mainline P0/P1 Chain Audit Register

Last updated: 2026-07-07

## Purpose

This document records current **P0/P1 mainline chain findings** and their
verification evidence. It is not a runtime source, not a trading authority, and
not an Owner operation surface.

The runtime source remains **PG current state**:

```text
live_signal_event
-> promotion_candidate
-> action_time_lane_input
-> Action-Time Ticket
-> FinalGate
-> Operation Layer
-> Runtime Safety State
-> ticket-bound protected submit
-> post-submit closure
```

## Current Audit Result

### Known Objective Facts

| Item | Current evidence | Meaning |
| --- | --- | --- |
| **Active StrategyGroup scope** | `tests/unit/test_action_time_full_chain_impact.py` covers 22 active `StrategyGroup + symbol + side` rows | The current multi-strategy, multi-symbol, strategy-owned side scope is test-covered |
| **Raw-input local chain** | `test_each_active_candidate_scope_reaches_disabled_smoke_from_raw_pg_input` | Constructed PG signal input can reach non-executing protected submit |
| **Mock real-submit chain** | `test_each_active_candidate_scope_reaches_mock_real_submit_and_closure_from_raw_pg_input` | Constructed PG signal input can reach `submitted` and post-submit closure with a mock exchange result |
| **Tokyo runtime observation** | 2026-07-07 Tokyo PG showed `BRF2-001 / AVAXUSDT / short` reached `live_submit_ready` and `disabled_smoke_passed` | Production server can detect a real fresh signal and push it to the submit boundary without exchange write |
| **Tokyo deployed head** | `99d7055c0fb54b9c1bed078fe6a7d44e72c42622` deployed to `brc-runtime-governance-99d7055c-stale-action-time-monitor-fix`; postdeploy acceptance passed | The stale action-time monitor blocker fix is now active on Tokyo |
| **Postdeploy current monitor** | Latest PG monitor run after deploy is `quiet`, `blocker_classes=["none"]`; 22 readiness rows are `market_wait_validated` | `action_time_boundary_not_reproduced` is no longer the current blocker after expired/closed signals |
| **File authority strict audit** | `validate_no_runtime_file_authority.py` and `audit_production_runtime_file_io.py --max-frequent-report-write 0` | Production current chain is not using repo/output/report JSON or Markdown as runtime authority |
| **L2-L7 invariant scan** | `test_l2_l7_mainline_chain_invariants.py` | API signatures, materializer CLI surfaces, production systemd file authority, watcher scope, dispatcher identity, refresh sequence order, and no-trigger `action_time_if_needed` cadence now fail if legacy loose identity, file authority, or heavy no-signal work returns |

### Current Open / Closed Findings

| Severity | Finding | Status | Evidence | Next action |
| --- | --- | --- | --- | --- |
| **P0** | Required action-time post-step can fail without enough stdout context | **closed and deployed** | `run_server_product_state_refresh_sequence.py` now emits `blocked_required_stdout_tail` and `blocked_required_stderr_tail`; deployed in `99d7055c` | Keep in focused refresh-sequence tests |
| **P0** | Local constructed chain did not prove all active scopes can pass mock real-submit and post-submit closure | **closed and deployed** | 22 active scopes now pass through mock `real_gateway_action -> submitted -> reconciliation_pending`; deployed in `99d7055c` | Keep in full action-time impact suite |
| **P1** | Server Monitor could reuse a stale `action_time_boundary_not_reproduced` readiness blocker after the fresh signal expired | **closed and deployed** | Candidate Pool now treats action-time-only blockers as current only when a fresh PG signal exists; Tokyo monitor after deploy reports `blocker_classes=["none"]` | Continue observing normal timer ticks |
| **P1** | Unsupported side raw signal could theoretically pollute the chain if only seed shape was tested | **closed locally** | `test_raw_pg_input_for_unsupported_side_is_rejected_before_signal_creation` constructs unsupported `StrategyGroup + symbol + side` raw signal and proves no signal, promotion, lane, or ticket is created | Include in impact suite before next deploy |
| **P1** | P0/P1 issues were too dependent on after-the-fact code review rather than a single active chain invariant gate | **closed locally** | `test_l2_l7_mainline_chain_invariants.py` checks ticket-bound API signatures, PG-only materializer CLI surfaces, production systemd file authority, action-time refresh state order, no-trigger cadence, non-submit production watcher systemd, and PG-ticket dispatcher identity | Keep in deploy-prep focused suite |
| **P1** | Server periodic watcher is intentionally non-authority and currently stops at `disabled_smoke` / preflight paths unless submit execution is separately armed | **open by design** | systemd dispatcher drop-in has `--execute-preflight` and does not include `--execute-operation-layer-submit` | Decide controlled production submit arming separately; do not hide it as market wait |
| **P1** | Real gateway action path is API-bound, not direct sequence-runner-bound | **open by design** | `materialize_ticket_bound_protected_submit_attempt.py` prepares `submit_prepared`; API layer performs gateway call and records result | Keep tests proving mock result identity; only official API path may perform real gateway call |

### Newly Registered Consumer Matrix Findings

| Severity | Finding | Current impact | Evidence | Required direction |
| --- | --- | --- | --- | --- |
| **P1** | Owner Console / publisher / server monitor current projections imported read-model builders from `scripts/` | **closed locally**: Owner Console reads `brc_control_read_model_snapshots`; Candidate Pool, Daily Table, and Goal Status builder ownership moved to `src/application/readmodels`; `scripts/build_*` are thin CLI wrappers | `src/application/readmodels/trading_console.py` reads PG current snapshots; `src/application/readmodels/{strategy_live_candidate_pool,daily_live_enablement_table,strategygroup_runtime_goal_status}.py` own builder logic; `test_pg_current_projectors_use_application_readmodel_builders_not_script_builders` guards publisher/monitor imports | Keep deleting or archiving remaining legacy artifact CLIs after their useful semantics are migrated |
| **P1** | API observation cycle imported `build_runtime_strategy_signal_input_artifact.py` | **closed locally**: API now uses typed signal-input helpers from `src/application/readmodels/runtime_strategy_signal_input.py`; the script is a thin CLI wrapper only | `src/interfaces/api_trading_console.py` imports `runtime_strategy_signal_input`; `test_api_observation_cycle_uses_application_signal_input_helper_not_script` guards the boundary | Continue removing legacy `signal_input_json` report references from watcher/pilot diagnostics separately |
| **P1** | Owner Console status views imported live-facts readiness and runtime pilot status builders from artifact scripts | **closed locally**: live-facts readiness and pilot-status builder ownership moved to `src/application/readmodels`; the live-facts script is a thin CLI wrapper and the old pilot-status script was deleted | `src/application/readmodels/{strategy_group_live_facts_readiness,strategygroup_runtime_pilot_status}.py`; `test_owner_console_status_readmodels_do_not_import_artifact_scripts` guards the boundary | Continue deleting artifact-named scripts when they are no longer command-line entrypoints |
| **P1** | Ticket-bound API and watcher post-step materializers owned FinalGate / Operation Layer / protected-submit / post-submit / fact / lane / runtime-safety logic from `scripts/` | **closed locally**: action-time materializer ownership moved to `src/application/action_time`; scripts are executable wrappers only | `src/application/action_time/{account_safe_facts,fact_snapshots,promotion_action_time_lane,action_time_ticket,finalgate_preflight,operation_layer_handoff,runtime_safety_state,protected_submit_attempt,post_submit_closure}.py`; `test_ticket_bound_api_imports_application_action_time_services_not_scripts` and `test_action_time_materializer_scripts_are_thin_application_wrappers` guard the boundary | Continue migrating remaining production-cadence script-owned publishers/orchestrators only where they own business state, not just command sequencing |
| **P2** | Legacy artifact builder family remains in current `scripts/` and tests | Not invoked by production systemd; can still confuse future agents and reintroduce report-thinking | `build_single_lane_task_packet.py`, `build_strategy_fresh_signal_action_time_boundary.py`, tradeability/candidate/daily table artifact tests and validators remain present | Delete/archive obsolete artifact CLIs after their useful PG projection semantics are moved into current read-model services |

## Verification Commands

Focused verification:

```text
pytest tests/unit/test_strategy_live_candidate_pool.py tests/unit/test_strategygroup_runtime_goal_status.py tests/unit/test_tokyo_runtime_server_monitor.py -q
pytest tests/unit/test_l2_l7_mainline_chain_invariants.py tests/unit/test_action_time_full_chain_impact.py tests/unit/test_server_product_state_refresh_sequence.py -q
pytest tests/unit/test_server_product_state_refresh_sequence.py tests/unit/test_action_time_full_chain_impact.py -q
```

Static verification:

```text
python3 -m py_compile \
  scripts/run_server_product_state_refresh_sequence.py \
  tests/unit/test_server_product_state_refresh_sequence.py \
  tests/unit/test_l2_l7_mainline_chain_invariants.py \
  tests/unit/test_action_time_full_chain_impact.py
git diff --check
python3 scripts/validate_no_runtime_file_authority.py --json
python3 scripts/audit_production_runtime_file_io.py --json --max-frequent-report-write 0
```

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: active 5 StrategyGroups
symbol: active 22 StrategyGroup-symbol-side scopes
stage: Action-Time Ticket / Runtime Safety / protected submit boundary
first_blocker: none for pre-trade chain; production real-submit arming remains intentionally not enabled in the broad watcher post-step
evidence: local full-chain tests now cover disabled_smoke and mock real_gateway_action for every active scope; Tokyo reached disabled_smoke for BRF2-001 / AVAXUSDT / short; Tokyo monitor after 99d7055c reports healthy waiting with blocker none
next_action: keep broad watcher non-authority until a controlled production submit arming change is explicitly implemented through the official ticket-bound API path
stop_condition: a fresh in-scope signal either reaches submitted through official ticket-bound real gateway action, or fails with one precise PG blocker and no file-authority fallback
owner_action_required: no for engineering tests; yes only if production real-submit arming policy is intentionally changed
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no exchange write from tests, reports, or JSON artifacts
```
