# Optuna Candidate Review Rubric

Last updated: 2026-04-24

This document defines the manual review rubric for candidate-only Optuna artifacts
written to `reports/optuna_candidates/*.json`.

Hard constraints:

- Candidate artifacts remain `candidate_only` and must not auto-promote runtime config.
- Review status is an assessment result, not an execution approval.
- Sim-1 period still requires human review before any parameter set is considered for
  follow-up validation.

## Review Statuses

- `PASS_STRICT`
  - Candidate passes all Strict v1 hard gates.
  - No material warning remains open.
- `PASS_STRICT_WITH_WARNINGS`
  - Candidate passes all Strict v1 hard gates.
  - One or more warning-only checks are unresolved, but none are blocking.
- `PASS_LOOSE`
  - Candidate fails one or more Strict v1 hard gates, but still meets the looser
    exploratory threshold and should be kept for comparison/reference.
- `REJECT`
  - Candidate fails loose screening, shows obvious overfitting/instability, or has
    incomplete artifact integrity.

## Strict v1

Use this as the current gate for entering the manual review pool.

Required hard gates:

- `total_trades >= 100`
- `sharpe_ratio >= 1.0`
- `total_return >= 0.30`
- `max_drawdown <= 0.25`
- `win_rate >= 0.45`
- `params_at_boundary == false`

Current warning-only checks:

- `sortino_ratio` missing / `0` / obviously suspect
- `trade_concentration` unavailable
- `profit_concentration` unavailable
- `max_consecutive_losses` unavailable

Notes:

- `sortino_ratio` is currently informational only. It must be shown in the review,
  but should not fail Strict v1 by itself until the surrounding review pipeline is
  considered fully stable.
- `params_at_boundary == false` means the candidate must not sit exactly on the
  configured search-space boundary for reviewed parameters.

## Loose v1

Use this for exploratory retention when the candidate is not ready for the strict pool
but still has enough signal to keep.

- `total_trades >= 50`
- `sharpe_ratio >= 0.5`
- `total_return >= 0.10`
- `max_drawdown <= 0.30`
- `win_rate >= 0.40`

Loose v1 does not require the candidate to pass parameter-boundary checks, but the
review should explicitly note any boundary-hugging behavior.

## Warning Semantics

Warnings do not block `PASS_STRICT_WITH_WARNINGS`, but they must be carried into the
review summary.

Typical warnings:

- `sortino_missing_or_suspect`
- `trade_concentration_unavailable`
- `profit_concentration_unavailable`
- `max_consecutive_losses_unavailable`
- `parameter_near_boundary`

Escalate a warning to reject only if evidence shows the candidate is materially unsafe
or the artifact cannot be trusted.

## Manual Review Template

```md
# Candidate Review Summary

## Basic Info
- Candidate Name:
- Generated At:
- Source Profile:
- Git Commit:
- Objective:
- Best Trial:
- N Trials:

## Hard Gates (Strict v1)
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Total Trades |  | >= 100 |  |
| Sharpe Ratio |  | >= 1.0 |  |
| Total Return |  | >= 30% |  |
| Max Drawdown |  | <= 25% |  |
| Win Rate |  | >= 45% |  |
| Params at Boundary |  | false |  |

## Warning Checks
| Check | Result | Status |
|-------|--------|--------|
| Sortino Ratio |  |  |
| Trade Concentration |  |  |
| Profit Concentration |  |  |
| Max Consecutive Losses |  |  |

## Parameters
```json
{}
```

## Review Decision
- Review Status:
- Reason:

## Follow-up
1.
2.
3.
```

## Current Interpretation

For current Sim-1 pre-review work:

- Prefer `PASS_STRICT` and `PASS_STRICT_WITH_WARNINGS` candidates for follow-up.
- Keep `PASS_LOOSE` only as comparison/reference material.
- Do not use `REJECT` candidates for downstream runtime discussion.
