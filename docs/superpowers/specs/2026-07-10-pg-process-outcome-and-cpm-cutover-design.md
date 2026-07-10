# PG Process Outcome And CPM v2 Cutover Design

## Objective

Close the last orchestration gap before deploying `CPM-LONG v2`: action-time
facts or promotion may be truthfully business-blocked without making the
watcher/systemd process fail.

## Authority Decision

PG remains the only runtime truth source.

```text
materializer transaction
-> domain rows in PG
-> brc_runtime_process_outcomes current row in PG
-> CLI exit code reflects process health only
-> server refresh sequence continues or fails closed
-> monitor/read models explain the PG business state
```

The server sequence must not parse stdout JSON to determine business state.
No JSON/MD file or generated artifact participates in this flow.

## Process Versus Business State

`brc_runtime_process_outcomes.process_state` already separates:

- `succeeded`;
- `noop`;
- `business_blocked`;
- `retryable_failure`;
- `hard_failure`.

The CLI exit contract becomes:

| PG process state | CLI exit | Meaning |
| --- | ---: | --- |
| `succeeded` | `0` | Process completed and advanced state |
| `noop` | `0` | Process completed with nothing to do |
| `business_blocked` | `0` | Process completed and persisted an exact non-advancing business result |
| `retryable_failure` | `1` | Infrastructure/runtime process failed and may be retried |
| `hard_failure` | `1` | Safety/identity/process hard failure |

Exit code is process transport, not business authority. The detailed state and
first blocker remain in PG.

## Materializer Integration

### Action-Time Facts

`materialize_action_time_fact_snapshots` will write one current process outcome
in the same transaction as its fact snapshots.

| Materializer result | PG process state | PG business state |
| --- | --- | --- |
| `no_current_fresh_live_signal` | `noop` | `waiting_for_opportunity` |
| `action_time_fact_snapshots_materialized` | `succeeded` | `processing` |
| `action_time_fact_snapshots_blocked` | `business_blocked` | `temporarily_unavailable` |

The blocked fact snapshot continues to carry
`blocker_class=computed_not_satisfied`. Missing strategy facts remain visible;
they are not defaulted or converted into market wait.

### Promotion / Action-Time Lane

The promotion materializer already writes `brc_runtime_process_outcomes`.
Its CLI will use that persisted process state:

- `promotion_candidates_blocked` is a successful process with a business block;
- PG/repository/identity failures remain process failures;
- no lane, ticket, FinalGate, Operation Layer, or order is fabricated.

## Shared Exit-Code Function

The common process-outcome module will expose one function that maps a typed or
persisted process outcome to a CLI exit code. Materializers must not each invent
their own status-to-exit mapping.

When the process-outcome table is absent in historical unit-test schemas, the
materializer may preserve its existing legacy test fallback. Production at
migration 106+ must use the PG outcome row.

## CPM v2 Production Cutover

After local acceptance, merge and deploy the complete branch as migration 107.

The release must:

- preserve CPM v1 as historical observe-only;
- make CPM v2 the only trial-grade Event Spec;
- atomically bind four active CPM candidates to v2;
- keep all other Event Specs observe-only;
- import no historical signal, promotion, lane, ticket, or order;
- change no Owner Policy, runtime profile, notional, leverage, symbol set, or
  lane concurrency.

## Performance And Cadence

| Dimension | Decision |
| --- | --- |
| Cadence | One bounded PG process-outcome upsert per invoked materializer |
| No-signal JSON/MD writes | `0` |
| PG writes | One current-row upsert per process/scope; existing fact/promotion rows unchanged |
| CPU | Constant-time outcome classification; no new heavy builder |
| Disk | No new files, reports, sidecars, or append-only logs |
| Timeout | Existing subprocess and server-sequence timeout boundaries remain |
| Retention | Current PG row plus existing audit lineage only |

## Acceptance

- Fact business block persists `computed_not_satisfied` and a PG
  `business_blocked` process outcome.
- Fact CLI exits `0` for that successful process.
- Promotion business block exits `0` from its PG process outcome.
- PG/repository/SQL/identity failures remain non-zero and fail closed.
- Server refresh sequence reaches current-projection publication without
  reporting a watcher service failure.
- No JSON/MD file authority or stdout business-state parsing is introduced.
- Tokyo reaches migration 107 with healthy services and no forbidden effects.

## Authority Boundary

This design changes process reporting only. It grants no signal, promotion,
lane, ticket, FinalGate, Operation Layer, protected-submit, exchange-write,
profile, sizing, withdrawal, transfer, or credential authority.
