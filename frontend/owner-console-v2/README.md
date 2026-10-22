# Owner Console V2

Owner Console V2 is the active static frontend served at `/trading/`.
The prior `frontend/owner-console` source remains retired and retained; the
R1 certification and deployment path builds V2 only.

## Product surfaces

- Overview: account and active Tickets with causality and candlestick review.
- Trades / Strategies: historical windows, URL filters, cursor pagination,
  and inherited Ticket / Observation queries.
- Review: completed Ticket evidence and exact decimal summaries.
- Controls: strategy ENTRY pause/resume, global ENTRY pause/resume,
  guarded flatten-all, Dynamic selection and certified Static rollback.

Control mutations call the existing same-origin Owner API. Session, TOTP,
version checks, frozen idempotency identities and unknown-result lockdown
remain enforced. Deploying the UI does not change any control state.
Single-Ticket flatten is unavailable. Production control-write acceptance is
separate from mocked tests and static deployment.

## Local development and verification

```bash
pnpm --dir frontend/owner-console-v2 install --frozen-lockfile
pnpm --dir frontend/owner-console-v2 exec tsc -b
pnpm --dir frontend/owner-console-v2 build
./frontend/owner-console/node_modules/.bin/vitest run --dir frontend/owner-console-v2
```

The Vite development/preview proxy points to the production Owner API.
Use isolated request mocks for control tests; do not use production writes as
part of a build or deployment smoke. Production static assets use `/trading/`;
API requests retain `/api/owner/v1/` at the origin root.

## Release and rollback

The official entry points are
`scripts/owner_console/certify_static_release_candidate.py` and
`scripts/owner_console/deploy_release.py --kind static`. Both use an exact,
clean commit. The deployer builds that commit in a disposable directory,
installs the immutable static release and switches only the static symlink.
A failed smoke restores the previous static release. Kernel workers, Owner
API, PostgreSQL and exchange controls are not changed by a static release.

Current production identity is recorded only in
`docs/current/MAIN_CONTROL_ROADMAP.md`.

## Trade explanations and Review coverage

The Owner read API owns exit attribution across Trades, Strategies and Review.
An explicit `ExitRequested` reason has its exact event evidence. Otherwise a
terminal Ticket may be attributed only from its current Review's complete exit
fills and exact same-Ticket order commands. Conditional Algo IDs and actual fill
Order IDs are distinct; the persisted Review owns their association. Missing,
partial, duplicate or ambiguous facts remain unknown. Frozen time-stop details
come from the Ticket's exact Profile ID and semantic hash, never today's Binding.

Execution evidence and economic evidence are independent. A funding gap does
not make the execution chain incomplete; a missing exit cause does not erase
confirmed PnL. Review completeness still requires both dimensions. Raw reasons,
authorization IDs and evidence remain available in details.

All income surfaces use terminal timestamps in Asia/Shanghai. The full-window
`GET /api/owner/v1/performance` summary is independent of detail page size/cursor,
includes Owner flatten by default, and retains all/current version and explicit
exit-scope filters. Strategy, Owner, safety and unknown exit classes are mutually
exclusive; unknown is never treated as a strategy-natural exit.

Each metric independently reports covered/missing Tickets and exact 80-digit
verified sums. Unknown funding never becomes zero. The API bounds each window
to 90 days and 5000 Tickets, failing explicitly instead of silently truncating.
A content fingerprint binds the population, current Review revision, economics,
classification and effective filters. Detail GETs validate this fingerprint in
their readonly transaction; changed facts return 409 statistics_snapshot_changed.
The UI stops paging and requires a whole-query refresh, not a blind old-cursor
retry. Strategy matrix and its full summary share one read transaction. Overview
headlines and group contributions use the same income snapshot; delayed Review
revisions revise the original terminal period rather than today's income.

Cross-page navigation and copied links retain exact timestamps and supported
identity/scope filters. Profit statistics exclude unfilled terminal attempts and
unrealized positions; current managed exposure is independently resolved from
Overview and exact causality reads. Cumulative single-Ticket Net R is not account
return. No historical Review, policy, schema or exchange state is rewritten.

If a row's net PnL is unavailable because funding evidence is incomplete but gross PnL
is known, its PnL cell displays the gross amount with `（资费不完整）` and an
explicit gross label. The underlying net value stays null, Net R stays unknown,
and gross never enters net totals or win/loss classification.
