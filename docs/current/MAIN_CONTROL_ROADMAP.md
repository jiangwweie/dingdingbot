---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-08-13
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

| Area | Verified state |
| --- | --- |
| Integration branch | `dev` |
| Verified at | `2026-08-10 13:35 CST`; direct PostgreSQL, systemd, Nginx, public HTTPS and Binance readonly evidence |
| Production commit | `1c3063bf520a52c15b144bf613884c7e00147bfc` |
| Production tag | `tokyo-runtime-2026.08.10.2`; annotated, immutable, and verified on `origin` |
| Production release | `/opt/brc/releases/brc-trading-kernel-1c3063bf520a` |
| Production-commit certification | The exact six-command Release Certification passes: unit/architecture, integration, full-chain, Ruff, Mypy and diff checks |
| Deployment phase | The sealed `0004_owner_control_plane` authority, Owner Console and Strategy Workbench received regular releases; the resumable migration repair, independent static release and reconciled flatten-operation completion repair remain active |
| PostgreSQL identity | Alembic, runtime metadata, Registry, armed Policy authority, Seed and runtime capabilities agree with the production commit and schema |
| History preservation | The database-bound `0002` preservation digest and proof remain exact after migration; terminal lineage was retained without downgrade, dual write, old-schema reader or manual lifecycle DML |
| StrategyUniverse deployment | The six approved vNext Event Universes are exact Active with no Warming Universe; the target-bound seven-member Certification Batch passed during the regular release |
| Owner controls | Global new ENTRY is enabled at Policy version `9`; `SOR-001` is paused at Strategy Control version `2`, so both SOR 15-minute Events reject new admission while the other registered StrategyGroups remain enabled |
| Runtime ownership | Observation, Entry, Lifecycle and Reconciliation are active and enabled; the Entry write fence is absent after official promotion |
| Runtime stability | Observation, Entry, Lifecycle, Reconciliation and Owner API are active/enabled with zero restarts in the post-release samples |
| 2026-08-10 PostgreSQL postflight | No nonterminal Ticket, non-flat Position, active Budget Reservation, unresolved Exchange Command or open Incident existed at the completed release postflight |
| 2026-08-10 exchange postflight | Binance was `independent_sides` and `cross`; the seven approved instruments were configured at `5x`, with no non-flat position or open-order domain at the completed release postflight |
| Controlled flatten acceptance | Natural Ticket `ticket:fb99bed7ca2b28e49b6346d498b8a23c` entered through the official path, was exited by Owner authorization `owner-authorization:3ae1622e6e124ffab141b350f89e3330`, and is terminal, reconciled, settled and reviewed; the durable Operation is `completed` with no blocker |
| Owner Console | `https://jiaoyingpan.cloud/trading/` is active behind the existing Nginx HTTPS server; the Strategy Workbench static route is deployed from the exact verified build, and its protected API returns `401` before password-plus-TOTP authentication |
| Nginx isolation | Existing Nginx configuration was not rewritten; syntax passes, the Owner API remains Unix-Socket proxied, and unauthenticated data access returns `401` |
| Full capability | Natural v4 closure evidence now exists; `promote-full` and the final requirement audit remain explicit follow-up operations and were not bundled into this release |
| M1 multi-asset planning | Owner adopted the same-Venue Binance USDⓈ-M TradFi Equity Product Family, same-account isolated RuntimeProfile, eight candidates plus QQQ/SPY references, LONG/SHORT Observation and REGULAR-only first Entry boundary; local M2–M4 implementation is authorized without production deployment, real TradFi Entry or capital increase |
| M2–M4 local candidate | Product Compatibility, Instrument Center, Product-filtered controlled Warming Universe edit, neutral TradFi RuntimeProfile, and `SOR-US-EQ-PERP-001` LONG/SHORT detector and ExitPolicy are implemented on the focused branch. M6 supersedes the earlier observation-only Policy/Profile identities; production remains unchanged |
| M5 local candidate | Signal-owned TradFi SOR Observation Outcomes, automatic bounded Product/Session refresh, version-isolated Strategy Observation reads and Owner Console path review are implemented locally. Focused acceptance proves no AdmissionDecision, CapacityClaim, Ticket, Exchange Command or venue mutation is created; production remains unchanged and TradFi Entry remains disabled |
| M6 local candidate | The focused branch implements direct small-capital TradFi live Entry through the official Signal → AdmissionDecision → CapacityClaim → Ticket → durable Command chain, one `policy-main / Policy v4` Event-to-Profile scope, neutral `tradfi-equity-usdm-v1`, Product action-time gates, account-wide Owner flatten/Drain, Strategy Live Control and Instrument threshold display. Focused backend, migration, deployment, document, frontend, Ruff, Mypy and diff verification pass. The candidate remains local and unpushed; no R4 deployment, Entry promotion, Strategy resume or exchange write has occurred |
| Scope boundary | Funding ownership and broader Incident-quality work were not changed by this release |

## Deferred Release Candidate

The Owner reported active production exposure on 2026-08-11 and explicitly
chose natural lifecycle completion instead of manual or deployment-driven
flattening. This report supersedes the prior flat postflight only for current
deployment readiness; exact current PostgreSQL and exchange state has not been
refreshed by this documentation-only action.

| Area | Deferred state |
| --- | --- |
| Candidate commit | `ae2462562245ee236669407d997cbfaff1ca3020` — `feat(deploy): split owner console release paths`; it contains the prior Ticket price-map candidate plus M0.5 R1/R2 release separation |
| Candidate branch | Exact commit is on focused branch `codex/owner-console-phase1-20260805`; it is not a production tag and has not been pushed or deployed by this work |
| Classification | Exact `1c3063bf..ae246256` classification is `R2`; affected runtime is only `brc-owner-console-api.service`, with no flatness or Kernel Release Certification requirement |
| Certification | Exact focused Owner API Certification Manifest is `pass` for Schema `0004_owner_control_plane`; the static frontend exact production build also passes |
| Previous candidate | `5e902453360f884d2ec2a7d8c6c92568d9459f4a` remains immutable certified provenance but is superseded as the proposed R1/R2 deployment target by `ae246256...` |
| Production identity | Production remains `1c3063bf520a52c15b144bf613884c7e00147bfc` and `tokyo-runtime-2026.08.10.2`; the new candidate has not changed the current release symlink, PostgreSQL identity or services |
| Deferral decision | No Controlled Flatten, no deployment, no Owner Policy change, no Entry service/fence change and no StrategyGroup control change are authorized by this record |
| Pre-M0.5 activation boundary | Under the currently installed combined release path, deployment still requires Entry fencing and exact internal/external flatness; existing Tickets continue naturally and no deployment-driven flattening is authorized |
| M0.5 classification | The exact `1c3063bf..ae246256` change set classifies as `R2`: Owner API and static presentation only, with no Schema, Registry, Owner Policy, runtime-authority or Exchange Command change |
| M0.5 local state | The R0-R4 classifier, independent R1/R2 release roots, focused Owner API certification, schema-compatible API startup and removal of Kernel artifact preservation are implemented locally on the focused branch; no production service or symlink has changed |
| M0.5 activation boundary | After explicit Owner deployment confirmation, exact candidate `ae246256...` may activate through R1/R2 without flatness or Kernel service changes |
| Supersession | Replacing `ae246256...` with a later candidate requires another explicit record and an exact passing focused certification |

## Current Performance Snapshot

The 2026-08-10 deployment postflight verifies immediate release stability, not
a representative host-capacity benchmark.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Worker stability | Observation, Entry, Lifecycle, Reconciliation and Owner API are active/enabled; all restart counters are zero | Trading and control-plane cadence is stable after release and promotion |
| Entry boundary | Entry started while fenced, Global ENTRY resumed through the TOTP-protected Owner API, and the write fence was removed last | Non-SOR admission is restored without reopening SOR-001 |
| Internal truth | PostgreSQL reports zero active trading residue and the flatten Operation is `completed` | The controlled exit, cleanup, Settlement and Review projection agree |
| External truth | Binance is flat with no open-order domain; account mode, margin mode and configured leverage remain exact | External postflight agrees with internal flatness |
| Web isolation | Nginx syntax passes; the public Strategy Workbench static `index.html` matches the locally verified build hash and the Owner Console remains same-origin behind the Unix Socket | The new frontend and API did not replace or reconfigure unrelated services |
| Release identity | Current symlink, release markers, runtime environment and PostgreSQL metadata identify `1c3063bf` and `0004_owner_control_plane` | No old/new writer identity overlap was observed |

A longer resource-envelope sample remains a separate operational observation;
it is not a gate retroactively added to this completed deployment.

## Remaining Critical Path

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Natural lifecycle continuation | The current production release protects, exits, reconciles, settles and reviews every existing Ticket without deployment-driven flattening |
| 2 | M0.5 local acceptance | Complete focused code review, Owner API tests, release-classifier checks, frontend build, Ruff, Mypy and document authority checks without production mutation |
| 3 | M0.5 R1/R2 activation | Owner explicitly confirms deployment; record the exact superseding static/API Commit, install the split release roots and prove Kernel workers and `/opt/brc/current` were untouched |
| 4 | Full policy promotion | After current exposure is naturally flat, run and certify `promote-full` from current PostgreSQL and Binance facts with exact Kernel identity |
| 5 | Final requirement audit | Re-run local and Tokyo evidence and close every acceptance item |
| 6 | M6 combined R4 activation | The local M0.5 + M2–M6 candidate is sealed and remains unpushed. After explicit Owner deployment confirmation, refresh current PostgreSQL, Binance, systemd and Nginx facts; require exact flatness and R4 gates; perform the forward `0005` migration and readonly postflight; then use TOTP Strategy resume to open direct small-capital TradFi ENTRY |

## Current Stop Conditions

Exchange writes remain fail-closed for wrong identity, invalid account mode,
stale or contradictory facts, same-domain occupancy, missing budget or Initial
Stop, duplicate or unknown command outcome, schema/code mismatch, old-writer
overlap, or official-path bypass.

The `0004` production deployment, Owner Console Strategy Workbench, Owner
control plane, controlled flatten acceptance and official Entry restoration are
complete and sealed.
`SOR-001` remains paused by explicit Owner control. The broader rebuild program
is not final until M0.5 activation, `promote-full` and the final requirement
audit are certified from current direct evidence. Until an explicit M0.5
deployment confirmation, production remains on
`1c3063bf520a52c15b144bf613884c7e00147bfc` and active exposure follows the
existing certified lifecycle.
