---
name: backend
description: Codex backend/core implementation workflow. Use for backend, execution, risk, infrastructure, API, or domain changes.
user-invocable: true
---

# Backend (Codex Core Implementation)

## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
- The relevant Codex task card and current source files

## Role

Codex owns core backend implementation and skeleton development, especially execution, risk, reconciliation, order lifecycle, exchange gateway, and account safety.

Claude may receive only bounded local backend tasks via task card.

Controlled testnet/dev/readiness execution-chain work is allowed when scoped by
the active task. Real live / real-funds order placement remains separately
Owner-authorized only.

## Core Files

Codex-owned by default:

- `src/application/execution_orchestrator.py`
- `src/application/order_lifecycle_service.py`
- `src/application/position_projection_service.py`
- `src/application/capital_protection.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`

## Engineering Constraints

- Keep `domain/` free of I/O frameworks.
- Use `decimal.Decimal` for financial calculations.
- Mask sensitive values in logs.
- Prefer named Pydantic models over `Dict[str, Any]`.
- Ask before long test suites.
