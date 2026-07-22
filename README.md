# BRC Multi-Position Trading Kernel

Status: active rebuild and controlled cutover

## Target

This repository contains one PostgreSQL-backed trading kernel:

```text
typed live signal
-> immutable Ticket
-> durable exchange command
-> protected multi-position lifecycle
-> reconciliation
-> settlement
-> review
```

The kernel supports multiple concurrent Netting Domains while serializing new
ENTRY admission. It forbids add-to-position behavior, ENTRY retries after
authoritative rejection, blind resend after unknown outcome, and runtime
fallback to retired models.

## Start Here

```text
AGENTS.md
docs/README.md
docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md
docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md
docs/current/MAIN_CONTROL_ROADMAP.md
```

## Current Production Code

```text
src/trading_kernel/**
migrations/trading_kernel/**
scripts/trading_kernel/**
```

## Local Verification

```bash
pytest tests/trading_kernel -q
ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel
python3 scripts/audit_production_runtime_file_io.py
python3 scripts/trading_kernel/verify_schema.py
python3 scripts/trading_kernel/certify_readonly.py
```

Tokyo cutover and real-funds acceptance use committed tooling only. Ad hoc
server edits and retired runtime restoration are not supported.
