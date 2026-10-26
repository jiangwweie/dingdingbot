---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-10-26
---

# Main Control Roadmap

## Final Target

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

One PostgreSQL-backed kernel serializes new ENTRY while protected Tickets
continue concurrently across independent Netting Domains.

## Current Verified State

### Recovery repairs deployed and enabled trading chains restored

This snapshot supersedes the Kernel/control posture in older snapshots below.
Independent Owner API and V2 static remain at their prior360fd425 release;
only Kernel software changed in these two R3 releases.

| Area | Direct evidence |
| --- | --- |
| Current Kernel | `c85d289bdd09e9451d2d4342476bc0f2687faec1`, immutable tag `tokyo-runtime-2026.10.26.3` pushed to origin; exact candidate fast-forwarded and pushed to dev. Official R3 regular release PASS in167127ms; schema remains `0013_owner_directional_risk_v1` |
| Exact certification | R3 PASS:1788 Unit/Architecture,1760 Integration,69 Full-chain; Ruff, Mypy207 source files and diff PASS. Earlier d8994c79 failed local certification and debdf8a6 was interrupted to add successor coverage; neither is deployment evidence |
| SOR-1H repair | Prior Kernel b549a0be/tag2026.10.26.2 repaired same-session global pause/resume lineage and clean NO_CHANGE successor identity. Real PG tests cover repeated genuine pause/resume, drift/source outages and early/old birth rejection. Production Gap Audit completed14 scopes:7 checked-negative and7 historical triggers suppressed. Actual post14:00 Entry resolver accepted7/14; other7 remain legitimate first-trigger suppression. The original lineage-interrupted blocker disappeared |
| Generic repair | Expired recovery with a newer existing Desired no longer waits forever for old ARMED checkpoints. Exact Dynamic REBASE_PENDING alone enters the existing gap fence/drain/ledger; the existing Desired is retained by CAS. Existing SQL proof grants only future-close recovered activation and fresh checkpoints. This also covers a normal NO_CHANGE successor retaining an unarmed recovery origin; Static and already-armed paths retain prior behavior |
| Actual BRF2 takeover | New production `ACTIVE_NEW` recovery Authority `authority:recovery:3291fa3f7130e195e299b4e066073812c4c27d8ae4c53638b4db68eaed453790` committed through the existing original Desired; prior source Authority and gap ledger preserved. New future-close recovery plan starts at17:00 Asia/Shanghai, not a retrospective trade; Vacuum resolved |
| Cutover and control preservation | Source action-time empty PG/exchange and exact current member/account gates PASS. Entry fenced and all four Workers plus independent Owner API stopped for identity rotation. Stopped current-Universe/history and control baseline preserved. Policy30 genuine Owner Resume remains enabled; official promoter returned `promoted`. Exact Owner/Strategy/Selection/Research/Directional controls match source. Direction unset/v1, research enabled50/control4 unchanged |
| Running services | Four Workers active at exact target Commit/Schema, NRestarts0; independent Owner API active/NRestarts0. Operational write fence absent. Protected Feishu endpoint present with valid HTTPS host in each Worker; no URL printed or test message sent |
| Runtime acceptance | Actual17:00 closed-bar observations armed BRF2 recovery checkpoints16/16, last detector status NOT_TRIGGERED16/16. At17:04–17:05 Asia/Shanghai, BRF2 observation authority16/16 valid, ENTRY resolver reports RECOVERY_TRIGGER_NOT_CURRENT because no fresh post-arm trigger exists; no rebase or expired-authority blocker remains. CPM16/16, MI16/16 and MPG15/15 exact current observation/ENTRY authority PASS. SOR-1H7/14 current authority valid; other7 remain legitimate consumed-first-trigger suppression. Owner Policy30/Resume and account gates remain valid. These prove restored capability, not immediate execution or profitability |
| Current preparation | The17:00 hour caused normal serialized Universe preparation; MPG finished and current membership became15. Other unfenced Desired targets may defer after a consumed close while their current authorities remain valid. These do not justify pausing/resuming Owner controls, rearming checkpoints, or forcing orders |
| Safety sample | Post-release readonly PG Ticket/position/command/Incident counts0, four exact Workers/API active, no operational fence. Exact exchange account has independent sides/Cross/5x with zero positions/orders;32 current instrument rule facts at the16:59:55 probe. Later operations must reread these volatile facts; no natural post-repair live Ticket/economic outcome is claimed |
| Safety boundary | No migration, credential mutation, direct production SQL repair, fabricated clock/Signal, forced ARMED or test order. No forced flatten and no risk/control expansion. Retired SOR-001 and Owner-paused TradFi remain paused. The `brc` automatic monitor was deleted at Owner request and has not been recreated |

Evidence: `.local/sor1h-authority-repair-20261026/` and
`.local/generic-expired-recovery-repair-20261026/` retain exact certificates,
formal release/promotion logs, stopped baseline, preserved controls and current
readonly resolver/checkpoint evidence. Generated artifacts are display-only.

### Earlier10:40 installation snapshot: directional risk and Feishu, ENTRY paused

This snapshot supersedes the Kernel, schema, Owner API and static production
identities recorded below. Older snapshots remain dated evidence only.

| Area | Directly verified state |
| --- | --- |
| Release identity | Kernel, Owner API and V2 static all `360fd425f82e2bc5716f4f58f2584063c0ca8925`; immutable annotated tag `tokyo-runtime-2026.10.26.1` pushed to origin. Official R4 compatible upgrade completed at approximately 10:37 Asia/Shanghai, followed by R2 API and R1 static. This is the combined directional-risk and Feishu release, not a notifications-only R3 |
| Exact certification | Same-commit R4/R2/R1 manifests PASS. R4: 1,788 Unit/Architecture, 1,752 Integration and 69 Full-chain; Ruff, Mypy207 source files and diff PASS; Golden/Core parity961 Snapshots/23,064 member decisions. Periodic resource audits remain outside the existing release portfolio. One pre-existing resident-test UTC01:00 assertion was corrected in tests only before the final candidate was frozen |
| Owner maintenance and closure | Genuine Console Owner ENTRY pause produced Policy29 with `new_entry_submit_enabled=false`; genuine Owner flatten-all completed three Tickets. All three Ticket/Aggregate pairs are terminal, position/protected quantities zero, active domains and budgets released, Review present; Owner operation completed. No agent-created live order or direct exchange mutation |
| Source Selection quiescence | Four exact source Generic Generations reached STAGED while Owner Policy was paused. Observation was stopped to prevent new preparation; Lifecycle/Reconciliation and the old API remained available. The exact deployed0012 coordinator processed their actual30-minute deadlines, last10:32:18.904; all became FAILED_CLOSED and targets were abandoned. The existing authenticated Owner-pause/zero-debt predicate proved their retained negative Vacuums quiescent. No forged clock, shortened timeout, manual SQL repair, forced activation or extra Owner strategy/Selection change |
| Schema and preservation | Official stopped, flat, forward-only0012→0013 upgrade PASS in191404ms. All five writers were stopped before the final source check. Every existing0012 table/column/row participated in the85-table preservation manifest; final stopped-source digest `sha256:517b02bd01e3df4327ebeea9742998a7b424fbb0c194b9add051ab17109e6468` matched after DDL and before identity rotation. Exact COMPATIBLE_RESTART Fact persisted; new Seed `sha256:eed0c812d181f995581b6a083cea6b0db9362ed902866bcab820227831789852` |
| Owner directional control | Exact Owner read-role query through a READ ONLY transaction verified account control `unset`, version1, no pending view. Directional events, admissions and send-authorizations all zero at installation. Tracked grants give Owner Control UPDATE on controls and INSERT on events, with no INSERT/UPDATE on immutable rules, admissions or send-authorizations. Existing roles/passwords retained |
| Owner trading authority | Policy29 remains paused and unchanged. Official `promote_entry.py --prepare-owner-resume` returned `prepared_owner_paused`: Entry process active and operational Fence removed only after fresh PG/exchange checks; no Owner Resume or trading permission was written. A genuine Console Resume/TOTP remains the only way for the Owner to reopen ENTRY |
| Runtime ownership | Four persistent Workers active/enabled at exact360fd425/0013, NRestarts0; PIDs Observation887095, Entry893297, Lifecycle887094, Reconciliation887096. Independent Owner API active/NRestarts0, PID889914, `/healthz` returns `ok`. No old/new writer overlap or timer cold-start cadence |
| Feishu notices | Protected Worker environment configured; Entry/Lifecycle/Reconciliation process-environment readback matches its HTTPS Feishu endpoint without printing the URL. Notices cover accepted ENTRY, full TP1 fill and post-TP1 Runner flatness. Runner messages retain “成交明细待确认” when only flatness is known. Best effort, two-second timeout, no retry/durable queue; no real notification delivery or live lifecycle acceptance is claimed by configuration alone |
| Owner API / public static | Official R2/R1 deployment and health smoke PASS. Public index/JS/CSS HTTPS200 with exact public/disk SHA-256 equality; unauthenticated directional-control GET401. API restart invalidated prior in-process Sessions. Directional data accepted through the actual readonly role; genuine authenticated browser control-write acceptance remains NOT TESTED |
| Current safety sample | At10:40–10:41 Asia/Shanghai: PG Ticket/position/reservation/domain/unreviewed-terminal/command/Incident/busy-lane/nonterminal-Aggregate/nonquiescent-Vacuum counts all0; nonterminal Generations/Owner operations0. Exact exchange probe during paused preparation confirmed zero positions/orders, independent sides/Cross/5x and exact current Universe/account scope |
| Dynamic / control preservation | Ten Active Universe pointers and frozen membership preserved,106 active scopes over31 current instruments with31 fresh certifications at postflight. Strategy Controls and Selection mode/version/pending controls match source. Four FAILED_CLOSED attempts and negative fences are retained historical/recovery evidence, not successful new Authority takeover. Research control/quota unchanged. Crypto SOR-001 remains permanently ENTRY-disabled |
| Remaining boundary | Software delivery and paused operating readiness are complete. Owner direction selection, real notification delivery, future current-period Authority/recovery and natural live lifecycle/economics remain separate evidence. The completed deployment-window heartbeat was deleted when the authorized deployment began; it must not redeploy this completed release |

Evidence: `.local/feishu-release-e984381a/` contains exact certificate hashes,
the source deadline audit, formal Kernel/API/static release logs, stopped-source
preservation baseline, role/control and public-asset postflight, current Writer
identities and protected Webhook existence checks. Generated evidence is
display-only and never runtime authority. Action-time PostgreSQL, systemd and
exchange facts must be refreshed for any subsequent operation.

### Readonly database table inventory for the knowledge catalog

Verified at **2026-10-22 20:32:22 Asia/Shanghai** against database
`brc_trading_kernel`, with a follow-up primary-key catalog check. Both probes
used `BEGIN READ ONLY`, a five-second local statement timeout, catalog SELECTs
and COMMIT. `transaction_read_only=on`; no business rows were read or counted.

| Scope | Direct catalog evidence |
| --- | --- |
| Non-system persistent tables | **88** ordinary/partitioned tables across the two non-system schemas; system schemas, views, indexes, sequences and temporary tables excluded |
| `public` business tables | **85** `brc_*` tables; exact table names, column-name sets and primary keys match tracked Kernel metadata, with no missing or extra business table/column. Physical column ordinal order differs from metadata declaration order in 16 tables; no layout-order equality claimed |
| Migration version table | **1**, `public.alembic_version`; observed revision `0012_generic_signal_path_v1` |
| Independent operations tables | **2**, `brc_cutover_ops.cutover_runs` and `brc_cutover_ops.cutover_phases`; not members of Kernel metadata |
| Bounded source discrepancy | `cutover_runs.exchange_instrument_ids_json` exists in the production catalog but is not declared by the current `PostgresCutoverJournal` CREATE TABLE statement. Its writer/provenance was not proved in this inventory; no runtime use or authority inferred |
| Safety and limits | SSH/Docker/psql catalog reads only; no schema/control/business mutation, service restart, exchange request, full-history scan or live row-count scan. This is not a fresh runtime, policy, position or trading-activation certification |

Display-only catalog evidence is under
`.local/project-knowledge/table-catalog/production-catalog.json`. Stable table
responsibilities and field names are explained in the
[knowledge catalog](../knowledge/DATABASE_TABLE_CATALOG.md); volatile production
inventory remains owned by this section.

### Latest unified income statistics release

This Owner surface snapshot supersedes the explanation-release snapshot below;
Kernel production identity and trading authority are unchanged.

| Area | Directly verified state |
| --- | --- |
| Release | Owner API and static V2 both `a7cfd0393b227002325ee5fe79116ef547cc2975`; immutable tag `tokyo-runtime-2026.10.22.3`; deployed2026-10-22 approximately18:52 Asia/Shanghai through official R2 API then R1 static release paths. Remote `dev` contains the exact implementation |
| Owner-approved income contract | Default includes all ended exposure Tickets and all versions, including Owner flatten. Income belongs to terminal time in Asia/Shanghai, not issue/Review-generation time. Strategy/Owner/safety/unknown causes are explicit disjoint partitions; unknown is never treated as natural strategy exit. Version and exit filters remain explicit; copied links and cross-page navigation retain fixed windows and supported identities |
| Full-window statistics | `/api/owner/v1/performance` is authenticated GET-only. Full-window counts, per-metric known/missing coverage, verified sums, exit partitions and per-group contributions are independent of detail cursor/page size. Queries retain90-day/5000-Ticket bounds and read timeout; overflow fails explicitly. Money aggregation uses80-digit Decimal. Gross fallback never enters net aggregates, Net R or net win/loss |
| Consistency | The fingerprint binds effective filters, complete Ticket population, exact current Review/revision, economics and execution classification. Ticket/Review/detail GETs validate it within the readonly transaction; drift returns409 `statistics_snapshot_changed`, blocks further paging and requires full refresh. Strategy matrix and its headline share a transaction. Overview daily headline/group contributions share one terminal-day income snapshot |
| Local verification | Owner unit/interface slice338 PASS; existing Owner PostgreSQL integration55 PASS; new income PostgreSQL integration5 PASS; V2 tests115 PASS; V1 regression57 PASS. Time-range12, URL8, unified-filter19, Review29, Strategies49, chart23 and Trades pagination/truth scripts PASS. Affected Mypy32 files, Ruff/diff/typecheck/build PASS. Exact R2/R1 certification manifests PASS on release SHA |
| Browser evidence | Isolated readonly production-sample browser fixture verified first50→all72 Review details keep headline +16.98 USDT with60/72 net coverage. Switching to Strategies preserved exact2026-09-22 14:20:48→2026-10-22 14:20:48 window and identical headline. Automated component tests cover snapshot409 lockdown and full-window-failure disclosure |
| Deployed readonly acceptance | At that exact sample window:72 terminal Tickets/60 known net; full net16.9799390541890812999999999503 USDT and cumulative single-Ticket net R3.62443446596345438148693781065. Matrix sum and four partitions equal full net;67 strategy exits/55 known net4.9733238625830181999999999503 plus5 Owner exits/5 known net12.0066151916060631. Review detail pages50+22 cover the population; Trades contains the same ended exposure identities. Fingerprint stayed stable after limit/cursor changes; every exit-scope query matched its detail list |
| Public postflight | Index/JS/CSS HTTPS200 with exact local/public SHA-256 equality. API Unix-Socket healthz `ok`, active/NRestarts0. Google login provider remains enabled/binding disabled; public browser displays Google login. Unauthenticated performance GET returns401. No authenticated production-browser business-page acceptance claimed after session invalidation; release-code/read-role data acceptance above passed |
| Safety proof | Four Kernel Worker PIDs2067875/2085006/2067874/2067876 and NRestarts0 unchanged. Owner Policy/Strategy/Selection Control digests match before/after; Schema0012 unchanged. Only Owner API restarted. No flatness request, ENTRY pause/resume, Worker restart, schema migration, economic/history rewrite, production control write or exchange request in acceptance probes |
| Explicit remaining boundary | Truly unavailable funding and unproved historical exit facts remain unknown. This release does not complete live economic attribution or production control-write acceptance; those boundaries remain separate |

Evidence: `.local/unified-profit-statistics-20261022/` holds exact certification,
classification/deploy logs, before/after service/control proofs, bounded readonly
source samples, deployed income verification and public asset hashes.
`output/playwright/unified-profit-statistics-20261022/` holds browser artifacts.
Generated evidence is display-only and is never runtime authority.


### Latest Owner API / V2 explanation release

The Owner surface snapshot below supersedes the older Owner API/static entries
in the Kernel release snapshot that follows. It does not change Kernel identity.

| Area | Directly verified state |
| --- | --- |
| Snapshot | 2026-10-22 approximately13:32 Asia/Shanghai; Owner explicitly authorized development, testing and deployment of explanation/readonly-query fixes, then the labelled gross-PnL display |
| Owner API | `c98faeb8cf3585ddc80c76fa127f37cfb0b977ba`, immutable tag `tokyo-runtime-2026.10.22.1`; official R2 exact-commit certification and API deployment PASS; Unix socket healthz `ok`, service active/NRestarts0. Google provider remains enabled, binding disabled; unauthenticated Review returns401 |
| Static V2 | `7211164f1feb96e0f0314db87c29398889bef5ba`, immutable tag `tokyo-runtime-2026.10.22.2`; official R1 exact-commit certification/deployment PASS. Public index, JS and CSS200 with local/public SHA-256 equality. Remote `dev` contains both changes |
| Explanation boundary | Trades, Strategy Tickets, Review and causality share exact exit attribution from the original ExitRequested or current Review exit fills and same-Ticket commands. Frozen time-stop details use exact Ticket Profile ID/hash. Execution gaps and economic gaps are independent; missing exit attribution no longer denies known economics. No core trading or persistent economic-calculation change |
| Summary / gross display | API page scope and UI deduplicated loaded-record scope are explicit. Strict per-metric totals stay unavailable when incomplete; separately labelled verified partial sums carry per-metric coverage and missing Ticket IDs. With missing funding but known gross, the PnL cell shows gross plus `（资费不完整）` and an explicit gross label; net remains null, Net R unknown, and gross never enters net sums or win/loss statistics |
| Verification | Owner unit/interface slice329 PASS, PostgreSQL read-repository integration56 PASS, V2 component/hook111 PASS, Review contracts29 PASS, V1 regression57 PASS, affected Mypy11 files PASS, Ruff/diff and production build PASS. Actual browser read-only fixture path50→71 records changed net coverage45/50→59/71 and fees50/50→71/71, with no console errors/warnings. Production release code/read-role verified71 Reviews, coverage gross/fees71/71 and net/funding59/71, matching Trades/Strategy Ticket attribution and existing causality/K-line annotations |
| Runtime / authority preservation | Four Kernel Worker PIDs remained2067875/2085006/2067874/2067876 with NRestarts0 and unchanged release paths. Owner Policy, Strategy Entry and Selection Control digests matched before/after; Schema stayed0012. Only Owner API restarted. No migration, historical rewrite, policy/control mutation, exchange request or exchange write from the acceptance probes |
| Remaining boundary | Actual funding attribution gaps remain unknown. Authenticated production browser business-page acceptance was not performed after API session invalidation; public production login/provider/auth-boundary smoke and deployed readonly model queries passed. Production control-write acceptance remains NOT TESTED |

Exact manifests, deploy logs, control/service before-after proofs, bounded
readonly sample checks and public asset hashes are retained in
`.local/owner-review-clarity-20261022/`; browser evidence is under
`output/playwright/owner-review-clarity-20261022/`. Generated evidence is display-only.


### A+B+MPG R4 deployed; global ENTRY restored; MI Owner Resume verified

| Area | Directly verified state |
| --- | --- |
| Snapshot time | Kernel release snapshot2026-10-15 23:35 through2026-10-16 00:03 Asia/Shanghai; Owner API-only postflight refreshed2026-10-20 approximately11:37 Asia/Shanghai from fresh Tokyo PG/exchange/systemd/markers |
| Integration branch | `dev` |
| Production commit | `3c4760e39d84548fdd962d0a2419724fc946d97c` |
| Production tag | `tokyo-runtime-2026.10.15.3`, immutable annotated tag pushed to origin at the exact production SHA |
| Production-commit certification | Exact complete R4 PASS: 1,711 Unit/Architecture, 1,722 Integration, 64 Full-chain; Ruff, formal Mypy199 and diff PASS; SOR Golden/Core parity961 snapshots/23,064 member decisions. Four periodic-resource cases remain excluded by the official portfolio, not claimed PASS. Command durations total3767.421s. Same-commit Owner API R2 PASS |
| Kernel / schema | Official compatible_upgrade R4 deployment PASS in249404ms; exact source `e7f86acf1287a0cb395702331add1cd9f5354d2d` / `0011_orb_session_1h_v1` advanced to `0012_generic_signal_path_v1`. OBS-EFFICIENCY-01, ALPHA-02A and MPG recovery guard are now deployed |
| Source migration | Earlier `0009_capacity_policy_v0`→0010→0011 forward lineage retained; this release adds the stopped/flat/quiescent0011→0012 migration |
| Seed / preservation | New seed `sha256:64cb207a859d348c162b5c29e0bb1272b93dff47be7d4bcffa26ebb7d1291437`. Official stopped-source preservation digest `sha256:8b7edffce72bce6a1a99e46b3d1006cab66ac06167be64718af447ef1a8f3803` matched before identity rotation. Exact source/target Compatibility Fact persisted; existing historical preservation proof independently retained |
| Owner controls | Policy version `28` has `new_entry_submit_enabled=true`; genuine Owner Web Resume/TOTP superseded maintenance Policy27. MI separately paused at control2, then genuinely resumed by Owner at control3. Selection mode/epoch and capital/risk boundaries were not changed by deployment |
| Runtime ownership | Observation, Entry, Lifecycle and Reconciliation active/enabled, NRestarts0 at23:56–23:59; each process exact3c4760e3/0012. Official `promote_entry.py` returned `status=promoted` after Owner Resume and fresh PG/exchange checks; operational fence absent |
| Owner API / Console | Independent R2 Owner API now `14f54fede9ea6960b7db615e78e96a381d4b3944`, deployed2026-10-20 approximately11:37 Asia/Shanghai through the official API-only path after exact R2 certification PASS. `Strategies?view=all` now returns13 StrategyVersions and preserves eight retired pre-compatibility Events as explicit `historical_product_compatibility_not_recorded` gaps; `view=current` remains7 versions with no compatibility gap. Missing compatibility on a current/nonretired/authorized/active-or-warming Event remains a409 contradiction. The release preserves the prior4hour idle Session timeout and12hour absolute lifetime; the API restart invalidated process-local Sessions, so genuine login may be required again. At that R2 postflight, Kernel remained3c4760e3/0012 and static frontend remained6bb3ffa8. All four Kernel Worker PIDs, restart counts and release paths were identical before/after; Owner/Strategy/Selection/runtime-profile digests and research enabled50/control4 were unchanged; three current positions retained exact exchange protection, unresolved Commands0 and open Incidents0. No trading pause, flatness, migration, database repair or exchange action occurred. On2026-10-16 approximately09:39 Asia/Shanghai, desktop static frontend `6bb3ffa8f71e086dfd4916f168a91f7528708a48` deployed through official R1 after exact typecheck/build certification PASS; public HTTPS200 and exact index hash PASS. Desktop controls verified1024/1100/1280/1440/1920 with57 component and8 E2E tests PASS. Latest static R1: Owner Console V2 `738c858c5bb2c851a486a1adaf77a47800a469a7`, tag `tokyo-runtime-2026.10.21.1`, deployed2026-10-21 through the official static-only path after exact V2 typecheck/build certification PASS. Public `/trading/` index, JavaScript and CSS returned200 with public/disk SHA-256 equality; real browser displayed the V2 login screen. API and all four Worker PIDs, NRestarts0 and release paths matched preflight. V1 source is retired from default release and retained; prior static release `6bb3ffa8f71e086dfd4916f168a91f7528708a48` remains available for symlink rollback. No API/Kernel restart, database migration, control mutation or exchange action. V2 production control-write acceptance remains NOT TESTED. |
| Controlled closure | Owner Web controlled-closed MI UNIUSDT long19, Ticket `ticket:a6886748abe0542bd7607d118cca3b54`. Existing runtime resolved cancel unknown and cleaned protection; terminal Ticket/Aggregate, released budget/domain, completed Settlement/Review. No manual exchange write by agent |
| Trading facts | At23:56–23:59 account flat/order-free, unresolved Commands0, open Incidents0. This is a dated sample, not a promise of continuing flatness after ENTRY restoration |
| Source Selection quiescence | BRF2 completed ACTIVE23:10:29.795. Owner MI pause caused Coordinator to legally ABANDON unfenced Generation `generation:c7f6330404e16979df87a0d5ddf5cd5bb70a92eb6fc500b3065ba4faea068a61`; standalone OWNER_PAUSED Vacuum drained. All exact source migration gates zero before final Writer stop; no SQL repair, forced terminal state or manual Vacuum deletion |
| ExitProfile postflight | Existing typed Profile/Binding authority and frozen Ticket exit semantics preserved; no exit policy changes |
| Dynamic Selection postflight | Ten current Universe pointers/member manifests, Dynamic history, typed ExitProfile bindings, Owner/Selection controls and terminal lineage preserved through stopped and running target postflight. Fresh current member certifications32 over106 active scopes; official PG/exchange postflight PASS |
| MPG state |22:00 recovery consumed and ARMED14/14 scopes. A later23:00 NO_CHANGE Authority was effective and Readiness signal_absent14/14; no Signal required to prove recovery. Future current-period authority still requires fresh runtime evidence |
| MI state | Owner Resume is verified, but business recovery is not complete. New Generation `generation:24c10ffe57027b12b11021c4aca5d3d2440ce163fe4f172ff7e32b63a3ff608a` ACTIVE at00:01:58.108; target Universe v38 active/warmed16/16 and original Vacuum RESOLVED_ACTIVE. Current Recovery Authority `authority:recovery:a11cda8f4b9ab248caeccbc671d5fb4772b9753f047bb56406eba090ce16d722` matches Owner control3, effective/first eligible01:00 and expires02:00. At00:03 Readiness16/16 selection_recovery_not_effective; real new ENTRY remains blocked pending the01:00 legal recovery close/rebase. This is not full business-readiness acceptance |
| Research collection | Owner separately approved initial collection. Official `configure_research_collection.py` enabled `generic_signal_path_v1` at2026-10-16 00:20:42.864 Asia/Shanghai, control_version1→2, daily_limit50 shared by CPM/MPG/MI/BRF2/SOR-1H per UTC day. Audited Owner identity/reason persisted. At00:23 collected0, no daily coverage row yet, research failures0; no collected-result acceptance claimed. MI recovery is independent. ENTRY/Strategy/Selection/Authority/risk-profile digests unchanged across enablement; four Workers healthy. One-hour and24/48-hour readonly follow-up configured; no automatic quota expansion |
| SOR retirement | Crypto `SOR-001` remains permanently ENTRY-disabled; neither global nor MI Resume grants it permission |

Sources: `.local/alpha-ab-mpg-r4-3c4760e3/` holds exact local R4/R2 manifests
and complete certification log. `.local/alpha-ab-mpg-production-3c4760e3/`
holds official deployment/API/promotion logs, stopped source baseline, exact
Compatibility Fact, terminal closure, four Worker identities, research controls
and fresh postflight/MI recovery samples. `.local/alpha-02a-research-enable-50/` holds the separate research Owner authorization audit, control readback, before/after trading-authority digests, coverage/error/resource and Worker checks. Generated evidence is display-only;
Static R1 source certification, deploy and public index/assets/Writer integrity evidence are retained in `.local/owner-frontend-r1-20261016/`. V2 R1 certification and public/browser/service-integrity evidence are retained in `.local/owner-console-v2-r1-20261021/` and `output/playwright/owner-console-v2-release-20261021/`. The exact Kernel production identity/tag above remains unchanged by the independently versioned static release.
action-time PG/exchange/systemd facts remain authoritative.

### Current Dynamic acceptance boundary

| Strategy | Current boundary | Remaining evidence |
| --- | --- | --- |
| MPG-001 | Deployed guard;22:00 recovery14/14 ARMED and23:00 normal NO_CHANGE successor verified | Continue exact future-period observation and natural trading evidence |
| MI-001 | Owner Resume control3 verified; new recovery Generation ACTIVE00:01:58, original Vacuum resolved; Authority matches control3 | First eligible01:00 recovery close/rebase and Readiness;16/16 still blocked before that boundary |
| CPM / BRF2 / SOR-1H | Exact source controls and Universe lineage preserved by R4; global ENTRY restored | Fresh per-family current-period qualification remains required for every new ENTRY |
| SOR-001 | Permanently retired for new ENTRY | Historical Registry/Universe cannot grant resume |

## Repair Evidence

Production evidence identified and local regressions repaired these defects:

1. Old Static Observation consumed selected members' due close before queued
   first Dynamic activation. Exact same-epoch precommitted current Snapshot now
   coordinates observation deferral and bounded retry; born Signals keep their
   existing authority path.
2. Switching Vacuum opened before prior recovery checkpoints were ARMED, blocking
   the very recovery observations needed to progress. DESIRED now checks actual
   recovery and unconsumed close before taking the slot or opening Vacuum.
3. Consumed-close or unarmed-recovery queue heads starved eligible work. Bounded
   eligible FIFO filtering preserves the single warming slot and Owner pause.
4. Reconciliation and activation locked Certification/Instrument in opposite
   order, producing the16:12 production deadlock. Both use Instrument then
   Certification in canonical order; real PostgreSQL concurrency test PASS.
5. STAGED members were excluded by both certification scheduler preview and
   claim, causing CERTIFICATION_STALE while waiting. Both now refresh those
   members through the existing readonly certification path. Regression proves
   no activation, Observation permission, Entry permission or Exchange Command.

No schema change, SQL repair, forged ARMED, consumed-close reuse, timeout
extension, capital expansion or safety-boundary bypass. Original Owner intents
and terminal lineage remain preserved.

## Remaining Critical Path

1. Prove each family's real current-epoch Universe/Authority takeover after
   recovery and the next legal boundary; current complete activation gate is open.
2. Follow naturally admitted Tickets through protection, exit, reconciliation,
   settlement and review without forced trades or risk expansion.
3. Keep long-run evidence, offline projector and complete live economics deferred.

## Three-Stage Program Direction

The Owner reports delivery of BRC-ALPHA-01's offline attribution first edition.
Repository receipt and independent reproduction remain unverified; this does
not close the deferred offline MAE/MFE projector, GS-13, long-run evidence or
natural Ticket acceptance. See the
[research delivery and planning record](../superpowers/plans/2026-10-14-brc-alpha-research-status-and-plan.md).
The Owner-approved direction is SOR-1H release and natural lifecycle validation,
then generic ALPHA-02 path Observation, then evidence-driven strategy iteration.
ALPHA-02 design may proceed alongside natural SOR-1H evidence accumulation;
profitability is not a prerequisite to designing evidence collection. Prefer
reuse of existing SOR-US Signal-owned paths; preserve Shadow/real-PnL and Owner
Regime/maintenance-pause boundaries. ALPHA-02A and OBS-EFFICIENCY-01 are deployed with MPG recovery after exact combined R4 and the preservation-gated0012 upgrade. The Owner subsequently approved bounded initial prospective collection50/UTC day through the official research-only control; further quota changes remain separately authorized. Initial samples are quota-limited and must disclose skipped_budget rather than represent a complete Signal population.
Local parameter tuning is deferred; console redesign and USDC adaptation remain
separate backlog. Research does not change capital, exits, selection or scope.

The Owner completed genuine new SOR-1H enable/Dynamic controls and global
ENTRY Resume through the Console; Policy24 was the earlier live posture; the earlier Policy25/26 maintenance lineage is retained; current maintenance pause27 was superseded by genuine Owner Resume/TOTP28. Official Entry promotion and real paired Dynamic takeover
are complete. The SOR deployment monitor must not redeploy completed software.
Natural lifecycle evidence remains separate acceptance; Generic recovery
also completed with CPM current Authority at09:22:04.378.
protected future Owner changes retain their normal authentication requirements.
The completed preceding joint release included BRC-RECON-RELIABILITY-01:
reconciliation expedite fairness, Universe lock ordering, superseded
certification Claim handling and minimal stagnation visibility. Those repairs and their exact
combined certification were completed before the current release; do not
redeploy a historical SOR-1H-only candidate. See the
[reliability repair design](../superpowers/specs/2026-10-14-reconciliation-reliability-repair-design.md).
Software deployment, strategy/Selection activation and real lifecycle evidence
remain separate gates. This authority does not resume retired SOR-001.
The current verified snapshot above owns the completed release and remaining controls.

## Current Stop Conditions

No exchange write under wrong identity, stale/contradictory action-time facts,
unknown outcome, same-domain occupancy, missing stop/budget, schema mismatch or
old-writer overlap. Existing exposure retains its frozen lifecycle. Crypto SOR
must remain Entry-disabled. No manual repair of recovery/cursors to manufacture
activation evidence.

## Historical Evidence

Prior roadmap snapshots are preserved in
[historical roadmap](../archive/2026-10-12-main-control-roadmap-history.md).
Historical PASS belongs only to its exact candidate and scope. The earlier
repository publication `release-2026.10.12.1` is not this server deployment.
