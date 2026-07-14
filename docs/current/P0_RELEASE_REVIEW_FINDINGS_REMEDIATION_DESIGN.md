---
title: P0_RELEASE_REVIEW_FINDINGS_REMEDIATION_DESIGN
status: LOCAL_VERIFIED_DEPLOYMENT_PENDING
authority: docs/current/P0_RELEASE_REVIEW_FINDINGS_REMEDIATION_DESIGN.md
last_verified: 2026-07-14
---

# P0 Release Review Findings Remediation Design

## Decision Summary

This design closes the **two findings found during review of the local release
candidate** on `codex/release-risk-analysis-20260714`:

1. **P1 Owner-notification ledger truncation**: the monitor can project more
   than 1,000 notification candidates, while one combined ledger query applies
   a global `LIMIT 1000`. A previously sent row can be omitted, selected again,
   sent again, and then collide with the unique `dedupe_key` constraint.
2. **P2 venue lookup-view divergence**: the application classifies every
   `SL/RUNNER_SL + stop_market` lookup as conditional, while the gateway uses a
   conditional view only for Binance and keeps the existing regular client-id
   view for non-Binance adapters.

The recommended repair is:

```text
notification candidates
-> exact dedupe-key lookup with complete candidate coverage
-> compatibility lookup only for exact misses
-> delivery eligibility and five-attempt cap
-> send and persist

durable exchange command
-> one pure shared venue lookup-view resolver
-> application and gateway consume the same result
-> typed readonly lookup
-> contradiction check and durable reconciliation decision
```

The **current Tokyo Release continues running unchanged**. This design does not
pause new entries, deploy code, restart services, mutate production PG rows,
send Feishu messages, create exchange writes, or change strategy, capital,
leverage, symbol, side, profile, FinalGate, Operation Layer, protection, exit,
or emergency-reduce policy.

## Relationship To Current Documents

This document is a focused corrective supplement to:

- `docs/current/P0_OWNER_NOTIFICATION_PROJECTION_AND_DELIVERY_CLOSURE_DESIGN.md`;
- `docs/current/P0_CONDITIONAL_EXCHANGE_COMMAND_RECONCILIATION_CLOSURE_DESIGN.md`.

It does not replace their product semantics. It corrects two implementation
assumptions discovered after their local implementations were reviewed:

| Existing contract | Preserved rule | Corrected assumption |
| --- | --- | --- |
| Owner notification projection and delivery | PG notification ledger remains the single delivery history; five attempts per run; sent rows never resend | One globally limited combined query does not guarantee coverage of every exact candidate key |
| Conditional exchange-command reconciliation | Required lookup view must be proven before absence; no reconciliation exchange write | Application and gateway cannot independently infer the required view |

The source package designs and implementation plans record this corrective
closure. This document is now `LOCAL_VERIFIED_DEPLOYMENT_PENDING`; deployment
remains a separate Owner decision.

## Known Objective Facts

### Notification Ledger Fact

`scripts/run_tokyo_runtime_server_monitor.py::_pg_owner_notification_rows`
currently executes one query with this shape:

```sql
WHERE dedupe_key IN (...)
   OR (notification_kind IN (...) AND correlation_id IN (...))
ORDER BY updated_at_ms DESC
LIMIT 1000
```

The delivery selector treats an identity absent from the returned map as a new
or retryable notification. The send occurs before the absent-row branch inserts
the ledger record. `brc_server_monitor_notifications.dedupe_key` is unique.

A review reproduction with **1,001 candidates and 1,001 already-sent exact
ledger rows** returned only 1,000 ledger rows and selected one omitted identity
for delivery.

Sources:

- `scripts/run_tokyo_runtime_server_monitor.py`;
- `src/application/owner_notification.py`;
- `migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py`;
- `tests/unit/test_owner_notification_delivery.py`.

### Venue Lookup Fact

`src/application/action_time/exchange_command_reconciliation.py` currently
derives the expected view from only `order_role` and `order_type`:

```text
SL or RUNNER_SL + stop_market -> conditional_algo_order
everything else               -> regular_order
```

`src/infrastructure/exchange_gateway.py` currently derives it differently:

```text
Binance SL or RUNNER_SL + stop_market -> conditional_algo_order
non-Binance                           -> regular_order
```

The existing gateway test explicitly proves that `okx_swap + SL + stop_market`
returns `regular_order`. The application would classify that typed result as
`required_lookup_view_mismatch` and hard-stop it.

Sources:

- `src/application/action_time/exchange_command_reconciliation.py`;
- `src/infrastructure/exchange_gateway.py`;
- `tests/unit/test_phase5e_exchange_gateway_min_notional.py`;
- `tests/unit/test_ticket_bound_exchange_command_reconciliation.py`.

## Analysis From The Facts

### Why P1 Is Release-Blocking

The notification defect can cause an externally visible duplicate card before
the database reports the unique-key collision. It can then fail the monitor
transaction that should have recorded the delivery outcome. This does not grant
trading authority, but it makes Owner notification and monitor cadence
unreliable. Therefore the combined candidate must not be deployed until it is
closed.

### Why P2 Is A Core Contract Defect

The current Tokyo scope uses canonical `exchange_id=binance_usdm`, so the
divergence does not change the currently selected live venue behavior. It still
violates the durable multi-venue boundary: the same typed request can receive
two different required-view answers depending on which layer evaluates it.

The correction must remove the duplicate inference, not add another adapter or
compatibility bridge.

## Global Invariants

1. Every projected notification candidate must obtain the exact ledger row for
   its stable `dedupe_key` when that row exists.
2. A global result limit must never turn an existing `sent`, exhausted, or
   resolved ledger row into apparent absence.
3. Legacy correlation compatibility runs only after exact stable-key lookup and
   cannot override an exact match.
4. The five-card limit remains a delivery-attempt limit after eligibility, not
   a ledger-read limit.
5. No notification query is issued per candidate.
6. Notification delivery continues to use one PG ledger and one server-monitor
   cadence; no outbox, second timer, or file-backed state is added.
7. One pure function decides the required exchange-order lookup view from the
   typed request.
8. The application and gateway must consume that function; neither may retain
   a second role/type/venue inference table.
9. A result from the wrong view remains contradictory truth and hard-stops.
10. Lookup-view resolution never authorizes a venue, profile, order, or exchange
    write. Existing gateway identity, Owner policy, Runtime Safety State,
    FinalGate, and Operation Layer boundaries remain authoritative.
11. No migration, production JSON/MD reader, recurring report writer, or second
    runtime source is introduced.

## P1 Notification Ledger Repair

### Options

| Option | Benefit | Failure mode | Decision |
| --- | --- | --- | --- |
| Remove only `LIMIT 1000` from the combined exact/legacy query | Smallest edit; closes the reproduced count boundary | Keeps exact identity and compatibility matching coupled; a broad legacy match can still inflate the result and obscure deterministic precedence | Reject |
| Increase the limit to 2,000 or another constant | Very small edit | Moves the failure boundary and does not establish complete exact-key coverage | Reject |
| Split exact-key lookup from compatibility lookup; batch each bounded candidate set | Complete exact coverage, deterministic precedence, no per-candidate query, no schema change | Requires a focused refactor and boundary tests | **Adopt** |

### Adopted Read Algorithm

`_pg_owner_notification_rows` becomes a two-phase resolver.

#### Phase 1: Exact Stable-Key Coverage

1. Deduplicate projected intents by
   `owner_notification_delivery_identity(intent)`.
2. Build one stable `owner_notification_dedupe_key` for each unique intent.
3. Query exact keys in bounded chunks of **500 keys** using
   `WHERE dedupe_key IN (...)` with **no global result limit**.
4. Index the returned rows by exact `dedupe_key`.
5. Resolve every exact match before considering compatibility rows.

The chunk size prevents database parameter-limit surprises while keeping query
count proportional to batches rather than candidates:

```text
exact_query_count = ceil(unique_candidate_count / 500)
```

There is no `LIMIT` because `dedupe_key` is unique and the input key set is
already bounded by the current-state repository inputs.

#### Phase 2: Legacy Correlation Compatibility

Only exact misses enter this phase.

1. Build the existing normalized legacy aliases for unresolved intents.
2. Query aliases in bounded chunks, not one query per intent.
3. Order candidate rows by:

```text
updated_at_ms DESC
created_at_ms DESC
notification_id DESC
```

4. Normalize the returned row correlation and require an exact pair match:

```text
notification_kind + normalized correlation_id
```

5. Select the newest compatible row for each unresolved delivery identity.
6. Never replace an exact stable-key match with a compatibility row.

Compatibility remains a read-and-update bridge for historical pre-fix rows.
It is not a second ledger and has no removal dependency for current stable keys.

### Delivery And Persistence Behavior

The downstream sequence remains:

```text
complete ledger resolution
-> suppress sent/exhausted rows and reopen eligible resolved incidents
-> rank eligible intents
-> select at most five
-> send
-> update existing row or insert genuinely new row
```

An implementation must not use a post-send upsert as the primary repair. An
upsert after the external call could hide an insert collision but cannot undo a
duplicate Feishu delivery. Correct complete lookup is the primary invariant;
the unique constraint remains the database defense.

The design does not add a distributed delivery claim or hold a PG row lock
across Feishu network I/O. No concurrency defect was demonstrated in this
review, and expanding into a new delivery-claim state machine would be a
separate design decision.

### P1 Negative Cases

| Case | Required result |
| --- | --- |
| 1,001 candidates; all exact rows are `sent` | Zero selected, zero Feishu calls, 1,001 suppressed, no insert |
| 1,001 existing sent candidates plus one new critical candidate | Exactly one send for the new candidate; no existing identity resends |
| Exact row and legacy row both match | Exact row wins regardless of timestamps |
| Only a double-prefixed historical correlation row matches | Historical row suppresses or retries according to its persisted state |
| Failed row below retry cap beyond the old 1,000-row boundary | It remains retry-eligible and consumes at most one of five attempt slots |
| Failed row at retry cap beyond the old boundary | It is exhausted and consumes no delivery slot |
| Resolved incident beyond the old boundary becomes active | It reopens once under the existing episode rules |

## P2 Shared Venue Lookup-View Repair

### Options

| Option | Benefit | Failure mode | Decision |
| --- | --- | --- | --- |
| Add `exchange_id` checks only to the application helper | Small edit | Gateway and application still own duplicate policy and can drift again | Reject |
| Trust whatever view the gateway returns | Removes application duplication | A Binance regular-view miss could again masquerade as conditional absence | Reject |
| Define one pure domain resolver and make both application and gateway consume it | One invariant, testable without I/O, preserves contradiction detection | Requires replacing both existing helpers | **Adopt** |

### Pure Resolver

Add one pure function beside the existing typed lookup models in
`src/domain/ticket_bound_exchange_command.py`:

```python
def required_exchange_order_lookup_view(
    request: ExchangeOrderLookupRequest,
) -> ExchangeOrderLookupView:
    ...
```

The function performs no database or network I/O. It uses the canonical
`request.exchange_id`, not the adapter's informal CCXT name.

### Current Resolution Matrix

| Canonical exchange | Command kind | Role/type | Required view |
| --- | --- | --- | --- |
| `binance_usdm` | `place_order` | `ENTRY` or `TP1`, non-`stop_market` | `regular_order` |
| `binance_usdm` | `place_order` | `SL` or `RUNNER_SL`, `stop_market` | `conditional_algo_order` |
| non-Binance adapter identity | `place_order` | Existing supported combinations | `regular_order` |
| any venue | `cancel_order` | Owned target | `complete_open_orders`, handled by the cancel reconciliation path |
| `binance_usdm` | `place_order` | Unsupported role/type combination | Fail closed before lookup |

The non-Binance row preserves the existing regular-client-id adapter contract.
It does **not** authorize any non-Binance live venue. Venue admission and live
authority remain controlled by canonical runtime identity, Owner policy,
gateway binding, and action-time safety.

A future venue with a conditional-order API must extend this resolver with an
explicit canonical venue capability and negative tests. It must not copy the
Binance rule into an adapter-local helper.

### Application Integration

`lookup_unknown_exchange_command` already creates an
`ExchangeOrderLookupRequest`. The application must:

1. resolve the expected view from that typed request;
2. call the gateway with the same request;
3. compare the returned `result.lookup_view` with the resolved expected view;
4. preserve `required_lookup_view_mismatch` as contradictory truth;
5. keep unsupported resolution and lookup exceptions as `lookup_failed` or
   hard-stop according to the existing typed decision contract.

The obsolete `_required_lookup_view_for_command` role/type-only inference is
deleted rather than retained as a compatibility wrapper.

### Gateway Integration

`ExchangeGateway.find_order_by_client_id` must call the same pure resolver and
route the actual readonly request accordingly.

The gateway may translate a pure resolver `ValueError` into its existing typed
`InvalidOrderError/F-011` adapter error, but it must not independently
recalculate the view.

The existing gateway private `_required_lookup_view` is deleted or reduced to a
strict translation wrapper that delegates entirely to the domain resolver. It
must not retain a second decision table.

### P2 Negative Cases

| Case | Required result |
| --- | --- |
| `binance_usdm + SL + stop_market` returns conditional view | Reconciles from conditional evidence |
| `binance_usdm + SL + stop_market` returns regular view | `required_lookup_view_mismatch`; hard stop remains |
| `okx_swap + SL + stop_market` returns regular view | Accepted as the current non-Binance adapter contract |
| `okx_swap + SL + stop_market` returns conditional view | Contradictory view; hard stop |
| Binance unsupported role/type combination | Fails before a regular fallback can occur |
| Missing or malformed canonical exchange identity | Typed request validation or lookup failure; never inferred from symbol |
| Cancel command | Continues through complete normal + conditional open-order visibility, not the place resolver |

## Affected Files

### Allowed Implementation Files After Confirmation

| File | Responsibility | Planned change |
| --- | --- | --- |
| `scripts/run_tokyo_runtime_server_monitor.py` | PG ledger resolution and delivery | Split exact-key and legacy compatibility lookup; remove global truncation |
| `src/domain/ticket_bound_exchange_command.py` | Pure durable-command semantics | Add the shared required-view resolver |
| `src/application/action_time/exchange_command_reconciliation.py` | Unknown-outcome decision | Consume shared resolver and delete duplicate inference |
| `src/infrastructure/exchange_gateway.py` | Venue readonly adapter | Consume shared resolver and delete duplicate inference |
| `tests/unit/test_owner_notification_delivery.py` | Notification delivery integration | Add >1,000 exact/legacy boundary cases |
| `tests/unit/test_ticket_bound_exchange_command_reconciliation.py` | Application reconciliation | Add venue-aware positive and contradictory cases |
| `tests/unit/test_phase5e_exchange_gateway_min_notional.py` | Gateway direct lookup | Prove shared resolution for Binance and non-Binance |
| `tests/unit/test_exchange_gateway_open_order_views.py` | Cancel visibility regression | Prove cancel behavior remains unchanged if needed |
| `docs/current/P0_OWNER_NOTIFICATION_PROJECTION_AND_DELIVERY_CLOSURE_DESIGN.md` | Notification source design | Record the corrective closure and final verification evidence |
| `docs/current/P0_OWNER_NOTIFICATION_PROJECTION_AND_DELIVERY_CLOSURE_IMPLEMENTATION_PLAN.md` | Notification execution plan | Add the remediation test and implementation steps |
| `docs/current/P0_CONDITIONAL_EXCHANGE_COMMAND_RECONCILIATION_CLOSURE_DESIGN.md` | Reconciliation source design | Record the single-resolver correction and final evidence |
| `docs/current/P0_CONDITIONAL_EXCHANGE_COMMAND_RECONCILIATION_CLOSURE_IMPLEMENTATION_PLAN.md` | Reconciliation execution plan | Add the remediation test and implementation steps |

### Forbidden Files And Effects

```text
migrations/versions/**
deploy/systemd/**
live profile or Owner policy files
strategy registry, Event Specs, RequiredFacts, sizing, leverage, or capital code
FinalGate or Operation Layer authority code
protection, emergency-reduce, automatic-close, withdrawal, transfer, or secret code
production JSON/MD readers or recurring report writers
```

If implementation requires a migration, a new notification state machine, a
new venue permission, or a file outside the allowed scope, implementation stops
and this design returns for revision.

## Test-First Execution Specification

### Task A: P1 Notification Coverage

1. Add the 1,001-sent-row regression and verify it fails under the current
   global `LIMIT 1000` behavior.
2. Add the old-boundary-plus-one-new-card regression and verify the current code
   either resends or collides incorrectly.
3. Implement exact-key chunking and unresolved-only compatibility lookup.
4. Run delivery tests and prove zero duplicate calls and zero insert conflicts.
5. Add exact-over-legacy precedence and normalized historical-row tests.

### Task B: P2 Shared Required View

1. Add a non-Binance `SL + stop_market + regular_order` application test and
   verify the current application hard-stops it.
2. Add direct pure-resolver matrix tests.
3. Implement the pure resolver and replace application/gateway inference.
4. Prove Binance wrong-view evidence still hard-stops.
5. Prove non-Binance regular evidence no longer hard-stops.

### Required Verification Commands

```bash
pytest -q tests/unit/test_owner_notification_delivery.py
pytest -q \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py \
  tests/unit/test_phase5e_exchange_gateway_min_notional.py \
  tests/unit/test_exchange_gateway_open_order_views.py
pytest -q \
  tests/unit/test_owner_notification.py \
  tests/unit/test_owner_notification_scenarios.py \
  tests/unit/test_owner_notification_delivery.py \
  tests/unit/test_runtime_monitor_frequency_policy.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py \
  tests/unit/test_phase5e_exchange_gateway_min_notional.py \
  tests/unit/test_exchange_gateway_open_order_views.py
pytest -q tests/unit
python3 scripts/validate_current_docs_authority.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 scripts/audit_production_runtime_file_io.py --fail-on-risk
git diff --check
```

No Tokyo, Feishu, or exchange network call is part of local acceptance.

## Cadence And Performance Impact

| Dimension | Notification repair | Venue resolver repair | Acceptance target |
| --- | --- | --- | --- |
| Cadence | Existing server monitor, every 10 minutes | Only when an unknown durable command is reconciled | Unchanged |
| PG reads | Batched exact-key reads plus unresolved-only legacy reads | Existing command read only | No per-candidate query; no history-wide scan |
| PG writes | Existing delivery update/insert only after selected attempt | Existing command transition only after typed truth | No new table or recurring row family |
| Network | Existing maximum five Feishu attempts with current timeout | Existing one readonly order lookup per unknown place command | No new endpoint or write call |
| CPU | Set/map resolution over bounded current candidates | One pure enum decision | Negligible and bounded |
| No-signal file writes | Zero | Zero | **0 JSON/MD/YAML/JSONL files** |
| Disk/retention | Existing PG notification retention | Existing command/event retention | Unchanged |
| Subprocess timeout | Existing monitor timeout behavior | Not applicable | Unchanged |

The implementation review must keep
`suspicious_runtime_file_authority=0`, `frequent_report_write=0`, and production
performance risk clear.

## Rollout And Rollback

### Local Phase After Confirmation

1. Implement on the existing isolated branch
   `codex/release-risk-analysis-20260714`.
2. Use TDD for each finding and commit the two repairs separately.
3. Run targeted, combined, full-unit, current-doc, output-scope, file-I/O, and
   diff checks.
4. Produce a new review result and stop before deployment.

### Local Implementation Evidence — 2026-07-14

| Checkpoint | Result |
| --- | --- |
| P1 RED | The 1,001-sent-row regression failed on the old global-limit query with a duplicate `dedupe_key` insert for an omitted sent row |
| P1 GREEN | Exact-key chunked lookup plus unresolved-only legacy lookup suppressed all 1,001 sent rows and delivered one genuinely new card beyond that boundary |
| P2 RED | A non-Binance `SL + stop_market + regular_order` result was incorrectly hard-stopped by the old application-only role/type inference |
| P2 GREEN | One pure domain resolver is consumed by both application and gateway; the non-Binance regular result now reconciles while a Binance wrong view remains contradictory truth |
| Focused suites | `66 passed` and `164 passed` |
| Full unit suite | `3139 passed, 1 skipped, 3 warnings, 0 failed` in `616.53s` |
| Current docs/output/file-I/O | All validation commands passed; `suspicious_runtime_file_authority=0`, `frequent_report_write=0` |
| Tokyo/Feishu/exchange access | None |

### Deployment Boundary

Local acceptance does not authorize deployment. The current Tokyo Release
continues handling new entries under its existing gates and policies.

A later explicit deployment phase must:

1. identify the exact tested commit;
2. read-only check current Ticket, position, open-order, unknown-command, and
   monitor state;
3. deploy through the current Tokyo deployment contract;
4. verify service/timer health and current PG notification behavior without
   sending a synthetic production card or creating a synthetic production
   order;
5. preserve any unknown exchange outcome and its hold during rollback.

### Rollback

No migration is introduced, so rollback is code-only:

- restore the previous release code and service definition set;
- do not delete or rewrite notification ledger rows;
- do not clear unknown commands or domain holds;
- do not reinterpret a conditional-order miss as absence;
- forward-fix any ambiguous delivery or exchange-truth state.

## Authority And Live-Enablement Boundary

```text
chain_position:
  owner_notification_delivery + durable_exchange_command_reconciliation

live_enablement_state_before:
  two local release packages implemented and tested, but review found one
  notification reliability blocker and one venue-contract defect

blocker_removed_after_future_local_acceptance:
  owner_notification_ledger_exact_coverage_gap
  exchange_lookup_view_single_authority_gap

live_enablement_state_after_future_local_acceptance:
  release candidate is locally corrected and reviewable; Tokyo remains on the
  current Release until a separate deployment decision

capability_unlocked:
  complete notification dedupe coverage for the bounded current candidate set
  one shared venue-aware readonly order lookup-view contract

owner_action_required:
  confirm local implementation scope only

authority_boundary:
  no production intervention, no notification-policy expansion, no new venue
  admission, no exchange write, no strategy/capital/leverage/profile/scope
  change, no automatic emergency reduce or automatic close
```

## Acceptance

The remediation is complete only when all conditions are true:

1. The 1,001-sent-row test selects zero notifications and makes zero notifier
   calls.
2. A new eligible card beyond 1,000 existing sent rows is delivered once.
3. Exact stable-key matches always outrank compatibility matches.
4. No global result limit can omit an exact candidate key.
5. Notification delivery remains capped at five eligible attempts per run.
6. One pure resolver is the only required-view decision authority.
7. Binance conditional commands cannot be proven absent through a regular view.
8. Non-Binance regular-view evidence is judged consistently by application and
   gateway.
9. Contradictory result views still hard-stop.
10. Cancel reconciliation remains on complete open-order visibility.
11. No new schema, runtime source, report writer, service unit, exchange write,
    policy change, or live-scope expansion is introduced.
12. Targeted and full unit tests pass, current document authority validates,
    output scope validates, production file-I/O risk remains clear, and
    `git diff --check` passes.

## Design-Stage Validation Evidence

The design-only worktree was checked before the confirmation gate:

| Check | Result |
| --- | --- |
| Current document authority | `current_docs_authority_valid` |
| Output artifact scope | `output_artifact_scope_valid` |
| Production runtime file-I/O audit | `suspicious_runtime_file_authority=0`, `frequent_report_write=0` |
| Runtime/code modification | None; this design document is the only worktree change |
| Tokyo/Feishu/exchange access | None |

## Confirmation Gate

Local implementation and certification are complete. Deployment, service
mutation, production PG mutation, real Feishu delivery, and exchange access
remain outside this document pending a separate Owner release decision.
