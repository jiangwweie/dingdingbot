---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-10-12
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

The target remains one complete multi-StrategyGroup, multi-position trading
system. New ENTRY admission is globally serialized; protected Tickets in
different Netting Domains progress concurrently.

## Current Verified State

### 2026-10-12 Unified Generic Selection / Capacity V0 — DEPLOYMENT_COMPLETE

**Software deployment is complete. Trading has not been resumed.** This table
supersedes the dated preparation and prior release snapshots below.

| Area | Directly verified production fact |
| --- | --- |
| Production commit | `962e19dd611a6692d0531d872d668659c216ebdd` |
| Production tag | `tokyo-runtime-2026.10.12.1`; immutable local tag resolves to the exact certified production commit |
| Production-commit certification | Exact R4 PASS: 1,541 Unit/Architecture, 1,627 PostgreSQL Integration and 54 Full-chain tests; Ruff, Mypy (192 files), diff, Golden integrity and production Core parity PASS |
| Kernel / schema | `/opt/brc/releases/brc-trading-kernel-962e19dd611a`; Alembic and runtime identity are `0009_capacity_policy_v0` |
| Runtime Seed | `sha256:a053adc206ecb7fa2fe9ee813c779bca5a6feb654a0a5256879e9aaefa1945ed`; release marker, PostgreSQL and readonly recomputation agree |
| Owner API / Console | Both active release symlinks identify the production commit; exact R2/R1 PASS, API service/socket health PASS, static index hash matches and public `/trading/` returns 200 |
| Migration / preservation | Stopped-flat `0007 -> 0008 -> 0009`, forward-only; all Writers including Owner API stopped; fresh authoritative 14 MPG/MI provenance proofs PASS; exact source-row preservation digest `sha256:8dda6247770de7d8809bb8ba06566e84e9665e496636941bf4fe4c9599b714a7` PASS before runtime identity rotation |
| Capacity Policy | Version `18` installed atomically by the formal compatible deployment identity transaction; same Strategy/side maximum 2; family limits `long_continuation=2 / opening_range=2 / rally_failure_short=1`; global 3 Tickets, per-Ticket 2%, gross 6% and directional 4% stop-risk boundaries unchanged |
| Owner controls | Policy version `18` has `new_entry_submit_enabled=false`; no automatic Dynamic activation or ExitProfile mutation |
| Generic installed Specs | CPM, MPG, MI and BRF2 exact frozen Specs installed through the typed release-owned repository boundary after preservation/identity PASS; each numeric certification PASS, zero mismatches, 96 archives; CPM/BRF2 463 cutoffs each, MPG/MI 1,852 each; all four controls remain `static_baseline` with no pending activation |
| SOR retirement | `SOR-001` Entry remains paused at control version 6; historical Selection control/version and drained standalone OWNER_PAUSED Vacuum preserved; no resume/delete/new ENTRY authority |
| Runtime ownership | Observation, Lifecycle and Reconciliation active; Owner-authorized Entry service restart completed after deployment: Entry active/enabled but its startup wrapper waits for the retained write fence, so the trading loop is not running; Owner API active. All checked services have zero restarts after release |
| PostgreSQL / exchange | Readonly integrity, flatness, Registry/Seed/Universe identities PASS; active Ticket/position, unresolved Command and open Incident all zero; Binance positions/open orders zero, independent sides/Cross/configured 5x |
| Dynamic Selection postflight | Source counts exactly preserved: Jobs 38, Snapshots 38, Generations 18, Vacuums 18, Authorities 53, Gap Audits 19; active Universe membership digest unchanged; Spec installation created no Job/Snapshot/Generation/Authority/Ticket/Command |
| ExitProfile postflight | 8 Profiles / 8 immutable Bindings / 8 current pointers / 8 ACTIVATED events, exact catalog PASS; no switch or retirement |
| Resource boundary | Kernel slice remains 1 CPU / 1 GiB / Tasks 128; direct postflight memory about 409 MiB / 7 tasks; server available memory about 1.57 GiB and release volume free about 11 GiB |
| Deferred evidence | 24h/long soak remains unperformed, not PASS. Legacy Static-batch Entry promotion flags remain false with the preserved actual 22-instrument Universe; they are not claimed to authorize trading |

（来源：exact candidate R4/R1/R2 manifests、four-Spec numeric verifier、formal
Tokyo deploy result `status=pass / elapsed_ms=128890`、typed Spec installation
result、fresh Tokyo PostgreSQL/Binance/systemd/API/static/resource postflight。）

The first deployment attempt found a readonly revision-discovery allowlist
omission for the valid `0007` source before any DDL. Five regression cases proved
RED then GREEN; the replacement clean candidate received a new complete R4.
At a subsequent advisory check, Observation was between hourly close updates;
the provenance gate correctly refused the temporary mixed-time source. After
the natural update completed and every Writer stopped, the fresh 14-proof source
passed without deleting or fabricating any lifecycle facts.

R4 performance work now streams output, prints the 30 slowest Integration cases,
clones isolated preseeded Generic test templates and removes the duplicate
migration invocation (all migration tests remain in full Integration). Whole
Integration remained about 79m37s: no material whole-suite speedup is claimed.
The measured longest resource case was 256.21s; numerous real Authority/Trading
chains, not a stuck process or an unbounded 24h wait, dominate the suite. Further
portfolio consolidation is separate from this completed deployment.

### Current Remaining Control Actions

**2026-10-12 Entry restoration repair — local verification only:** the focused
`codex/entry-resume-current-universe-20261012` branch replaces fixed initial
membership/Batch restoration assumptions with exact PG current pointers,
fresh member certifications and current Owner Resume/TOTP proof; removes the
promoter's auto-arm operation; and checks scope/Policy/runtime drift and
post-I/O expiry before unfencing. Final Unit/Architecture 1,567 PASS, complete
Full-chain 54 PASS, final restoration PG/chain slice 13 PASS, additional
Bootstrap/schema/Policy/Owner slice 46 PASS, Ruff/Mypy/diff PASS. A candidate
readonly query against actual Tokyo facts returned 22 members / readiness true /
Owner proof false. This did not install code or modify production. The repair
still requires its exact same-schema release certification and reconciliation
of the existing regular-deployment wrapper's remaining Static assumptions before
installation. No new Release PASS or repaired production runtime is claimed.
The deployed release/tag above remain unchanged and Entry stays fenced.

- No remaining software installation or migration step for this release.
- Entry service is restarted/enabled, but new ENTRY remains closed/fenced; ordinary trading restoration must follow
  fresh official gates, not the legacy fixed-Static manifest assumptions or a
  direct Policy/SQL bypass.
- Four Generic strategies are technically installed and numerically certified,
  not live Dynamic. First activation remains an explicit official Owner action;
  there is no additional economic/research/Shadow waiting gate.
- Crypto SOR remains permanently retired. Existing lifecycle/history is not
  rewritten, and no additional exchange mutation was performed in deployment.

### 2026-10-11 Preparation Evidence — Superseded By The Release Above

Owner authorized the unified Generic Selection / Capacity V0 stopped-flat
release after necessary assurance. The Owner then closed Entry and flattened
through the Console. Fresh readonly source verification and Binance probing
confirmed the maintenance facts below. This is advisory evidence; the official
deployment must repeat it after every migration writer, including the Owner API,
is stopped. No new release is sealed and no target schema is active yet.

| Area | Directly verified maintenance fact |
| --- | --- |
| Running Kernel | `/opt/brc/releases/brc-trading-kernel-dbe62a32c4ae`; runtime commit `dbe62a32c4ae74d3fd82c58a33196c6dc6f81357`, schema `0007_exit_profile_authority_v1` |
| Owner API / static | Both release symlinks identify `34ead07f7fc6225ac365b39bddcd7c21bb6cf4db`; these supersede the older Console snapshot below |
| Owner Entry | Policy revision `17`, `new_entry_submit_enabled=false`; the four current Worker services remain active pending release assurance |
| PostgreSQL closure | Zero active Ticket, position, reservation, Netting Domain, unresolved Command, open Incident, nonterminal Aggregate and missing terminal Review |
| Binance advisory | Zero non-flat and open-order domains in the 22-instrument current Universe probe; independent sides, Cross, configured 5x |
| Static comparison source | 14 exact MPG/MI provenance proofs pass; source shape, Registry, Policy, capabilities and runtime identity pass |
| SOR retirement | Strategy Entry control revision `6` remains paused; Selection control revision `9` still records the historical Dynamic mode. Its standalone `OWNER_PAUSED` Vacuum is drained and must remain a negative ENTRY fence, not be resumed or deleted |
| Preservation source | All 74 source tables / 28,651 rows were scanned in advisory verification; the digest is refreshed after writers stop, never reused from this advisory snapshot |
| Release assurance | Candidate `c9934a569702be9adc481801631b030820c61897` exact R4 failed its Integration command: 1,608 passed / 14 failed, 4,974.19s. Causes were stale table/index/revision/nullable-policy assertions, retired 401 step-up behavior, a missing retired-SOR fixture prerequisite, and using latest seed code on old-schema migration fixtures. Test-only corrections passed the complete affected 118-test slice and 1,533 Unit/Architecture tests; production code remains unchanged. No R4 PASS manifest exists for that candidate; new clean candidate certification is required |
| Long-duration validation | Owner removed isolated-server / 24h soak as a predeployment prerequisite. Long-run evidence remains unperformed and deferred to postdeployment observation, not PASS |
| Production mutation | No service stop, migration, release activation, Policy B installation or exchange write has been performed by the agent in this maintenance preparation |
| Staged services | Kernel, Owner API and static Console archives for `c9934a569702be9adc481801631b030820c61897` were prepared without activation. Owner API/static exact manifests passed; all active symlinks still identify the prior running releases |

（来源：本任务 Owner 授权、东京 PostgreSQL source verifier、Binance readonly probe、release symlink及systemd查询。）

### Previous Sealed Release Snapshot — 2026-09-06

| Area | Verified state |
| --- | --- |
| Integration branch | `dev` |
| Verified at | `2026-09-06`; direct Tokyo PostgreSQL, systemd and Binance USDⓈ-M readonly evidence after Dynamic fallback recovery and official Entry Promotion |
| Production commit | `dbe62a32c4ae74d3fd82c58a33196c6dc6f81357` |
| Production tag | `tokyo-runtime-2026.09.06.2`; records the R3 repair deployment and Entry promotion, not successful Dynamic activation |
| Production release | `/opt/brc/releases/brc-trading-kernel-dbe62a32c4ae` |
| Production-commit certification | R3 `pass`; complete unit/architecture, PostgreSQL integration, full-chain, Ruff, Mypy and diff gates passed for the exact deployed commit |
| Deployment phase | First-activation Authority repair completed through the official same-Schema R3 stopped-flat release path on `0007`, followed by `promote_entry.py: status=promoted`; no migration or forced position exit occurred |
| PostgreSQL identity | Alembic and runtime authority identify `0007_exit_profile_authority_v1`; Registry, Policy, Seed and runtime capabilities agree with `dbe62a32` |
| History preservation | Both forward revisions preserved certified lineage; B completed exact `0006` source preservation before its `0007` runtime identity rotation |
| StrategyUniverse deployment | Eight Universes remain Active, zero are Warming, 58 scopes are Active and the Static SOR pair remains the current pair |
| Owner controls | Policy version `16` has `new_entry_submit_enabled=true`; `SOR-001` Selection Control is `static_baseline` at version `7`, with no pending activation |
| Runtime ownership | Observation, Entry, Lifecycle and Reconciliation are active/enabled; the Entry fence is absent after official Promotion |
| Current PostgreSQL activity | After the ADA Ticket completed and the repair was deployed/promoted: zero active Ticket, projected position, unresolved Command, open Incident and active reservation; readonly certification `pass` |
| Exchange postflight | Fresh Binance deployment/promotion proofs report zero non-flat position and open-order domains, independent sides, Cross margin and configured 5x for all 15 current instruments |
| Dynamic Selection postflight | The `2026-09-06 00:00 UTC` attempt selected seven of 22 ready Candidates at 01:00 UTC; both targets staged at 01:18:45 UTC, then first-activation Authority validation repeatedly failed. At 01:30:10 UTC audited `FALLBACK_PREVIOUS` restored Static pair; no Dynamic activation succeeded |
| ExitProfile postflight | Eight immutable ExitProfiles, eight initial Bindings, eight current pointers and eight `ACTIVATED` events exist; no Profile switch/retirement side effect occurred |
| New trading activity | Official Entry Promotion produced `ticket:1c612dcecd76efca3c96db7c79819fad`: CPM ETH LONG, Entry/Initial Stop/TP1 accepted and Aggregate `position_protected` |
| Scope boundary | Static Entry is live. A new Dynamic activation and any ExitProfile switch/retirement remain separate exact Owner actions |

### First-Activation Repair Acceptance

The deployed repair corrects Static mode on a proposed `ACTIVE_NEW` grant,
closes displaced activation audits on fallback, accepts repeated consistent
suppression evidence, preserves historical fence/drain timestamps across
retargeting, handles recovered Owner-Pause `VALID_EMPTY`, and logs safe exception
locations. Exact R3 passed; 76 Selection PostgreSQL tests include first and
subsequent switching, seven-member runtime activation and atomic fault rollback.
（来源：exact R3 manifest；Tokyo PostgreSQL/systemd and official deployment/promotion results）

No failed generation was revived and no new Dynamic authorization was created.
The next authorized Session must prove actual `ACTIVE_NEW`, atomic LONG/SHORT
membership, completed audit, resolved Vacuum and `dynamic_selection` control.
The separate Static-manifest assumptions in deployment/Entry re-promotion tools
remain documented in the incident review and are not claimed repaired.

## Owner Console R1/R2 Release

| Area | Verified state |
| --- | --- |
| Verified at | `2026-08-31`; direct Tokyo API release marker, systemd and Unix-Socket health evidence |
| Static release | Static Owner Console remains at `92b7b222cd3392e96cc61d23ceeb4887bbca080b` |
| Owner API release | Owner API runs `552bc3d3f0bd807d5fefa7d284c6b440f6619cdb`, R2 certified against Schema `0007_exit_profile_authority_v1` |
| Scope | R2 changed only `/opt/brc/owner-console-api/current` and `brc-owner-console-api.service`; it did not change Kernel release, Policy, Entry fence, Registry, Nginx or exchange state |
| Postflight | API exact marker matches, service is active and Unix-Socket `/healthz` returns `{"status":"ok"}`; Kernel remains `dd047941` with Entry fenced and safety workers active |
| Deployment repair | API release provisioning now bootstraps pip through the target venv Python from the release directory and waits for Unix-Socket readiness before judging health, avoiding rollback to a Schema-incompatible old API |

## Dynamic First-Activation Incident And Recovery

The first Dynamic Session is not recoverable as trading authority and must never
be revived. The current facts below come from direct Tokyo PostgreSQL, Owner API,
systemd and Binance readonly inspection on `2026-09-04`.（来源：Tokyo production
PostgreSQL、Owner API journal、systemd、Binance USDⓈ-M readonly facts；exact local
R3 release certification）

| Area | Current authority |
| --- | --- |
| Failed Session | `2026-09-01 00:00 UTC`; Candidate data and Snapshot completed, but no Session Authority was granted |
| Root cause A | `temporarily_unavailable` certification was collapsed into a terminal non-eligible result, causing premature fallback |
| Root cause B | fallback Gap Audit ran before the first eligible `01:15 UTC` close and persisted `AUTHORITY_GAP_SOURCE_INTEGRITY_FAILED` from an invalid four-bar window |
| Owner containment | `SOR-001` is paused at Strategy Control version `4`; the failed Generation is `ABANDONED`, its Vacuum is `OWNER_PAUSED`, and existing Tickets continue normal protection and exit |
| Permission repair | The Owner control role now has the exact Vacuum current/event privileges required by the official Pause path; the tracked source repair is isolated on `codex/owner-console-vacuum-grant-fix` |
| Runtime repair | `dbe62a32c4ae74d3fd82c58a33196c6dc6f81357` is deployed and R3-certified; the latest first-activation repair and acceptance boundary are recorded above |
| Recovery result | The September 6 attempt completed audited `FALLBACK_PREVIOUS`; Selection Control version `7` cleared pending mode and retained the Static pair. Its terminal history remains unchanged by the repair |
| Current gate | Static Entry is live. The failed Dynamic generation is terminal and must not be revived; the next Dynamic attempt remains a new Owner/TOTP action |

## Deployment Repairs Closed

| Defect | Root cause | Production resolution |
| --- | --- | --- |
| TradFi `warm_facts_invalid` | Binance returns the live Equity schedule under `marketSchedules.EQUITY.sessions`, while the parser expected a symbol-keyed schedule | Product Schedule parsing now accepts the production response shape; the production-shaped regression formed seven Warming Facts with zero Signal, Ticket or Command |
| StrategyUniverse readonly certification failure | Manifest comparison incorrectly depended on Event row ordering | Certification now compares the manifest semantically and independently of Event order; the final readonly postflight passes identity and semantic-digest checks |
| Initial R4 bootstrap timeout | A pre-fix failed Observation cadence had already scheduled the next attempt at the following closed 15-minute bar | The deployment resumed through the official bounded bootstrap path after the next natural closed bar; no synthetic lifecycle write or exchange mutation was used |
| Lifecycle entry-fill time inversion | `EntryFilled.occurred_at_ms` represented PostgreSQL observation time and could be seconds later than the exact Binance ENTRY fill, causing every lifecycle fill-window validation to fail | Lifecycle now freezes ENTRY Command creation as the legal lookup lower bound, derives the actual exposure start from exact attributed fill timestamps, and persists account-blocking Incident/Owner Monitor facts for deterministic lifecycle contradictions |

## Historical Performance Snapshot

The 2026-08-14 post-promotion snapshot verifies immediate trade authority,
runtime safety and identity alignment. It is not a representative
strategy-performance or host-capacity benchmark.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Worker stability | Observation, Entry, Lifecycle and Reconciliation are active/enabled with zero restarts | The complete persistent runtime cadence is operating after Entry Promotion |
| Entry boundary | Policy version `12` has `new_entry_submit_enabled=true`; Entry Fence is absent; TradFi SOR is enabled while Crypto SOR remains paused | A fresh eligible TradFi Signal may proceed through serialized admission, while Crypto SOR remains excluded by its scoped control |
| Internal truth | Certification reports zero Ticket, Position, Command and Incident residue; eight Universes are Active with zero Warming; 16 TradFi scopes are Entry-ready | PostgreSQL authority is clean and the current first blocker is `signal_absent`, not a policy, identity, service or Product gate |
| External truth | Binance reports zero positions and open orders; 15 eligible instruments remain at `5x` | External flatness agrees with internal flatness and the approved capital configuration |
| Release identity | Current release, runtime metadata and PostgreSQL schema identify `3fa2e21c` and `0005_tradfi_instrument_center` | No old/new writer identity overlap remains after the R4 release |
| Product readiness | Eight traded TradFi instruments are `active / regular` with eight fresh eligible certifications; corporate-event data is unavailable and recorded as a warning | Current Product gates permit Entry when spread, mark/index deviation and all remaining action-time facts pass |

## Completed Two-Hop R4 Capability Deployment

The stopped-flat maintenance window completed with distinct forward Alembic
revisions and fresh Phase-B PostgreSQL/Binance proofs for each hop. Entry
remains fenced after target postflight.（来源：Tokyo direct PostgreSQL, systemd,
release-marker and Binance readonly evidence；exact R4 manifests）

| Hop | Exact candidate | Target schema | Local release evidence | Production scope after postflight |
| --- | --- | --- | --- | --- |
| A | `codex/sor-dynamic-universe-v0-deploy-plumbing-fix` @ `4bf4cd2369e6b2c7cce0f669da787de91f1a92b6` | `0006_sor_dynamic_selection_v0` | R4 `pass`; production deployment `pass` | Static SOR pair preserved; Dynamic runtime facts remain zero; Entry fenced |
| B | `dev` @ `dd047941495634fff3fdda54a1e96f7b1a5ad20e` | `0007_exit_profile_authority_v1` | R4 `pass`; source preservation and required `0007` fix-forward `pass` | Eight Profile/Binding facts seeded; Entry fenced |

The two hops are deliberately separate forward Alembic revisions:

```text
0005 production
-> A / 0006 postflight, Entry fenced
-> B / 0007 postflight, Entry fenced
```

They must not be collapsed into one migration or deployed by the `0007` code as
the first hop. A failure after either schema commit is target-schema
fix-forward only. Software installation does not authorize Crypto `SOR-001`
resume, first Dynamic activation, ExitProfile switch or exchange write.（来源：
`TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`；R4 manifests in local Git metadata）

## Historical Program And Acceptance Record — Superseded

The natural TradFi acceptance below is an independent production-evidence lane.
It does not block local infrastructure, documentation, or Owner Console work.
Any later production deployment still refreshes current PostgreSQL, systemd,
release-marker, and exchange facts and follows the exact release contract.
The parallel engineering order is owned by
`MULTI_ASSET_STRATEGYGROUP_ROADMAP.md`. The first local/read-only **P3-X** study
does not support static Symbol ranking as the current path: historical
Instrument outcomes differ, but fixed ranks do not persist out of sample. The
current research lane therefore moves to a frozen, theory-driven **SOR Dynamic
Selection V0** based on point-in-time market state and EventSpec geometry. The
local Historical Replay has now passed all frozen quantitative gates: Dynamic 7
improved Tail3 / directional slot-day by **24.1%** versus Static 7, exceeded all
100 deterministic Random 7 controls, preserved `Selected > Near > Not Selected`,
and improved both LONG and SHORT. Owner has therefore superseded the independent
Forward Shadow route. The production detailed design has completed targeted review
and is approved only for an Implementation Plan handoff.
DS-00 subsequently proved that the external Replay headline used binary64 feature
arithmetic. The approved Decimal Golden removes seven equal-ratio boundary artifacts
and freezes Dynamic Tail3 `1,323` instead of `1,324`; this is a representation
correction, not a Feature、threshold、Top-N or Candidate change, and the external
report remains research provenance rather than production arithmetic authority.
The proposed design keeps generic PostgreSQL Selection facts and StrategyUniverse
as the single Instrument-membership authority, adds immutable time-bounded
SelectionSessionAuthority, and uses a scoped Strategy Entry Vacuum at Admission,
Ticket issuance and ENTRY dispatch. The architecture is now explicitly split into
three durable planes: Selection ends after `SNAPSHOT_READY`; an independently leased
Materialization Coordinator owns `VALID_EMPTY/NO_CHANGE/DESIRED`, Vacuum, drain,
warming, atomic activation and post-fence fallback; Deployment restores durable
authority and completes without waiting for Dynamic materialization. Owner has
frozen public Binance Candidate data, whole-attempt `SOURCE_FAILED` for any Candidate
source-integrity gap, `VALID_EMPTY` for zero eligible members, `NO_CHANGE` for an
unchanged operational pair, unfinished-ENTRY cancellation during reconfiguration,
retained vacuum-attributed partial fills only when a positive TP1+Runner split is
legal, first-trigger suppression across any audited Authority gap, serial LONG/SHORT
warming, an atomic final pair switch, newest-valid-selection supersession, Owner Pause
precedence, and
gated post-fence `FALLBACK_PREVIOUS` to the exact pre-switch Active pair. Every
Selection Period already operating in `dynamic_selection` receives a Selection-Period
`PRE_FENCE_CONTINUITY` Authority from its exact current pair before the Selection
outcome exists; it continues through Selection success, source/compute failure and
materialization waiting, and ends only when ordinary `NO_CHANGE` replaces it or the
Vacuum commit atomically cuts it off. Selection failure only appends the continuity
reason and never decides whether previous instruments may trade. Any SOR Authority
whose eligible-close coverage is not continuous requires a durable Authority Gap
Audit before grant: Vacuum activation/fallback audits exact `previous ∪ desired`,
while late continuity and late ordinary `NO_CHANGE` audit only the current pair. The
Authority freezes `first_eligible_close_time_ms`; positive suppression and
checked-negative proof are both durable, and a transaction crossing the canonical
close boundary rolls back, extends the audit and advances to the next close. Pause
Resume with unchanged members must drain, audit and resolve its Pause Vacuum before a
new `NO_CHANGE` revision. Generation Desired facts do not pre-allocate Universe IDs or
copy Dynamic target members; each actual immutable Universe writes the sole Generation
FK in its creation transaction. No second materialization-link table, direct Universe
Snapshot FK or copied rollback-member fact is created. Universe digests remain
membership-only. First `static_baseline -> pending dynamic_selection` activation is a
special case: existing Static authority remains authoritative until the first Dynamic
outcome. If its post-fence materialization fails, transition-scoped
`FALLBACK_PREVIOUS` freezes the exact Static pair, failed Generation, Gap Audit,
suppression and first eligible close while `selection_mode` remains `static_baseline`.
Selection/Authority periods begin at the `D 01:00` decision boundary, while
`session_start_ms=D 00:00` remains only SOR identity. `VALID_EMPTY` is forward-only:
unfinished ENTRY drains, but earlier legal Tickets/fills and protected lifecycle are
not rewritten or flattened. Release compatibility
is a thin projection of the existing Release Certification manifest, not a second release
engine; releases remain classified as `COMPATIBLE_RESTART` or
`REQUIRES_RUNTIME_REMATERIALIZATION`. The design changes no capital, leverage or
Alpha rule, but it necessarily extends Ticket lineage, durable cancel commands and
Lifecycle reduction for the narrow retained-partial branch. The final targeted
architecture review requirements are incorporated and the design status is
`DESIGN_APPROVED`. The P3-X.3 Implementation Plan has passed independent review with
status `PLAN_APPROVED / LOCAL_IMPLEMENTATION_COMPLETE / production_authority=NONE`. Owner-authorized
**DS-00 Golden/Evidence/Test Portfolio** execution is complete with a reproducible
961×24 Decimal Golden and zero production dependency. Independent review approved that
Golden as the sole DS-03/DS-09 Selection parity baseline. The active implementation scope
then completed **DS-01 Pure Domain Contracts** with 25 focused tests, 946 Fast Unit/Architecture
tests, full tracked Ruff/Mypy, and exact 23,064-member Golden digest parity. A targeted Codex
review subsequently froze `DS01_APPROVED`. Owner has now authorized the complete local
code/test/certification sequence: DS-02 forward Schema/PostgreSQL ownership and DS-03 Selection Runner/immutable Snapshot are approved. DS-04 completed Selection-Period continuity、
Snapshot disposition、`VALID_EMPTY` intent fencing、durable `PENDING -> DESIRED` Generation handoff、
Authority Gap Audit、trigger suppression and canonical first-eligible-close recovery. DS-05 has now completed
Admission/Ticket/dispatch Vacuum enforcement、durable ENTRY cancel、unknown recovery、zero/full/partial quantity
resolution、retained-partial protection and atomic `VALID_EMPTY`/Generation drain finalization with **228 focused**
and **916 Fast Unit/Architecture** tests. DS-06 has now completed serial LONG/SHORT warming、no-authority staged
scopes、atomic pair activation、exact post-fence fallback、newest-Snapshot supersession and Owner Pause precedence.
It also closes superseding `VALID_EMPTY` on the existing Vacuum、preserves the concrete fallback cause、terminates
invalidated pending Gap Audits and makes committed terminal Authorities idempotent coordinator results. DS-07
completed four new-ENTRY Authority boundaries and compatible birth-lineage propagation; DS-08 completed independent
runtime hosting/recovery、Reconciliation Vacuum facts、Owner Pause、bounded readonly and exact Release
Compatibility Fact persistence. **DS-09/DS-10 now complete the local sequence** with tracked Golden/Core parity in
R4 certification, a formal TOTP-protected first Dynamic activation boundary, exact 24-Candidate readonly audit,
zero unexpected Dynamic runtime-fact deployment postflight, bounded Selection-period status CLI and the stopped-flat
deployment/first-activation evidence package. The exact candidate is identified only by its clean-HEAD R4 manifest.
First Dynamic activation remains separately gated.（来源：Owner active-task decision；
`docs/superpowers/specs/2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md`；
`docs/superpowers/plans/2026-08-23-sor-dynamic-instrument-selection-trading-v0-implementation-plan.md`）

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Natural opportunity | Maintain the current 15-minute readonly monitor until an eligible TradFi SOR Signal appears; `signal_absent` is the normal waiting state |
| 2 | First natural TradFi lifecycle | One in-scope signal progresses through AdmissionDecision, CapacityClaim, immutable Ticket, durable Command, protection, exit, Reconciliation, Settlement and Review |
| 3 | External and internal closure | Exchange has no residual position or order; PostgreSQL has no active Ticket, reservation, unresolved Command or Incident for the completed episode |
| 4 | Full policy promotion | Run and certify `promote-full` only from current exact production facts and an accepted terminal reviewed Ticket |
| 5 | Final requirement audit | Re-run local and Tokyo evidence and close every remaining acceptance item |

## Current Stop Conditions

Exchange writes remain fail-closed for wrong identity, invalid account mode,
stale or contradictory facts, same-domain occupancy, missing budget or Initial
Stop, duplicate or unknown command outcome, schema/code mismatch, old-writer
overlap, or official-path bypass.

The current production identity and posture are exclusively the 2026-10-12
table above. Schema is `0009_capacity_policy_v0`, Policy version is `18`, Entry
service is active/enabled waiting for its operational fence, new ENTRY Policy remains disabled, four Generic controls are Static with no
pending activation, and Crypto SOR remains retired/paused. Older dated snapshots
and historical acceptance records do not resume trading or authorize activation.
