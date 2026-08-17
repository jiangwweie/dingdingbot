---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-08-14
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
| Verified at | `2026-08-14 00:18 CST`; direct PostgreSQL, systemd, release-marker, Owner control API and Binance readonly evidence |
| Production commit | `3fa2e21ce52bc3c203c721be4b696dc4265fcf96` |
| Production tag | `tokyo-runtime-2026.08.13.1`; annotated, immutable, verified locally and pushed to `origin` |
| Production release | `/opt/brc/releases/brc-trading-kernel-3fa2e21ce52b` |
| Production-commit certification | `6/6 pass`; unit/architecture, integration, full-chain, Ruff, Mypy and diff checks passed for the exact deployed commit |
| Deployment phase | R4 stopped-and-flat fix-forward deployment completed with `status=pass`; Product Schedule parsing and StrategyUniverse manifest certification defects were repaired before the final successful release |
| PostgreSQL identity | Alembic and runtime authority identify `0005_tradfi_instrument_center`; Registry, Policy, Seed and runtime capabilities agree with the deployed commit and schema |
| History preservation | The forward migration retained certified terminal lineage without downgrade, dual write, old-schema reader, active-position handover or manual lifecycle DML |
| StrategyUniverse deployment | Eight Universes are Active, zero are Warming, 58 scopes are Active and 15 instruments are eligible |
| Owner controls | Global new ENTRY is enabled at Policy version `12`; Entry write fence is absent; Crypto `SOR-001` is paused at Strategy Control version `2`, and TradFi `SOR-US-EQ-PERP-001` is enabled at Strategy Control version `2` |
| Runtime ownership | Observation, Entry, Lifecycle and Reconciliation are active and enabled; the persistent Entry worker is in its normal arbitration loop |
| Runtime stability | All four persistent workers report zero restarts; Entry has produced repeated `no_candidate` results after promotion without service error |
| Current PostgreSQL activity | No active Ticket, non-flat Position, unresolved Exchange Command or open Incident exists; the 16 active TradFi scopes are Entry-ready, all 16 Readiness rows report `signal_absent`, and there is no fresh unadmitted TradFi Signal |
| Exchange postflight | Binance reports zero non-flat position domains and zero open-order domains; wallet balance is `449.26301574U`, account mode remains compatible and all 15 eligible instruments are configured at `5x` |
| Product session | Eight traded TradFi Equity instruments resolve to `active / regular`; their unavailable corporate-event feed is an explicit warning, not an Entry rejection, while the two reference instruments remain outside executable membership |
| Current live acceptance | Official Entry Promotion completed with `status=promoted`; `SOR-US-EQ-PERP-001` was resumed through the TOTP-protected Owner API and may now produce a natural real Ticket through the official chain |
| Controlled flatten acceptance | The earlier natural controlled-flatten Ticket remains certified terminal, reconciled, settled and reviewed; no new controlled flatten or lifecycle DML was performed by this deployment |
| Owner Console | The existing public HTTPS Owner Console and Nginx isolation were preserved; this R4 deployment did not replace or rewrite unrelated Nginx service configuration |
| Multi-asset capability | Product Compatibility, Instrument Center, bounded Product/Session refresh, independent `SOR-US-EQ-PERP-001` semantics and direct official-chain TradFi ENTRY capability are deployed under the shared `policy-main / Policy v4` capital authority |
| Full capability | Entry Promotion and TradFi Strategy resume are complete; the first natural TradFi lifecycle, `promote-full` and the final requirement audit remain explicit follow-up evidence |
| Scope boundary | Crypto `SOR-001` remains paused; no Crypto SOR Entry authority was restored, and funding ownership and broader Incident-quality work were not changed |

## Owner Console R1/R2 Release

| Area | Verified state |
| --- | --- |
| Verified at | `2026-08-17`; direct Tokyo release marker, systemd, Unix-Socket health and public HTTPS evidence |
| Release commit and tag | Static Owner Console and Owner API both run `92b7b222cd3392e96cc61d23ceeb4887bbca080b`, tagged `tokyo-runtime-2026.08.17.1` and pushed with `dev` |
| Scope | R2: only `/opt/brc/owner-console/current`, `/opt/brc/owner-console-api/current` and `brc-owner-console-api.service` changed; no schema, Policy, Registry, Nginx configuration or Kernel Worker action occurred |
| Postflight | Static and API release markers match; API Unix-Socket `/healthz` returns `{"status":"ok"}`; public HTTPS succeeds; all four Kernel Workers remain `active`, `enabled` and at zero restarts |
| Recovery observation | The independent API deployment fallback selected system Python `3.10`, while current API imports require Python `3.11+`; the first target startup failed and the API was recovered with the server's existing Python `3.12` Kernel environment. The target API is healthy, but the automated R2 fallback/rollback path requires a focused P2.2 fix before the next Owner API release |

## Deployment Repairs Closed

| Defect | Root cause | Production resolution |
| --- | --- | --- |
| TradFi `warm_facts_invalid` | Binance returns the live Equity schedule under `marketSchedules.EQUITY.sessions`, while the parser expected a symbol-keyed schedule | Product Schedule parsing now accepts the production response shape; the production-shaped regression formed seven Warming Facts with zero Signal, Ticket or Command |
| StrategyUniverse readonly certification failure | Manifest comparison incorrectly depended on Event row ordering | Certification now compares the manifest semantically and independently of Event order; the final readonly postflight passes identity and semantic-digest checks |
| Initial R4 bootstrap timeout | A pre-fix failed Observation cadence had already scheduled the next attempt at the following closed 15-minute bar | The deployment resumed through the official bounded bootstrap path after the next natural closed bar; no synthetic lifecycle write or exchange mutation was used |

## Current Performance Snapshot

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

## Remaining Critical Path

The natural TradFi acceptance below is an independent production-evidence lane.
It does not block local infrastructure, documentation, or Owner Console work.
Any later production deployment still refreshes current PostgreSQL, systemd,
release-marker, and exchange facts and follows the exact release contract.
The parallel engineering order is owned by
`MULTI_ASSET_STRATEGYGROUP_ROADMAP.md`: infrastructure foundation first,
Owner product control second, and strategy-learning expansion last.

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

The `0005_tradfi_instrument_center` R4 deployment is complete and sealed at
`3fa2e21ce52bc3c203c721be4b696dc4265fcf96`. Global Entry is enabled at Policy
version `12`, Entry is active with no write fence, `SOR-US-EQ-PERP-001` is
enabled and `SOR-001` remains paused. The current TradFi chain is therefore
waiting only for a natural eligible Signal. A 15-minute readonly heartbeat
observes chain progress and abnormalities without performing runtime mutation.
