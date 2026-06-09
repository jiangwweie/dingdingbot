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
LS-003-A

## Goal

Add structured runtime log events for the newest Live-safe v1 reconciliation,
protection-health, and local hygiene flows.

## Why

Recent controlled testnet smoke work added or validated local-only terminalizing
paths and protection-health healing. Runtime operators need searchable,
secret-free events that distinguish actual exchange risk from local historical
data hygiene.

## Context

- Current program: Live-safe v1.
- Codex owns architecture and merge readiness.
- Claude owns only this bounded implementation/test task.
- Return/drawdown numbers are evaluation dimensions, not hard constraints.

## Allowed files

- `src/infrastructure/logger.py`
- `src/application/external_close_monitor.py`
- `src/application/order_lifecycle_service.py`
- `src/application/protection_health_monitor.py`
- `tests/unit/test_ls003_structured_runtime_logs.py`

## Forbidden files

- `src/application/execution_orchestrator.py`
- `src/application/position_projection_service.py`
- `src/application/capital_protection.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`
- `config/`
- runtime profiles

## Requirements

1. Add structured log payloads for external-close local hygiene, including
   symbol, signal id, terminalized order counts, source, and reason.
2. Add structured log payloads for closed-position stale protection
   terminalization, including symbol, signal id, order roles, and counts.
3. Add structured log payloads when protection-health blocks are cleared by a
   healed read model.
4. Add structured log payloads for historical-local hygiene metadata if the
   local cleanup path is later moved from SQL into code.
5. Do not log API keys, secrets, raw credentials, or unmasked account values.
6. Keep existing human-readable log messages unless a test proves duplication
   causes a real problem.

## Tests

- `pytest -q tests/unit/test_ls003_structured_runtime_logs.py`
- `pytest -q tests/unit/test_tiny001d1b_external_close_monitor.py tests/unit/test_tiny001c_protection_health_monitor.py`

## Done When

- The new structured events are emitted in the listed flows.
- Tests assert event names and key fields.
- No forbidden files changed.
- Existing external-close and protection-health tests still pass.
- Claude returns the required result format.

## Stop And Ask If

- A required change falls outside Allowed files.
- The task requires architecture, runtime profile, strategy parameter, or merge
  decisions.
- Existing behavior conflicts with the task card.
