## Single Lane Task Packet

- Task ID: `P0-MPG-001-SCOPE-NOT-ATTACHED-CLOSURE`
- Active lane: `MPG-001 / OPUSDT / long`
- Chain position: `symbol_scope_decision`
- First blocker: `scope_not_attached`
- Evidence: `output/runtime-monitor/latest-replay-live-parity-audit.json:MPG-001/OPUSDT blocker_class=scope_not_attached`
- Expected state change: `MPG-001/OPUSDT first_blocker changes from scope_not_attached to the next precise blocker, market_wait_validated, or lane exit under the WIP stop rule.`
- Next action: `produce_scoped_live_observation_or_scope_proposal`
- Stop condition: `scoped live observation proposal is attached or Owner scope decision is required`
- Authority boundary: `single_lane_task_packet_is_non_executing; no_finalgate_no_operation_layer_no_exchange_write_no_live_profile_or_sizing_change`

### Allowed Files

- `scripts/build_single_lane_task_packet.py`
- `scripts/validate_single_lane_task_packet.py`
- `scripts/build_daily_live_enablement_table.py`
- `scripts/validate_daily_live_enablement_table.py`
- `tests/unit/test_single_lane_task_packet.py`
- `tests/unit/test_daily_live_enablement_table.py`
- `output/runtime-monitor/latest-single-lane-task-packet.json`
- `output/runtime-monitor/latest-single-lane-task-packet.md`
- `output/runtime-monitor/latest-daily-live-enablement-table.json`
- `output/runtime-monitor/latest-daily-live-enablement-table.md`
- `scripts/build_strategygroup_tradeability_decision.py`
- `tests/unit/test_strategygroup_tradeability_decision.py`
- `output/runtime-monitor/latest-strategygroup-tradeability-decision.json`
- `output/runtime-monitor/latest-strategygroup-tradeability-decision.md`

### Forbidden Files

- `src/application/execution_orchestrator.py`
- `src/application/order_lifecycle_service.py`
- `src/application/position_projection_service.py`
- `src/application/capital_protection.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`
- live profile files
- order sizing defaults
- credential or secret files
- FinalGate bypass paths
- Operation Layer bypass paths

### Done When

`MPG-001/OPUSDT no longer has scope_not_attached, or the Daily Table reclassifies the same lane to a more precise first blocker.`
