# Optuna Candidate Report Contract (Candidate Only)

Last updated: 2026-04-24

This document defines the SSOT contract for artifacts written to:

- `reports/optuna_candidates/*.json`

Hard constraints:

- Candidate reports are **candidate only** and **must not** be promoted to runtime profiles automatically.
- Sim-1期间策略/风控不允许热改，Optuna 结果只能作为人工审查候选。

## JSON Schema (v1)

Required top-level keys:

- `artifact_version`: integer, currently `1`
- `candidate_name`: string, e.g. `optuna_candidate_<job_id>`
- `generated_at`: ISO-8601 UTC string
- `status`: string, must be `candidate_only`
- `promotion_policy`: string, must be `manual_review_required`
- `git`: object with `commit` / `branch` / `is_dirty` (nullable)
- `reproduce_cmd`: string command for dry-run replay (must not contain secrets)
- `source_profile`: object `{name, version, config_hash}`
- `job`: object `{job_id, status, objective, symbol, timeframe, start_time, end_time, n_trials}`
- `best_trial`: serialized OptimizationTrialResult
- `fixed_params`: dict (as provided in OptimizationRequest)
- `runtime_overrides`: dict (resolved BacktestRuntimeOverrides, exclude None)
- `constraints`: object (minimum: allowed_directions / same_bar_policy / random_seed)
- `resolved_request`: object (minimum: symbol/timeframe/limit/mode/costs/risk_overrides/order_strategy)
- `top_trials`: list of serialized OptimizationTrialResult

## Reproduce

Candidate replay is dry-run by default:

```bash
PYTHONPATH=. python scripts/replay_optuna_candidate.py --candidate reports/optuna_candidates/<file>.json
```

This prints:

- candidate metadata (including git commit)
- constraints
- resolved backtest request envelope
- runtime_overrides

## Implementation Notes

- Artifact output directory `reports/` is ignored by git.
- Candidate report construction is owned by `src/application/strategy_optimizer.py`:
  - `StrategyOptimizer.build_candidate_report()`
  - `StrategyOptimizer.write_candidate_report()`

