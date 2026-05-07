# ADR-0007: Reconciliation Read Model Persistence

**Status:** Accepted  
**Date:** 2026-05-06  
**Scope:** LS-003d — periodic reconciliation read model persistence

## Context

LS-003a added `ReconciliationService.build_read_model(symbol)` as a read-only runtime snapshot. LS-003b wired it into a periodic report-only loop that logs consistent and mismatched states but does not persist history.

The project already has `PGReconciliationReportORM` and `PGReconciliationDetailORM`, but those belong to startup reconciliation. Their semantics include startup action and resolution concepts such as ghost orders, orphan orders, `actions_taken`, and `resolved`. The periodic read model is observation-only and must not imply remediation.

## Decision

Add dedicated PG persistence for periodic reconciliation read model results:

- `reconciliation_read_model_reports` stores one aggregate row per symbol check.
- `reconciliation_read_model_mismatches` stores zero or more mismatch details for that report.

The periodic loop saves:

- Consistent reports with no mismatch details.
- Mismatch reports with all mismatch details.
- Fetch failure reports when `build_read_model(symbol)` raises a non-cancellation exception.

Persistence is best-effort. Save failures are logged and never propagated into trading behavior, loop continuation, order placement, shutdown, protection handling, or reconciliation itself. `asyncio.CancelledError` remains a shutdown signal and is re-raised.

## Rationale

Dedicated tables keep read-only observation separate from startup reconciliation action history. Reusing the startup tables would blur report-only runtime telemetry with action/resolution records, making future operators and agents more likely to treat observations as remediation state.

Consistent reports are saved because absence of mismatches is useful evidence. They allow operators to distinguish "the system checked and was consistent" from "the system did not check or failed before recording."

Fetch failure reports are saved because inability to build the read model is itself an observation. It preserves data-health evidence without turning the failure into a control action.

There is no `cycle_id` or `run_id` in this version. The report identity is `{checked_at_ms}:{symbol}`, which is enough for the current single-symbol periodic observation and avoids introducing a broader runtime task model.

There is no retention policy in LS-003d. Cleanup policy affects operations, storage expectations, and possibly compliance posture, so it should be decided separately rather than hidden inside this persistence slice.

There is no REST API or frontend in LS-003d. The task creates the durable read source only; query surfaces and Owner Console display remain separate product/API work.

Best-effort persistence is chosen instead of fail-closed because these rows are observation data, not trading safety authority. A database write failure must not block entries, cancel orders, repair protection, interrupt shutdown, or alter reconciliation semantics.

## Boundary With LS-003c

LS-003d does not implement control-path reconciliation. It does not:

- Block symbols.
- Create recovery tasks.
- Repair protection orders.
- Cancel orphan exchange orders.
- Place orders.
- Change runtime profiles, risk rules, strategy logic, or Decision Trace schemas.

Any future transition from observation to block/recovery/repair belongs to LS-003c or another explicitly approved control-path task.

## Consequences

The runtime now has a durable read-only history of periodic reconciliation observations. This supports later operator review and future API/frontend work without changing trading behavior.

The tables are additive and can be rolled back by downgrading Alembic revision `008` when no runtime depends on the stored observations.
