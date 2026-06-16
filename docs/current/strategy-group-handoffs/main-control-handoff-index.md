# Main-Control StrategyGroup Handoff Index

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-15

## Research Sync

Current research handoff source:

```text
branch: codex/strategy-research-20260613-goal
commit: d62ce55727614fcfdb2d12f8fee1d3c226950048
status: reviewed_and_synced_to_main_control_baseline
```

See `docs/current/strategy-group-handoffs/main-control-research-sync.md`.

## Batch

| StrategyGroup | Role | Default Mode |
| --- | --- | --- |
| `MPG-001` | Momentum persistence | `armed_observation` |
| `TEQ-001` | Equity-like perpetual momentum | `armed_observation` |
| `FBS-001` | Funding / basis stress | `armed_observation` |
| `PMR-001` | Precious-metal overlay | `observe_only` |
| `SOR-001` | Session opening-range structure | `conditional_armed_observation` |

## Boundary

These handoffs are Strategy Picker and watcher-scope inputs only. They are not
order authority, FinalGate pass evidence, Operation Layer evidence, deploy
authority, credential changes, live profile changes, or order-sizing defaults.
