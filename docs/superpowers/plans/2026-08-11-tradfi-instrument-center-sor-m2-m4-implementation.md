# M1-M4 TradFi Instrument Center And SOR Implementation

## Goal

Implement the Owner-approved same-Venue TradFi Equity Perpetual product surface,
versioned instrument/strategy decoupling, and observation-only
`SOR-US-EQ-PERP-001` without production deployment or real Entry authority.

## Allowed files

- `docs/current/MULTI_ASSET_STRATEGYGROUP_ROADMAP.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`
- `docs/superpowers/specs/2026-08-11-binance-usdm-tradfi-perpetual-m1-decision.md`
- `docs/superpowers/specs/2026-08-11-tradfi-instrument-center-sor-m2-m4-design.md`
- `docs/superpowers/plans/2026-08-11-tradfi-instrument-center-sor-m2-m4-implementation.md`
- `src/trading_kernel/**`
- `migrations/trading_kernel/**`
- `scripts/trading_kernel/**`
- `frontend/owner-console/**`
- focused `tests/trading_kernel/**`

## Forbidden changes

- Production deployment or server mutation.
- Exchange write, account agreement acceptance, credential mutation or capital expansion.
- Enabling TradFi new Entry.
- Restoring Crypto `SOR-001`.
- Porting MPG, BRF2, CPM, MI or RSRVCB in this task.
- A second execution chain, worker family, schema fallback or file-backed authority.

## Work packages

1. Record M1 Owner adoption and future strategy backlog.
2. Add Product Compatibility and product/session current projection.
3. Add observation-only RuntimeProfile/Policy/control and two US SOR Events.
4. Enforce compatibility at Universe installation.
5. Add typed product source and US SOR detector/ExitPolicy behavior.
6. Add bounded Instrument Center and Universe control API.
7. Add dark dense Instrument Center UI and strategy product summaries.
8. Run only focused red/green tests and proportional static/build checks.

## Done when

- Design acceptance items pass.
- Existing Crypto semantics remain unchanged.
- Worktree contains a reviewed local candidate and remains undeployed.
