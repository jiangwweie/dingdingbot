# Owner Console Phase 1 Acceptance Checklist

## Scope

This checklist records reproducible local acceptance for the read-only Owner
Console. It contains no volatile Tokyo deployment identity, Ticket identity,
account identity, credential, Session value, or row payload. Task 25 production
deployment remains a separate Owner gate.

## Product And Security Gates

- [x] Four primary pages and exact Ticket detail route exist.
- [x] Password plus TOTP is mandatory.
- [x] New login invalidates the old Session.
- [x] API restart invalidates all Sessions.
- [x] Every data route rejects unauthenticated access.
- [x] Read role cannot write.
- [x] Each page opens one bounded read-only transaction.
- [x] Candles open no database transaction.
- [x] No automatic network refresh exists.
- [x] Last Known Good survives failed manual refresh.
- [x] Active Ticket has no final review conclusion.
- [x] Missing Funding or external exit facts do not become zero.
- [x] Every deterministic sentence has evidence references.
- [x] CapacityClaim account values are labeled Latest Admission Snapshot.
- [x] No Strategy control or exchange write route exists.
- [x] Frontend initial bundle excludes `lightweight-charts`.

## Visual Gates

- [x] Real-browser screenshots cover all primary routes and exact Ticket detail at 1280x800, 1440x900, and 1920x1080.
- [x] Overview first-screen hierarchy and UI System B received explicit Owner visual approval before Task 17.
- [ ] Final local product preview received separate Owner visual acceptance.
- [x] No page-wide overflow, oversized dead space, stretched empty card, SaaS shadow, decorative icon tile, or viewport-height right drawer remains.

## Runtime And Deployment Gates

- [x] API idle resource use fits 25% CPU / 256 MiB / 32-task budget.
- [x] Four Trading Kernel workers remain unchanged.
- [x] Owner Console API uses an independent Unix Socket and systemd Slice.
- [x] Nginx configuration is same-origin, API no-store, and login-rate-limited.
- [x] Regular Kernel release preserves existing Owner Console venv and static assets without requiring them.

## Production-Fact Snapshot Gates

- [x] Production DML snapshot is Git-ignored, checksum-verified, and restored only into a guarded localhost disposable database.
- [x] Owner Console passes the same browser and API paths against the restored production-fact snapshot.
- [x] Restored-snapshot Signal, Trade, and Review worst-window EXPLAIN execution times are each below 2400 ms.
- [x] Restored-snapshot Signal, Trade, and Review end-to-end repository reads are each below 3000 ms.
- [x] Snapshot metadata and probe output contain no row payload, DSN, account identity, Ticket identity, Session, or credential.

## Verification Record

### Backend

| Verification | Result |
| --- | --- |
| Owner Console unit, HTTP, PostgreSQL integration, and deployment architecture | 283 passed |
| Complete architecture suite | 65 passed |
| Runtime and Owner Console Ruff scope | Passed |
| Production code and Owner Console scripts Mypy | 126 source files passed |
| Strict production runtime file-I/O audit | Passed; zero blocking cleanup, suspicious authority, or frequent report write |

The repository-wide Mypy command including all historical tests reports 112
test-typing errors across 27 files. They are test fixture and test-double
annotation debt rather than runtime errors; no production source file failed
the bounded Mypy command above. Closing that unrelated debt is outside Phase 1
and was intentionally not added to this personal-system acceptance scope.

### Frontend

| Verification | Result |
| --- | --- |
| Generated OpenAPI client | Passed; no unexpected tracked output |
| Vitest | 9 files, 23 tests passed |
| TypeScript | Passed |
| Production build | Passed |
| Playwright | 6 tests passed |
| Initial bundle | 481.09 kB; gzip 146.75 kB |
| Lazy chart bundle | 170.50 kB; gzip 55.38 kB |

Fifteen final screenshots exist under
`.local/owner-console-visual/task-24/`: Overview, Signals, Trades, exact Ticket,
and Review at 1280x800, 1440x900, and 1920x1080. The matrix was regenerated
after adding production-shaped long Decimal and deployment-drain reason
fixtures. Inspection confirmed aligned density, hierarchy, bounded text,
absence of page-wide overflow, and the accepted dark System B treatment.

The in-app Browser separately validated and displayed the 1280px restored-data
Overview, Signal, Trade, exact Ticket, and Review surfaces. Playwright remains
the complete three-viewport screenshot matrix; Browser supplied live page
identity, DOM, console health, interaction, and restored-data layout evidence.

### Restored Production Facts

| Query | EXPLAIN execution | Repository elapsed | Returned rows | Result |
| --- | ---: | ---: | ---: | --- |
| Signal | 0.832 ms | 10.522 ms | 101 raw limit+1 facts | Passed |
| Trade | 2.631 ms | 12.622 ms | 46 | Passed |
| Review | 2.470 ms | 25.705 ms | 41 | Passed |

The restored parity counts were 439 Signal Events, 46 Tickets, 46 Aggregates,
41 Reviews, and zero open Runtime Incidents. Browser validation used the same
restored database and confirmed login, Overview, 50-row Signal page, 46-row
Trade page, exact eight-stage Ticket causality, manual K-line failure isolation,
and 41-row Review page with no global sample-warning banner. Browser console
error/warn logs remained empty.

### Resource Measurement

| Resource | Observed idle value | Budget | Result |
| --- | ---: | ---: | --- |
| RSS | 132-191 MiB after startup settling | 204 MiB acceptance / 256 MiB hard limit | Passed |
| CPU | 0.1%-0.2% | 25% hard limit | Passed |
| Threads/tasks | 5 | 32 hard limit | Passed |
| API routes | Login 204; health and four read pages 200 | Successful bounded response | Passed |

The local API listened only on `/tmp/brc-owner-console-test.sock`. Acceptance
also found and fixed the CLI runner defect that previously ignored its `--uds`
argument; the systemd default path remains unchanged.

## Review Findings

Final restored-data visual review found two frontend overflow defects that the
short deterministic fixtures had not exposed: high-precision economic metrics
painted across adjacent Review columns, and a deployment-drain Exit Reason
expanded the lower three-column grid beyond the viewport. Review metrics now
truncate inside their exact cells with the full value retained in the title,
and Exit Reason rows now permit bounded Flex shrink. The responsive browser
test contains both production-shaped boundaries.

No P0/P1 finding remains after the fixes. The change adds no exchange
credential, exchange write, Strategy mutation, Ticket mutation, schema
migration, background worker, Redis, WebSocket, SSE, or alternate execution
chain.

One non-blocking current-data observation remains visible by design: the
restored Overview can present an evidence-unavailable or attention conclusion
when bounded monitor evidence is incomplete. The frontend does not replace that
state with a false healthy conclusion.

## Final Boundary

Task 25 may not begin until every technical gate above is closed, the final
preview is presented to the Owner, and the Owner gives fresh explicit
deployment confirmation after that preview.
