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
| **File authority strict audit** | `validate_no_runtime_file_authority.py` and `audit_production_runtime_file_io.py --max-frequent-report-write 0` | Production current chain is not using repo/output/report JSON or Markdown as runtime authority |

### Current Open / Closed Findings

| Severity | Finding | Status | Evidence | Next action |
| --- | --- | --- | --- | --- |
| **P0** | Required action-time post-step can fail without enough stdout context | **closed locally** | `run_server_product_state_refresh_sequence.py` now emits `blocked_required_stdout_tail` and `blocked_required_stderr_tail` | Deploy with next stage-worthy runtime fix |
| **P0** | Local constructed chain did not prove all active scopes can pass mock real-submit and post-submit closure | **closed locally** | 22 active scopes now pass through mock `real_gateway_action -> submitted -> reconciliation_pending` | Keep in full action-time impact suite |
| **P1** | Server Monitor could reuse a stale `action_time_boundary_not_reproduced` readiness blocker after the fresh signal expired | **closed locally** | Candidate Pool now treats action-time-only blockers as current only when a fresh PG signal exists; `test_pg_stale_action_time_boundary_without_current_signal_is_quiet` covers the Tokyo failure shape | Deploy with next stage-worthy runtime fix |
| **P1** | Server periodic watcher is intentionally non-authority and currently stops at `disabled_smoke` / preflight paths unless submit execution is separately armed | **open by design** | systemd dispatcher drop-in has `--execute-preflight` and does not include `--execute-operation-layer-submit` | Decide controlled production submit arming separately; do not hide it as market wait |
| **P1** | Real gateway action path is API-bound, not direct sequence-runner-bound | **open by design** | `materialize_ticket_bound_protected_submit_attempt.py` prepares `submit_prepared`; API layer performs gateway call and records result | Keep tests proving mock result identity; only official API path may perform real gateway call |

## Verification Commands

Focused verification:

```text
pytest tests/unit/test_strategy_live_candidate_pool.py tests/unit/test_strategygroup_runtime_goal_status.py tests/unit/test_tokyo_runtime_server_monitor.py -q
pytest tests/unit/test_server_product_state_refresh_sequence.py tests/unit/test_action_time_full_chain_impact.py -q
```

Static verification:

```text
python3 -m py_compile \
  scripts/run_server_product_state_refresh_sequence.py \
  tests/unit/test_server_product_state_refresh_sequence.py \
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
first_blocker: production real-submit arming is not enabled in the broad watcher post-step
evidence: local full-chain tests now cover disabled_smoke and mock real_gateway_action for every active scope; Tokyo reached disabled_smoke for BRF2-001 / AVAXUSDT / short
next_action: keep broad watcher non-authority until a controlled production submit arming change is explicitly implemented through the official ticket-bound API path
stop_condition: a fresh in-scope signal either reaches submitted through official ticket-bound real gateway action, or fails with one precise PG blocker and no file-authority fallback
owner_action_required: no for engineering tests; yes only if production real-submit arming policy is intentionally changed
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no exchange write from tests, reports, or JSON artifacts
```
