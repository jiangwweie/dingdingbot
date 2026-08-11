# M5-OBS-001

## Goal

Implement Signal-owned TradFi SOR Observation Outcomes, bounded StrategyVersion
evaluation reads, and Owner Console evidence while preserving the official M6
Ticket path and keeping TradFi Entry disabled.

## Why

M2-M4 can form TradFi StrategySignals but the existing Shadow model requires a
portfolio Admission rejection. M5 needs evidence when Admission is intentionally
not run.

## Allowed files

- `docs/current/**`
- `docs/superpowers/specs/**`
- `docs/superpowers/plans/**`
- `migrations/trading_kernel/versions/0005_tradfi_instrument_center.py`
- `src/trading_kernel/domain/**`
- `src/trading_kernel/application/**`
- `src/trading_kernel/infrastructure/**`
- `src/trading_kernel/interfaces/**`
- `scripts/trading_kernel/verify_schema.py`
- `frontend/owner-console/**`
- focused `tests/trading_kernel/**`

## Forbidden files

- production server configuration and credentials
- Nginx/systemd activation state
- capital, leverage and live-submit expansion
- a new Venue adapter, worker or execution chain

## Requirements

1. Generalize Shadow identity to one exact Signal while preserving optional
   portfolio-rejection Admission lineage.
2. Add the SOR path evaluator and quote/plan facts without simulated PnL.
3. Refresh TradFi Product facts automatically in Observation with network I/O
   outside transactions and bounded same-bar cache.
4. Support signals without AdmissionDecision as `not_evaluated`.
5. Add StrategyVersion Observation summaries, bounded samples and route-safe UI.
6. Keep TradFi Entry disabled and produce zero exchange writes.

## Tests

- focused domain Shadow/path tests;
- focused Observation-to-Signal/Shadow integration;
- exact `0004 -> 0005` preservation test;
- focused Owner read/API tests;
- focused Strategy page test and frontend build;
- Ruff, Mypy and current-document checks.

## Done When

- one TradFi Signal owns one completed or explicit unavailable Observation
  Outcome;
- no Ticket/Command authority is created by M5;
- Owner Console can summarize and inspect the outcome;
- focused verification passes;
- working tree is committed locally and production remains unchanged.

## Hard Stops

- do not deploy;
- do not enable TradFi Entry;
- do not add exchange mutation;
- do not weaken existing Ticket, Command, lifecycle or migration invariants.
