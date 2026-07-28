# Task 6 Report: Dynamic Binance USD-M Instrument Routing

## Scope

Implemented only **Task 6** from
`docs/superpowers/plans/2026-07-28-crypto-strategy-universe-implementation.md`.
No installer, certification worker, warming, activation, Tokyo, production, or
exchange action was performed.

## Invariants Preserved

- **Registry is not instrument-membership authority.**
- **Binance USD-M routing uses the strict canonical InstrumentCodec.**
- **Codec success is identity parsing, not Entry eligibility.**
- **Pending-certification / warming scope cannot issue a Ticket or durable
  command and therefore cannot reach Venue mutation.**
- **Existing Ticket safety authority survives removal from the active
  Universe.**
- **Illegal instrument identity fails before account routing and before any
  Venue write.**

## Changes

- Unified `CcxtVenueAdapter.execute()` with the same strict
  `_resolve_exchange_and_symbol()` path used by all other authenticated venue
  operations.
- Moved canonical codec resolution before venue/account adapter selection.
- Removed the remaining fixed-map wording from strict routing errors.
- Made the shared Ticket integration fixture derive `venue_symbol` from the
  canonical codec instead of hard-coding `BTCUSDT`.
- Added dynamic OPUSDT coverage for production public-market and authenticated
  rule factories.
- Added PostgreSQL-backed integration coverage for uncertified warming
  rejection and removed-Universe Ticket exit/reconciliation.

`production_runtime.py` and `binance_public_market_source.py` were already
map-free at the start of Task 6 due to the preceding Task 4 repair commit
`ef29132a`; this task preserved that state and added executable contracts rather
than reintroducing a second change.

## RED / GREEN Evidence

### RED

```text
pytest -q tests/trading_kernel/unit/test_venue_adapter.py::test_ccxt_adapter_rejects_illegal_instrument_before_account_routing
```

Result: **1 failed**. The invalid `OP/USDT:USDT` identity incorrectly reached
account routing first and raised `venue/account adapter is not configured`.

### Minimal GREEN

The same command then returned **1 passed** after strict codec resolution was
moved ahead of account routing.

## Verification

### Focused tests

```text
pytest -q \
  tests/trading_kernel/unit/test_instrument_identity.py \
  tests/trading_kernel/unit/test_binance_public_market_source.py \
  tests/trading_kernel/unit/test_production_runtime.py \
  tests/trading_kernel/unit/test_venue_adapter.py \
  tests/trading_kernel/integration/test_dynamic_instrument_routing.py \
  tests/trading_kernel/integration/test_issue_ticket.py::test_issue_ticket_claims_global_lane_and_reserves_budget_atomically
```

Result: **62 passed**.

Fresh rerun of the new PostgreSQL integration file:

```text
pytest -q tests/trading_kernel/integration/test_dynamic_instrument_routing.py
```

Result: **3 passed**.

### Ruff

Core correctness gate:

```text
uvx --from 'ruff>=0.15.0' ruff check --select E4,E7,E9,F \
  tests/trading_kernel/integration/test_dynamic_instrument_routing.py \
  src/trading_kernel/infrastructure/venue_adapter.py \
  tests/trading_kernel/unit/test_production_runtime.py \
  tests/trading_kernel/unit/test_venue_adapter.py \
  tests/trading_kernel/integration/test_issue_ticket.py
```

Result: **All checks passed**.

The new integration file also passed import-order checking with
`--select E4,E7,E9,F,I`.

A full-rule scoped Ruff run with the newly resolved `ruff>=0.15.0` executable
reported **107 pre-existing style findings**, primarily `TRY004`, `FURB157`,
and old import ordering across the large existing adapter/test files. Those
unrelated files were not mechanically reformatted in Task 6.

### Static and diff gates

- `git diff --check`: **passed**.
- No `_EXPECTED_UNIQUE_INSTRUMENTS`, production `venue_symbols`,
  `candidate_instruments`, or `InstrumentPriority` authority exists in the
  Task 6 production routing files.

## Remaining Boundary

Task 6 does not implement the Task 7 certification worker or Task 9 activation
state machine. The current no-write proof uses the existing formal
certification-derived instrument status while deliberately keeping Universe,
Scope, Policy, and Entry authority active. Task 7 will own refreshing that
status from readonly venue facts, and Task 9 will own complete activation.
Existing Ticket protection/exit/reconciliation continues independently of
current Universe membership.

## Review Fix Round 1/5

### Important 1: protection after Universe replacement

The original test protected the Ticket before retiring its Universe, so it did
not prove the required safety boundary.

The replacement RED now performs:

```text
durable ENTRY accepted
-> replace current Universe and retire the Ticket's old Scope/Universe
-> official reconciliation records the fill
-> reducer prepares durable INITIAL_STOP
-> dispatcher submits INITIAL_STOP through strict codec
-> TP1
-> EXIT
-> flat readonly reconciliation
```

The first RED was blocked by
`brc_fence_universe_pointer_during_entry()` because it treated every held ENTRY
lane as an unresolved Entry mutation, even after the durable ENTRY command was
already accepted.

The fence now blocks activation only while the Ticket owns an unresolved
`SET_LEVERAGE` or `ENTRY` command in `prepared`, `claimed`, or
`outcome_unknown`. Once ENTRY is durably accepted, Universe replacement may
proceed while the still-held global lane continues to prohibit every new
Ticket until Initial Stop protection resolves.

### Important 2: certification as the isolated Entry gate

The original test simultaneously removed the current pointer, changed the
Universe to warming, disabled Entry, and marked the instrument
`pending_certification`; it therefore did not prove certification was
load-bearing.

The corrected RED keeps all other authority valid:

- current Universe remains active and points to the Ticket's version;
- Runtime Scope remains `active` with `entry_enabled = true`;
- Owner Policy and runtime Entry authority remain enabled;
- only `brc_instruments.status` changes to `pending_certification`.

Before the fix, `issue_ticket()` returned `ISSUED`. The active-member selector
now joins and locks the exact instrument row and returns membership only when
`brc_instruments.status = 'active'`. The corrected chain returns
`SCOPE_OR_POLICY_MISMATCH` and proves **zero Ticket, zero Exchange Command, and
zero Venue calls**.

This is the smallest Task 6 formal source: the accepted design already defines
`pending_certification -> active` on `brc_instruments` as the current
certification-derived eligibility projection. Task 7 still owns how readonly
venue facts refresh that projection; Task 9 still owns the complete
certification/readiness activation transaction.

### Round 1 RED / GREEN

The two corrected tests initially failed with:

1. pending certification alone still returned `IssueTicketStatus.ISSUED`;
2. post-acceptance Universe replacement raised
   `ck_brc_universe_activation_entry_lane_idle`.

After the two minimal production changes, the same focused command returned
**2 passed**.

### Report location

The committed root report was moved with `git mv` to:

```text
.superpowers/sdd/2026-07-28-crypto-strategy-universe-implementation/task-6-report.md
```

### Round 1 final verification

The final focused PostgreSQL/unit command covered the dynamic routing contracts,
the claimed-ENTRY activation fence, active-instrument signal eligibility,
atomic Ticket admission, and a clean forward-only schema upgrade:

```text
65 passed in 7.01s
```

The changed migration, repository, and integration test passed Ruff core
correctness (`E4`, `E7`, `E9`, `F`); the changed integration test also passed
import ordering (`I`). `git diff --check` passed.

## Review Fix Round 2/5

### PostgreSQL migration-trigger state matrix

The previous suite proved only that an ENTRY command claimed during preflight
blocked a current-Universe pointer mutation. It did not explicitly cover every
unresolved mutation state or the accepted boundary.

A real PostgreSQL parameterized matrix now persists and verifies:

| Durable command | Status | Pointer result |
|---|---|---|
| `SET_LEVERAGE` | `prepared` | rejected, SQLSTATE `55000` |
| `SET_LEVERAGE` | `claimed` | rejected, SQLSTATE `55000` |
| `SET_LEVERAGE` | `outcome_unknown` | rejected, SQLSTATE `55000` |
| `ENTRY` | `prepared` | rejected, SQLSTATE `55000` |
| `ENTRY` | `claimed` | rejected, SQLSTATE `55000` |
| `ENTRY` | `outcome_unknown` | rejected, SQLSTATE `55000` |
| `ENTRY` | `accepted` | allowed |

Every rejected transaction also proves the current pointer remains on the
original Universe; the accepted transaction proves it advances to the seeded
replacement Universe. No production behavior changed in Round 2.

### Lane ownership during protection creation

The accepted-switch lifecycle test now seeds a second otherwise-valid short
Ticket before dispatching the original dynamic OP Ticket. Immediately after
the old Universe/Scope is retired, and before fill reconciliation creates the
Initial Stop, the test proves:

- the global Entry lane remains `claimed`;
- the lane still names the original Ticket;
- issuing the second Ticket returns `ENTRY_LANE_OCCUPIED`.

The lifecycle then continues through official fill reconciliation, durable
Initial Stop generation and dispatch, TP1, Exit, and flat readonly
reconciliation.

### Round 2 RED / GREEN and final verification

The coverage RED found that the suite had only one ENTRY/claimed fence case and
no explicit accepted boundary or second-Ticket proof. The first enhanced
lifecycle run then exposed a duplicate BTC Instrument insertion in the test
fixture. Removing that redundant test-data insert produced:

```text
8 passed in 7.09s
```

The final focused Task 6, schema, lifecycle, and routing command returned:

```text
72 passed in 12.88s
```

Both changed integration files passed Ruff `E4`, `E7`, `E9`, `F`, and `I`.
`git diff --check` passed, and the Round 2 diff contains no production-code
change.
