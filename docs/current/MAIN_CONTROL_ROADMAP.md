---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-10-16
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

### A+B+MPG R4 deployed; global ENTRY restored; MI Owner Resume verified

| Area | Directly verified state |
| --- | --- |
| Snapshot time | 2026-10-15 23:35 through 2026-10-16 00:03 Asia/Shanghai; fresh Tokyo PG/exchange/systemd/markers, official compatible upgrade and Owner API deployment |
| Integration branch | `dev` |
| Production commit | `3c4760e39d84548fdd962d0a2419724fc946d97c` |
| Production tag | `tokyo-runtime-2026.10.15.3`, immutable annotated tag pushed to origin at the exact production SHA |
| Production-commit certification | Exact complete R4 PASS: 1,711 Unit/Architecture, 1,722 Integration, 64 Full-chain; Ruff, formal Mypy199 and diff PASS; SOR Golden/Core parity961 snapshots/23,064 member decisions. Four periodic-resource cases remain excluded by the official portfolio, not claimed PASS. Command durations total3767.421s. Same-commit Owner API R2 PASS |
| Kernel / schema | Official compatible_upgrade R4 deployment PASS in249404ms; exact source `e7f86acf1287a0cb395702331add1cd9f5354d2d` / `0011_orb_session_1h_v1` advanced to `0012_generic_signal_path_v1`. OBS-EFFICIENCY-01, ALPHA-02A and MPG recovery guard are now deployed |
| Source migration | Earlier `0009_capacity_policy_v0`→0010→0011 forward lineage retained; this release adds the stopped/flat/quiescent0011→0012 migration |
| Seed / preservation | New seed `sha256:64cb207a859d348c162b5c29e0bb1272b93dff47be7d4bcffa26ebb7d1291437`. Official stopped-source preservation digest `sha256:8b7edffce72bce6a1a99e46b3d1006cab66ac06167be64718af447ef1a8f3803` matched before identity rotation. Exact source/target Compatibility Fact persisted; existing historical preservation proof independently retained |
| Owner controls | Policy version `28` has `new_entry_submit_enabled=true`; genuine Owner Web Resume/TOTP superseded maintenance Policy27. MI separately paused at control2, then genuinely resumed by Owner at control3. Selection mode/epoch and capital/risk boundaries were not changed by deployment |
| Runtime ownership | Observation, Entry, Lifecycle and Reconciliation active/enabled, NRestarts0 at23:56–23:59; each process exact3c4760e3/0012. Official `promote_entry.py` returned `status=promoted` after Owner Resume and fresh PG/exchange checks; operational fence absent |
| Owner API / Console | Independent same-commit R2 API deployment PASS; service active/enabled and Unix socket `/healthz` ok. Static frontend unchanged |
| Controlled closure | Owner Web controlled-closed MI UNIUSDT long19, Ticket `ticket:a6886748abe0542bd7607d118cca3b54`. Existing runtime resolved cancel unknown and cleaned protection; terminal Ticket/Aggregate, released budget/domain, completed Settlement/Review. No manual exchange write by agent |
| Trading facts | At23:56–23:59 account flat/order-free, unresolved Commands0, open Incidents0. This is a dated sample, not a promise of continuing flatness after ENTRY restoration |
| Source Selection quiescence | BRF2 completed ACTIVE23:10:29.795. Owner MI pause caused Coordinator to legally ABANDON unfenced Generation `generation:c7f6330404e16979df87a0d5ddf5cd5bb70a92eb6fc500b3065ba4faea068a61`; standalone OWNER_PAUSED Vacuum drained. All exact source migration gates zero before final Writer stop; no SQL repair, forced terminal state or manual Vacuum deletion |
| ExitProfile postflight | Existing typed Profile/Binding authority and frozen Ticket exit semantics preserved; no exit policy changes |
| Dynamic Selection postflight | Ten current Universe pointers/member manifests, Dynamic history, typed ExitProfile bindings, Owner/Selection controls and terminal lineage preserved through stopped and running target postflight. Fresh current member certifications32 over106 active scopes; official PG/exchange postflight PASS |
| MPG state |22:00 recovery consumed and ARMED14/14 scopes. A later23:00 NO_CHANGE Authority was effective and Readiness signal_absent14/14; no Signal required to prove recovery. Future current-period authority still requires fresh runtime evidence |
| MI state | Owner Resume is verified, but business recovery is not complete. New Generation `generation:24c10ffe57027b12b11021c4aca5d3d2440ce163fe4f172ff7e32b63a3ff608a` ACTIVE at00:01:58.108; target Universe v38 active/warmed16/16 and original Vacuum RESOLVED_ACTIVE. Current Recovery Authority `authority:recovery:a11cda8f4b9ab248caeccbc671d5fb4772b9753f047bb56406eba090ce16d722` matches Owner control3, effective/first eligible01:00 and expires02:00. At00:03 Readiness16/16 selection_recovery_not_effective; real new ENTRY remains blocked pending the01:00 legal recovery close/rebase. This is not full business-readiness acceptance |
| Research collection | Schema0012 installed `generic_signal_path_v1` disabled, daily_limit0, control_version1. No prospective collection enabled; any quota/start remains a separate Owner decision |
| SOR retirement | Crypto `SOR-001` remains permanently ENTRY-disabled; neither global nor MI Resume grants it permission |

Sources: `.local/alpha-ab-mpg-r4-3c4760e3/` holds exact local R4/R2 manifests
and complete certification log. `.local/alpha-ab-mpg-production-3c4760e3/`
holds official deployment/API/promotion logs, stopped source baseline, exact
Compatibility Fact, terminal closure, four Worker identities, research controls
and fresh postflight/MI recovery samples. Generated evidence is display-only;
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
Regime/maintenance-pause boundaries. ALPHA-02A and OBS-EFFICIENCY-01 are deployed with MPG recovery after exact combined R4 and the preservation-gated0012 upgrade. Research collection remains disabled/daily_limit0; bounded prospective collection still requires a separate Owner decision.
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
