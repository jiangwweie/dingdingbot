> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Task ID
GKS-v0

## Goal
Add a minimal Global Kill Switch safety primitive that can stop all new entries before order creation.

## Why
Owner-Gated Execution needs one system-level stop-all-new-entries primitive before Strategy Governance, Owner-Gated Permission Layer, human gating, or strategy pause work can safely build on top of runtime execution.

## Allowed files
- `docs/ops/gks-v0-global-kill-switch-task-card-2026-05-11.md`
- `src/application/global_kill_switch.py`
- `src/application/execution_orchestrator.py`
- `src/infrastructure/pg_models.py`
- `src/infrastructure/pg_global_kill_switch_repository.py`
- `src/infrastructure/repository_ports.py`
- `src/infrastructure/core_repository_factory.py`
- `src/interfaces/api.py`
- `src/interfaces/api_console_runtime.py`
- `src/main.py`
- `tests/unit/test_gks_v0_global_kill_switch.py`

## Forbidden files
- Strategy implementation files.
- Direction A documents or runtime rules.
- Risk profile, runtime profile, exchange credentials, and order-sizing defaults.
- Order cancel, force close, TP/SL mutation, adapter, backtest, or sweep code.
- Human gate, strategy pause, LLM control, or strategy router code.

## Requirements
1. GKS-v0 blocks only new entries.
2. Do not cancel existing orders.
3. Do not force-close existing positions.
4. Do not modify TP/SL.
5. Do not affect `OrderLifecycleService.update_order_from_exchange`.
6. Do not modify strategy/risk/runtime profiles.
7. Do not connect LLM.
8. Do not implement human gate or strategy pause.
9. Insert the GKS check in `ExecutionOrchestrator.execute_signal()` after per-symbol circuit breaker and before `CapitalProtection.pre_order_check()`.
10. When blocked, reuse `ExecutionIntentStatus.BLOCKED` and set `blocked_reason="KILL_SWITCH"`.
11. Use a minimal PG-backed persisted state plus in-memory cache.
12. PG row missing may be treated as OFF in v0, but this is not final live semantics.
13. A failed activation persistence write must not be silently downgraded. It must log/alert HIGH severity and return failure to the toggle caller.
14. Add minimal read/toggle API. Access boundary must be local/internal runtime control only, not a public internet control plane.
15. Add minimal logs and Decision Trace event for GKS checks.
16. GKS-v0 does not declare live readiness. Before live use, Owner must reconfirm initialization row, read failure policy, and persistence failure policy.

## Tests
- GKS active blocks new entries.
- GKS inactive reaches `CapitalProtection.pre_order_check()`.
- Circuit breaker has priority over GKS.
- GKS has priority over `CapitalProtection.pre_order_check()`.
- Blocked intent has `blocked_reason="KILL_SWITCH"`.
- Startup/service initialization restores persisted ON state.
- Toggle then read endpoint returns the new state.
- GKS does not affect existing order update path.

## Done When
- Focused tests pass.
- No forbidden scope is touched.
- Final response explains insertion point, persistence semantics, test result, and remaining risks.
