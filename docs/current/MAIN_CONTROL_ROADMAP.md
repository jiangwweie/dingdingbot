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

### SOR-1H and reconciliation reliability software release complete; Dynamic activation pending

| Area | Directly verified state |
| --- | --- |
| Snapshot time | 2026-10-15 00:04–00:08 Asia/Shanghai; official release output and bounded fresh PostgreSQL/systemd/journal reads |
| Integration branch | `dev`; later documentation commits do not change production identity |
| Production commit | `b8e82fb6b6dc24fdce36c845ac491b801fe561e5` |
| Production tag | `tokyo-runtime-2026.10.15.1`, annotated exact runtime tag created and pushed to origin |
| Production-commit certification | Exact R3/R2/R1 PASS: 1,681 Unit/Architecture, 1,693 Integration, 58 Full-chain; Ruff, Mypy196 and diff PASS. Earlier exact c06 R4 covered the0010→0011 migration; it is not claimed as b8 certification |
| Kernel / schema | Official same-schema regular release PASS, `entry_enabled=false`; Alembic/runtime `0011_orb_session_1h_v1`; Kernel/API/static now use the same exact deployed commit |
| Seed / Registry | Seed `sha256:98e0fe3c28c4f7dad37c96a5a63ca2be91ec38b4ccca8be791b8325f41366522`; source preservation and exact target gates PASS |
| Source migration | Stopped0010→0011 source preservation verified39,669 source rows. Original c06 cutover completed migration/identity but its postflight was BLOCKED by target Selection preparation; the successor official regular release resolved final software acceptance without rewriting source evidence |
| Owner controls | Policy version `23` has `new_entry_submit_enabled=false`; original capital/risk boundary retained. Existing four strategy controls and original Generic intent/negative fences preserved |
| Runtime ownership | Observation, Lifecycle and Reconciliation active, all NRestarts0 at the post-release check; ENTRY inactive/disabled/write-fenced. No Entry promoter or Owner Resume occurred |
| Owner API / Console | Exact R2 API and R1 static official deployment/smoke PASS, maintenance window ended |
| New SOR-1H pair | Official independent bootstrap complete for LONG/SHORT, two current Active Universes with fourteen warmed member-direction scopes. New strategy control paused/version1; Selection `static_baseline`, no pending mode, no epoch |
| Dynamic acceptance | New SOR-1H has no real Dynamic Universe/Authority takeover yet; first protected enable/Selection controls require genuine Owner TOTP. Chat deployment authorization is retained and must not be replaced by another deployment confirmation request |
| Trading facts | Official cutover external flat/order-free gates PASS; fresh post-release active Ticket/position/command/Incident counts all zero; no release-owned order dispatched |
| Readiness |32/32 current certification and10 Active Universes passed immediately before release. Latest running readiness is false after ordinary target cadence resumes; the earlier snapshot is not reusable as later ENTRY authority |
| ExitProfile postflight | Existing frozen exits retained; independent new Events use the established Crypto15m exit bindings. No exit/stop/strategy sizing change |
| SOR retirement | Old `SOR-001` remains paused/version6 and permanently ENTRY-disabled; TradFi remains paused |
| Remaining evidence | Genuine new strategy/Selection authentication, real paired Dynamic takeover and natural lifecycle evidence. Software release does not claim profitability, a natural Ticket or long-run soak |

Sources: `.local/sor1h-final-regular-deployment.log`, exact certification
manifests, official API/static release logs, official bootstrap completion,
fresh PostgreSQL/systemd and bounded journals. Generated output is display-only;
PostgreSQL and exchange remain runtime authority.

### Current Dynamic acceptance boundary

| Strategy | Current Selection control | Actual acceptance |
| --- | --- | --- |
| SOR-1H-001 | Static baseline, no epoch or pending mode; paused | Independent pair prepared; first genuine Dynamic authorization/takeover pending |
| CPM / MPG / MI / BRF2 | Original Dynamic mode and epoch retained | Historical failed recovery fences preserved; mode alone does not prove current Universe/Authority takeover |
| SOR-001 | Permanently retired for new ENTRY | Historical Universe retained; never resumed by this release |

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
Regime/maintenance-pause boundaries. Detailed implementation remains unstarted.
Local parameter tuning is deferred; console redesign and USDC adaptation remain
separate backlog. Research does not change capital, exits, selection or scope.

The latest Owner instruction authorizes joint repair deployment and new SOR-1H
Dynamic intent without repeated deployment confirmation, while explicitly
keeping ENTRY paused. The active monitoring task continues only the remaining
control/real-Dynamic acceptance; it must not redeploy the completed software.
Genuine protected Owner authentication remains mandatory. Keep new ENTRY paused.
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
