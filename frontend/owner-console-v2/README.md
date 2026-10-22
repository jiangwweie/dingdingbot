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

Review responses describe one returned page (`summary_scope=page`). The UI
combines deduplicated loaded Tickets (`summary_scope=loaded_records`); it never
claims a full-window total before all pages are loaded. Each metric has its own
coverage and missing Ticket IDs. Strict totals remain unavailable when incomplete;
`verified_totals` separately carries clearly labelled partial sums. Unknown
funding is never zero. No historical Review, economic fact or trade policy is
rewritten by these read models.
