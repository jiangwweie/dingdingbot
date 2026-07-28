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
state machine. The current no-write proof uses the accepted authority boundary:
an uncertified instrument remains `pending_certification` with a warming,
`entry_enabled = false` scope, so the official chain creates neither Ticket nor
durable Exchange Command. Existing Ticket protection/exit/reconciliation
continues independently of current Universe membership.
