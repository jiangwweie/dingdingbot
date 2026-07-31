# BRC Trading Kernel

## Product Objective

BRC is a single-Owner, small-capital experiment for asymmetric right-tail
returns. Its capital is deliberately limited and loss-capable. The system does
not promise stable yield or a smooth equity curve; it bounds individual losses
and execution failure while preserving the path for fewer large winners to
cover more frequent small losses.

The exact capital and order-capable boundary is owned by
`docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md`. Strategy evidence is
evaluated under `docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`.

## Trading Chain

The repository contains one PostgreSQL-backed trading kernel:

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

The kernel supports multiple concurrent Netting Domains while serializing new
ENTRY admission. It forbids add-to-position behavior, ENTRY retries after
authoritative rejection, blind resend after unknown outcome, and runtime
fallback to retired models.

## Capital and Leverage

Stop-risk budget controls planned loss at invalidation. Fixed account leverage
controls margin use; it does not increase stop-risk authority. Existing
exposure retains protection, controlled exit, reconciliation, Settlement, and
Review authority even when admission of new ENTRY is disabled.

## Runtime Architecture

Observation, Entry, Lifecycle, and Reconciliation run as four persistent
systemd workers with bounded polling and one shared resource slice. PostgreSQL
owns current state and append-only lifecycle facts. Exchange reads reconcile
external truth; repository documents and generated output are never runtime
authority.

Production execution and schema authority belong only under:

```text
src/trading_kernel/**
migrations/trading_kernel/**
scripts/trading_kernel/**
```

Current production identity, certification, runtime measurements, and remaining
acceptance gates are recorded only in
`docs/current/MAIN_CONTROL_ROADMAP.md`. Deployment procedure and resource limits
are owned by `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`.

## Documentation

| Start here | Responsibility |
| --- | --- |
| `AGENTS.md` | Repository operating and engineering constraints |
| `docs/README.md` | Current authority index |
| `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Product objective, capital premise, and order-capable profile |
| `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md` | Architecture and business invariants |
| `docs/current/MAIN_CONTROL_ROADMAP.md` | Current production facts and critical path |
| `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` | Release, recovery, and resource contract |

## Local Verification

Install the repository's development dependencies before running local checks:

```bash
python3 -m pytest -q tests/trading_kernel
python3 -m ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel
python3 scripts/audit_production_runtime_file_io.py
```

Schema and readonly certification additionally require a disposable or
explicitly authorized PostgreSQL URL:

```bash
export TRADING_KERNEL_DATABASE_URL='postgresql+psycopg://...'
python3 scripts/trading_kernel/verify_schema.py
python3 scripts/trading_kernel/certify_readonly.py
```

Tokyo releases and real-funds acceptance use committed tooling only. Ad hoc
server edits, direct exchange writes, and retired runtime restoration are not
supported.
