> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical roadmap, readiness, rehearsal, safety, or phase artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
>
> * `docs/canon/PROJECT_BASELINE_CURRENT.md`
> * `docs/canon/BRC_TARGET_SEMANTICS.md`
> * `docs/canon/AGENT_WORKSPACE_RULES.md`
> * `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> * `docs/canon/TECH_DEBT_BASELINE.md`
> * `docs/canon/DOCUMENT_GOVERNANCE.md`

# PLC Phase 5C Two-Symbol Synthetic Fixture Proof

Date: 2026-05-25
Status: REVIEW / SYNTHETIC_FIXTURE_PASSED

## Boundary

Phase 5C is a local synthetic proof. It does not authorize real live trading,
mainnet order placement, real-funds operation, runtime profile changes,
credential changes, transfer, withdrawal, multi-symbol runtime, portfolio
routing, or strategy-return optimization.

No Binance testnet action is required for this phase. Phase 5C proves local
symbol-isolation behavior only.

## Goal

Close the Phase 5B remaining proof gap:

- reconciliation must not report BTC mismatches inside an ETH read model;
- runtime read models must respect symbol filters for positions, orders, and
  execution intents;
- portfolio remains explicitly account-level aggregation;
- multi-symbol runtime remains blocked until Owner separately authorizes an
  exchange-connected multi-symbol rehearsal or profile/config change.

## Implemented Scope

- Added optional `symbol` filtering to runtime positions read model and
  `/api/runtime/positions`.
- Added optional `symbol` filtering to runtime execution-intents read model and
  `/api/runtime/execution/intents`.
- Added Phase 5C symbol-isolation audit verdict:
  `two_symbol_synthetic_fixture_passed / multi_symbol_runtime_still_blocked`.
- Added local BTC/ETH synthetic fixture tests covering:
  - reconciliation `build_read_model(symbol)` isolation;
  - runtime orders symbol filtering;
  - runtime execution intents symbol filtering;
  - runtime positions symbol filtering;
  - portfolio account-level aggregation over two symbols.

## Verification

Local verification:

```bash
python3 -m compileall -q \
  src/application/readmodels/runtime_execution_intents.py \
  src/application/readmodels/runtime_positions.py \
  src/interfaces/api_console_runtime.py \
  src/application/runtime_symbol_isolation_audit.py \
  tests/unit/test_phase5c_two_symbol_fixture.py

pytest -q \
  tests/unit/test_phase5c_two_symbol_fixture.py \
  tests/unit/test_phase5b_symbol_isolation.py
```

Result:

- `8 passed`.

## Remaining Blocks

Phase 5C does not unblock multi-symbol runtime by itself.

Still blocked:

- multi-symbol runtime profile;
- exchange-connected two-symbol rehearsal;
- multi-symbol order placement;
- portfolio/router behavior;
- any real-live discussion.

Required before any multi-symbol runtime step:

- Owner authorization for the exact exchange-connected action;
- runtime profile/config change review;
- account-risk cap review for multi-position exposure;
- operational stop conditions and rollback plan.

## Verdict

`phase5c_two_symbol_synthetic_fixture_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`
