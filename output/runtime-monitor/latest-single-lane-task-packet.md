## Single Lane Task Packet

- Task ID: `P0-MPG-001-WATCHER-TICK-MISSING-CLOSURE`
- Active lane: `MPG-001 / OPUSDT / long`
- Chain position: `replay_live_parity`
- First blocker: `watcher_tick_missing`
- Evidence: `output/runtime-monitor/latest-strategy-live-candidate-pool.json:MPG-001/OPUSDT first_blocker=watcher_tick_missing server_runtime_coverage=active_watcher_scope`
- Expected state change: `MPG-001/OPUSDT first_blocker changes from watcher_tick_missing to the next precise blocker, market_wait_validated, or lane exit under the WIP stop rule.`
- Next action: `refresh_readonly_watcher_for_candidate_symbol`
- Stop condition: `blocker moves, repeats through stop review, or symbol exits candidate universe`
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
- `scripts/build_replay_live_parity_audit.py`
- `tests/unit/test_replay_live_parity_audit.py`
- `output/runtime-monitor/latest-replay-live-parity-audit.json`
- `output/runtime-monitor/latest-replay-live-parity-audit.md`

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

`MPG-001/OPUSDT no longer has watcher_tick_missing, or the Daily Table reclassifies the same lane to a more precise first blocker.`
