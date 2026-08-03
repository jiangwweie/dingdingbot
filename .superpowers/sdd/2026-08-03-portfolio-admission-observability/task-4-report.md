## Task 4 Report — Portfolio Admission Policy v4

### Scope and authority

- Implemented **Policy v4**, **ExposureFamily**, directional stop-risk capacity, and post-rounding minimum materialization in the existing Trading Kernel path.
- Extended the already un-deployed **`0003_portfolio_admission_observability`** migration. No `0004` migration was created.
- Left **`CURRENT_SCHEMA_REVISION`** unchanged, as required: the identity switch belongs to Task 6.
- Did not deploy, alter production state, enable Entry, or perform any exchange mutation.

### Changes

- Added the typed **`ExposureFamily`** identity and exact per-family ticket limits.
- Replaced current admission usage of strategy-group capacity with bounded active-family count and active directional stop-risk selectors.
- Added Policy v4 fields: `family_ticket_limits`, `directional_stop_risk_limit_fraction`, and `min_materialization_ratio`.
- Enforced deterministic family and direction capacity blockers before sizing, and minimum materialization after risk, margin, and instrument rounding.
- Froze Policy v4 family/directional/minimum-materialization lineage into each Capacity Claim and Ticket; Claim-to-Ticket conversion preserves it.
- Revalidated frozen v4 limits at Ticket issuance and immediately before command dispatch.
- Added the current Ticket indexes for active family and directional-risk selectors; legacy StrategyGroup columns remain only nullable historical physical fields and are not current admission authority.
- Updated readonly certification to read Policy v4 fields only, without changing certification/deployment topology.
- Validated persisted exposure-family values during repository rehydration.

### TDD evidence

1. RED:
   `pytest tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_capacity_sizing.py -q`
   initially produced **11 failed, 13 passed**, demonstrating that existing sizing did not enforce the new materialization semantics.
2. GREEN:
   the same command produced **26 passed** after policy/sizing implementation.
3. The added materialization boundary covers wallet **1000**, target risk **20**, gross stop-risk **60**, directional limit **40**, and materialization floor **10**: post-rounding **9.99** rejects while **10.00** proceeds.

### Fresh verification

| Command | Result |
| --- | --- |
| `pytest tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_capacity_sizing.py -q` | **26 passed** |
| `pytest tests/trading_kernel/unit/test_entry_dispatch_preflight.py -q` | **7 passed** |
| `pytest tests/trading_kernel/integration/test_issue_ticket.py tests/trading_kernel/integration/test_command_dispatch.py tests/trading_kernel/integration/test_signal_to_ticket.py -q` | **65 passed** |
| `.venv/bin/mypy` over all changed kernel sources | **Success: no issues found in 13 source files** |
| `.venv/bin/ruff check` over changed Task 4 source, migration, script, and tests | **All checks passed** |
| `python3 -m compileall -q src/trading_kernel migrations/trading_kernel scripts/trading_kernel` | **passed** |
| `git diff --check` | **passed** |

### Requirement audit

- **CAP-001 through CAP-014:** covered by the 26-passing pure Capacity/Sizing suite, including exact minimum-materialization boundary values.
- **Family selector:** repository query is bounded by `venue_id`, `account_id`, `exposure_family`, and `terminal_at_ms IS NULL`.
- **Directional selector:** repository aggregation is bounded by `venue_id`, `account_id`, `position_side`, and `terminal_at_ms IS NULL`.
- **Policy seed:** current dynamic values are concurrent **3**; family limits **1/2/1**; ticket/gross stop risk **2%/6%**; ticket/gross initial margin **30%/90%**; directional risk **4%**; materialization **50%**.
- **Lineage:** Claims and Tickets store the exact family count/limit, directional risk/fraction, materialization ratio, and computed minimum stop-risk budget.
- **Legacy authority:** current application and readonly certification no longer use `max_strategy_group_concurrent_tickets`; physical legacy Claim fields remain historical-only and nullable.

### Known cross-task concerns

The requested combined command remains **15 passed, 2 failed**:

```text
pytest tests/trading_kernel/integration/test_capacity_claim_to_ticket.py \
  tests/trading_kernel/integration/test_runtime_authority_seed.py \
  tests/trading_kernel/integration/test_entry_promotion_gate.py -q
```

1. `test_readonly_certification_emits_exact_pending_closure_manifest` fails because Alembic resolves head to **`0003_portfolio_admission_observability`** while **`CURRENT_SCHEMA_REVISION`** remains **`0002_sor_v3_strategy_group_capacity`**.
2. `test_entry_promotion_rehearses_arm_failure_resume_and_idempotence` consequently receives `entry_promotion_gate_failed` instead of the downstream fenced-entry status expected by the test.

These are Task 6/Task 7 certification-topology dependencies. This task intentionally did not create `0004`, change `CURRENT_SCHEMA_REVISION`, or alter deployment/promotion behavior to mask the mismatch.
