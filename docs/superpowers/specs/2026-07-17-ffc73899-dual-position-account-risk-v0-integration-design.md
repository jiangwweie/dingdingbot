# FFC73899 And Dual-Position Account Risk V0 Integration Design

Status: **OWNER-REQUESTED PLAN BASELINE; ISOLATED WORKTREE CREATED; MERGE NOT STARTED**

Date: **2026-07-17**

Integration worktree:
`/Users/jiangwei/Documents/brc-merge-ffc73899-dual-position-risk-v0`

Integration branch:
`codex/integrate-ffc73899-dual-position-risk-v0`

## Executive Decision

The selected design is a **release-first, exact-commit, isolated integration**:

```text
release base ffc73899
-> merge exact budget head 5b67181e without touching either source branch
-> preserve release migrations 121-125
-> renumber budget migrations 121-128 to 126-133
-> preserve release runtime/lifecycle semantics
-> add account-capacity semantics through the existing Ticket/FinalGate chain
-> certify locally with PostgreSQL and the complete regression suite
-> stop before deployment or Owner policy activation
```

The integration is not performed in either source worktree. The source branch
histories are not rebased, reset, amended, or force-updated.

## Frozen Inputs

| Input | Exact identity | Treatment |
| --- | --- | --- |
| Release base | `ffc73899f2749208074a06b9c7384e74911a400d` | First parent of the integration merge |
| Budget source | `5b67181e2d287fb306bae953075c89e2c6be32ab` | Second parent of the integration merge |
| Common ancestor | `2001644581cccc968ba695d3ff129960db6a7e84` | Three-way merge base |
| Current moving release head | `fdad0e9346203421319044d70e5e33d99925e485` | Explicitly excluded from this merge scope |
| Source worktree with local change | `codex/release-risk-analysis-20260714` | `requirements-runtime.lock` remains untouched |

The moving release delta currently contains `faf49004`, `32cc84fd`, and
`fdad0e93`. It receives a separate post-integration intake review only after the
`ffc73899 + 5b67181e` merge is locally green. This prevents a moving release
target from changing the meaning of the current integration.

## Verified Merge Shape

| Dimension | Verified value |
| --- | ---: |
| Release-only commits | `88` |
| Budget-only commits | `41` |
| Files changed on both sides | `38` |
| Textual conflict hunks | `23` |
| Files with textual conflicts | `17` |
| Release migration files at `ffc73899` | `125` |
| Budget migration files at `5b67181e` | `128` |
| Required integrated migration head | `133` |

## Alternatives Considered

| Approach | Benefit | Cost | Decision |
| --- | --- | --- | --- |
| Merge inside the release worktree | Fewest directory operations | Pollutes a moving release line and risks staging its local lockfile change | Rejected |
| Rebase 41 budget commits onto release | Fine-grained history | Rewrites the source branch and repeats conflicts across many commits | Rejected |
| Cherry-pick selected budget commits | Can omit unwanted changes | Risks losing cross-commit invariants and no longer represents a true branch merge | Rejected |
| Exact two-parent merge in a sibling worktree | Preserves both histories and isolates all mutations | One large conflict-resolution checkpoint requires strict semantic review | Selected |

## Authority And Runtime Boundary

The merge adds locally testable account-capacity capability. It does not change
production authority.

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

The integrated branch must preserve these facts:

- existing StrategyGroup, symbol, side, profile, notional, and leverage scope;
- the current single open real-submit Action-Time lane;
- one Ticket as the business lifecycle owner;
- one durable exchange-command authority;
- FinalGate input by `ticket_id`;
- Operation Layer input by `ticket_id + finalgate_pass_id`;
- existing protection, exit, reconciliation, settlement, and review behavior;
- PG/current as the only production runtime authority;
- zero production JSON/Markdown authority and zero no-signal report-file growth.

The merge must not activate the two-position policy, change the production
single-position/3% baseline, create exchange writes, alter credentials, perform
withdrawals or transfers, or deploy to Tokyo.

## Migration Architecture

Both branches define Alembic revisions `121` through `125` after revision
`120`. The release chain is already the selected base and remains immutable.

| Budget source file | Integrated file | Revision edge |
| --- | --- | --- |
| `2026-07-14-121_create_account_risk_policy.py` | `2026-07-17-126_create_account_risk_policy.py` | `125 -> 126` |
| `2026-07-14-122_create_account_risk_current_projections.py` | `2026-07-17-127_create_account_risk_current_projections.py` | `126 -> 127` |
| `2026-07-14-123_repair_terminal_budget_reservations.py` | `2026-07-17-128_repair_terminal_budget_reservations.py` | `127 -> 128` |
| `2026-07-14-124_add_account_capacity_reservation_scope.py` | `2026-07-17-129_add_account_capacity_reservation_scope.py` | `128 -> 129` |
| `2026-07-14-125_add_account_capacity_claim_policy_event.py` | `2026-07-17-130_add_account_capacity_claim_policy_event.py` | `129 -> 130` |
| `2026-07-15-126_expand_asset_neutral_account_risk_identity.py` | `2026-07-17-131_expand_asset_neutral_account_risk_identity.py` | `130 -> 131` |
| `2026-07-15-127_backfill_asset_neutral_account_risk_identity.py` | `2026-07-17-132_backfill_asset_neutral_account_risk_identity.py` | `131 -> 132` |
| `2026-07-15-128_enforce_asset_neutral_account_risk_identity.py` | `2026-07-17-133_enforce_asset_neutral_account_risk_identity.py` | `132 -> 133` |

The budget-side modification of
`migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py`
is not accepted. Historical revision `086` is restored byte-for-byte from
`ffc73899`. The exact-instrument column and constraints are delivered only by
forward revisions `131-133`.

Acceptance requires one Alembic head, release-like upgrade `125 -> 133`, fresh
upgrade `base -> 133`, and disposable PostgreSQL downgrade/upgrade proof. No
production rollback may revive old schema or file authority.

## Conflict Resolution Architecture

### Release-owned semantics

The following release behavior always survives conflict resolution:

- TP1 reprice idempotency and current repriced-order reconciliation;
- active Ticket exit-policy adoption and exit-protection generation lineage;
- lifecycle runner maintenance, durable command identity, and unknown-outcome
  reconciliation;
- bounded gateway/runtime assembly, watcher cadence, and deployment writer
  fencing;
- exact certified `ccxt==4.5.56` adapter behavior;
- exact-head release preparation and zero-exchange deployment certification.

### Budget capability added to the release shape

The following budget capability is integrated without replacing release
ownership:

- exact opaque `exchange_instrument_id` and asset-neutral risk identity;
- versioned instrument-rule and risk-cluster membership snapshots;
- full-account read-only account risk facts;
- Account Exposure Current and Account Budget Current projections;
- one atomic Account Capacity Claim using the existing budget reservation;
- PostgreSQL lock-first capacity arbitration;
- Ticket and FinalGate semantic revalidation;
- lifecycle-triggered account risk reprojection after durable lifecycle facts;
- bounded hot-path reads and streaming account snapshot parsing.

### Resolution rule

For every conflict or overlapping auto-merge:

```text
start from the ffc73899 release behavior
-> identify the budget invariant being added
-> extend the existing release abstraction
-> reject duplicated state machines, gateways, writers, or repositories
-> prove both release regression and budget regression
```

No conflict is resolved by bulk-selecting all `ours` or all `theirs`.

## Dependency Decision

The final `requirements.txt` preserves the release dependency contract and adds
only the budget dependency proven necessary by imported production code:

```text
ccxt==4.5.56
ijson>=3.5.1,<4.0.0
```

The budget branch's relaxed CCXT range is rejected. FastAPI/Starlette bounds are
not changed merely because they appeared on the older budget line. Any future
framework pin change requires an independent runtime compatibility task.

## Commit And Review Model

The integration uses one real two-parent merge commit after all conflicts are
resolved and focused tests pass. Subsequent certification fixes use narrow
follow-up commits.

```text
parent 1: ffc73899
parent 2: 5b67181e
merge commit: merge: integrate dual-position account risk v0 onto ffc73899
follow-up commits: only for defects demonstrated by post-merge certification
```

The merge commit is local-only. It is not pushed, tagged, deployed, or merged
into either source branch during this execution plan.

## Validation Architecture

The frozen release base has one verified pre-merge documentation-authority
failure: `docs/current/P0_RUNTIME_STABILITY_AND_SIMPLIFIED_TOKYO_DEPLOYMENT_IMPLEMENTATION_PLAN.md`
exists at `ffc73899` without YAML front matter. The budget branch does not
contain this release-added file, so a normal merge retains it. The integration
must add only the required current-document front matter before the authority
gate; this is classified as an explicit baseline repair, not as a budget
feature or a reason to weaken the validator.

Validation proceeds from cheapest to most authoritative:

1. clean worktree and exact-ref assertions;
2. conflict inventory and migration graph checks;
3. focused release regression;
4. focused account-risk regression;
5. Action-Time full-chain and lifecycle regression;
6. PostgreSQL migration, concurrency, and 100000-row scale tests;
7. current-doc, output-scope, authority, and production file-I/O audits;
8. complete `pytest -q` with zero failures;
9. local release-preparation dry run with migration head `133`;
10. separate review of `ffc73899..fdad0e93` after the frozen merge is green.

The complete test suite is an announced long-running gate. It starts only after
all focused and PostgreSQL gates are green.

## Cadence And Performance Contract

| Dimension | Required integrated behavior |
| --- | --- |
| No-signal files | `0` new JSON/MD files per tick |
| No-signal account-risk rows | `0` Claim/Ticket/ExposureEpisode rows |
| One Action-Time invocation | At most `1` Reservation, `1` Ticket, `1` ExposureEpisode identity |
| Hot-path history | `0` terminal-history rows materialized in Python |
| Current rows | At most `max_concurrent_positions + 1` exposure/reservation rows |
| Network inside capacity transaction | `0` |
| Subprocess inside capacity transaction | `0` |
| Action-Time deadline | At most `30` seconds; freshness windows are not extended |
| Streaming transport | Configurable `65536` byte default chunk; bounded error body |
| Migration batches | At most `1000` rows with `5s` lock timeout and `60s` statement timeout |
| Disk retention | No new recurring report or trace sidecar; archive remains manual and bounded |

## Rollback And Stop Conditions

Before the merge commit, rollback is `git merge --abort`. After the merge
commit, rollback is deletion of only the integration worktree and branch. The
two source worktrees remain unchanged in either case.

Stop immediately when any of these is observed:

- a source SHA differs from the frozen input;
- a conflict requires editing either source worktree;
- more than one Alembic head or any duplicate revision remains;
- historical migration `086` differs from `ffc73899`;
- an active/current row cannot map to one exact instrument;
- the same ActionTimeInvocation can create two capacity claims;
- a capacity transaction performs network or subprocess work;
- release TP1/runner/exit-protection behavior regresses;
- FinalGate requires loose symbol/side identity;
- any test reaches an exchange write;
- PostgreSQL integration is skipped;
- production file-I/O audit is not clear;
- the complete suite has any failure;
- the work expands live scope, risk parameters, or production policy.

## Completion State

The integration design is complete when a clean local branch contains one
two-parent merge from the frozen inputs, migration head `133`, preserved release
lifecycle behavior, locally certified account-capacity behavior, zero test
failures, and no deployment or policy activation.

The next separate engineering decision is whether to absorb the moving release
delta `ffc73899..fdad0e93`; deployment and shadow activation remain later,
independent stages.
