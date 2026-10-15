---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-10-15
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

### MPG recovery R3 software release complete; genuine Owner ENTRY Resume verified

| Area | Directly verified state |
| --- | --- |
| Snapshot time | 2026-10-15 20:48–21:46 Asia/Shanghai; official regular deployment, exact markers/PG identity, four Worker process identities, API health and exchange readonly facts |
| Integration branch | `dev` |
| Production commit | `e7f86acf1287a0cb395702331add1cd9f5354d2d` |
| Production tag | `tokyo-runtime-2026.10.15.2`, immutable annotated tag pushed to origin at the exact production SHA |
| Production-commit certification | Exact R3 PASS: 1,681 Unit/Architecture, 1,695 Integration, 58 Full-chain; Ruff, Mypy196 and diff PASS. Four existing periodic-resource cases are excluded by the formal portfolio, not claimed PASS. Total certification3653.140s |
| Kernel / schema | Official regular R3 deployment PASS in199853ms, `entry_enabled=false`; Alembic/runtime `0011_orb_session_1h_v1`; no migration, no A+B deployment or research enablement |
| Source migration | Earlier `0009_capacity_policy_v0`→0010→0011 lineage retained. This MPG regular release changes only code identity and performs no DDL or data backfill |
| Seed / preservation | Seed `sha256:98e0fe3c28c4f7dad37c96a5a63ca2be91ec38b4ccca8be791b8325f41366522` retained; official source/target and running postflight preservation PASS for Universe/Authority/Owner controls/terminal lineage |
| Owner controls | Policy version `26` has `new_entry_submit_enabled=true`; genuine Owner Web Resume/TOTP verified after the maintenance pause at Policy25. Deployment preserved controls; strategy, capital/risk and Dynamic authorizations were not changed |
| Runtime ownership | Observation, Entry, Lifecycle and Reconciliation active/enabled, NRestarts0; each process environment identifies exact e7f86acf/0011. Official promotion preparation returned `prepared_owner_paused`; operational fence removed while paused; later genuine Owner Resume/TOTP at Policy26 restored new-entry permission |
| Owner API / Console | Owner API stopped only for final flat write-quiescent cutover, then restarted; `/healthz` returns ok. Existing compatible API/static release retained; no frontend/API release performed |
| Controlled closure | Owner used Web controlled exit for BRF2 ADAUSDT short Ticket `ticket:254270cf7923f2adefb6b179ddc58e77`. Official cancellation/reconciliation resolved transient unknown outcome; Ticket/Aggregate terminal, budget released, domain released, Settlement/Review complete; no manual exchange write |
| Trading facts | Cutover/20:54 flat/order-free PASS. At21:46, authorized runtime has a new BRF2 LTCUSDT short Ticket `ticket:68ceee4346d67c056a7756c514761152`, quantity10.419, Aggregate position_protected; exact full reduce-only stop and TP1 orders match PG/exchange; pending Commands0. Current runtime is no longer flat |
| ExitProfile postflight | Existing Profile/Binding authority and frozen exits preserved; no exit-policy changes or strategy parameter changes |
| Dynamic Selection postflight | Original controls and terminal lineage retained; MPG new recovered target ACTIVE with original Vacuum resolved. Owner Resume alone is not strategy readiness: MPG still needs22:00 recovery close and rebase before ENTRY |
| MPG state | Old20:00 failed Generation retained. New `generation:a2659598d42a31f91caad16666eb82b5077728b5acbc9ea38acbe0a80cecae28` ACTIVE at21:10:05.904; old Vacuum RESOLVED_ACTIVE. Recovery Authority `authority:recovery:081667d130253cb16b04598aae3b6fca26c5f99e7b876bde57652ea6a2b49913`, effective/first eligible22:00, expires23:00; 14scopes still selection_recovery_not_effective at21:44. Exact new code hash PASS; direct normal successor after rebase still needs natural future evidence |
| Entry restoration | Software/postflight complete; official preparation followed by genuine Owner Console Resume/TOTP restored new-entry permission. Entry active/enabled with fence absent; no synthetic authorization or agent Policy update |
| SOR retirement | Crypto `SOR-001` remains permanently ENTRY-disabled; no strategy or Selection scope resumed by this release |
| A+B boundary | Historical `fcea10c8` R4 PASS preserved, not deployed. MPG fix port is preparation only; new combined SHA requires its own fresh R4 before any0012 release. Research remains disabled by default |

Sources: `.local/mpg-production-e7f86acf/deployment.log`, exact R3 manifest,
`four-worker-identity.json`, `postdeploy-safety.json`, API health and deployment
preservation markers; `.local/mpg-r3-e7f86acf/` retains certification and earlier
readonly samples. Generated outputs are display-only. Action-time PG/exchange/
systemd/marker facts remain required before any later production action.

### Current Dynamic acceptance boundary

| Strategy | Current boundary | Remaining evidence |
| --- | --- | --- |
| MPG-001 | Direct-successor guard deployed; recovered target ACTIVE21:10, Vacuum resolved; Authority first eligible22:00 | Legal22:00 recovery/rebase and later direct normal successor; no simulated production acceptance |
| CPM / MI / BRF2 / SOR-1H | Existing Universe/Authority/Selection controls preserved by exact deployment postflight; global ENTRY resumed by Owner; action-time gates still required | Fresh per-family business availability must be read at action time; service running is not activation proof |
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
Regime/maintenance-pause boundaries. ALPHA-02A implementation and local R4 are complete on a separate undeployed candidate; the new combined candidate still needs exact R4.
Local parameter tuning is deferred; console redesign and USDC adaptation remain
separate backlog. Research does not change capital, exits, selection or scope.

The Owner completed genuine new SOR-1H enable/Dynamic controls and global
ENTRY Resume through the Console; Policy24 was the earlier live posture; maintenance pause at Policy25 has now been superseded by genuine Owner Resume/TOTP at Policy26. Official Entry promotion and real paired Dynamic takeover
are complete. The SOR deployment monitor must not redeploy completed software.
Natural lifecycle evidence remains separate acceptance; Generic recovery
also completed with CPM current Authority at09:22:04.378.
protected future Owner changes retain their normal authentication requirements.
The Owner subsequently required joint release with BRC-RECON-RELIABILITY-01:
reconciliation expedite fairness, Universe lock ordering, superseded
certification Claim handling and minimal stagnation visibility. Repair and exact
joint-candidate certification are release prerequisites even if flatness is met;
do not deploy the prior SOR-1H-only candidate. See the
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
