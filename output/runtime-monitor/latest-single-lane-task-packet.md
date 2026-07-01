## Single Lane Task Packet

- Task ID: `P0-MPG-WATCHER-TICK-CLOSURE`
- Active lane: `MPG-001 / SOLUSDT / long`
- Chain position: `replay_live_parity`
- First blocker: `watcher_tick_missing`
- Evidence: `output/runtime-monitor/latest-replay-live-parity-audit.json:MPG-001/SOLUSDT blocker_class=watcher_tick_missing`
- Expected state change: `watcher/public facts tick becomes present and the lane advances to the next precise blocker or market_wait_validated if all non-market blockers close`
- Next action: `refresh_or_repair_watcher_public_fact_input`
- Stop condition: `MPG-001/SOLUSDT no longer has watcher_tick_missing, or refreshed evidence proves a different earlier blocker class`
- Authority boundary: `non-executing read model only; no FinalGate bypass, no Operation Layer bypass, no exchange write`

### Allowed Files

- `scripts/build_replay_live_parity_audit.py`
- `scripts/build_daily_live_enablement_table.py`
- `scripts/run_strategygroup_runtime_local_monitor_sequence.py`
- `tests/unit/test_replay_live_parity_audit.py`
- `tests/unit/test_daily_live_enablement_table.py`
- `tests/unit/test_strategygroup_runtime_local_monitor_sequence.py`
- `output/runtime-monitor/latest-*.json`
- `output/runtime-monitor/latest-*.md`

### Forbidden Files

- `src/application/execution_orchestrator.py`
- `src/application/order_lifecycle_service.py`
- `src/infrastructure/exchange_gateway.py`
- live profile files
- order sizing defaults
- credential or secret files
- FinalGate bypass paths
- Operation Layer bypass paths

### Done When

`Daily Table rank 1 either moves past MPG-001/SOLUSDT watcher_tick_missing or reclassifies it into a more precise first blocker with Tradeability and Daily Table agreeing on the same lane.`
