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
| Verified at | `2026-08-13`; direct PostgreSQL, systemd, release-marker and Binance readonly postflight evidence |
| Production commit | `3fa2e21ce52bc3c203c721be4b696dc4265fcf96` |
| Production tag | `tokyo-runtime-2026.08.13.1`; annotated, immutable, verified locally and pushed to `origin` |
| Production release | `/opt/brc/releases/brc-trading-kernel-3fa2e21ce52b` |
| Production-commit certification | `6/6 pass`; unit/architecture, integration, full-chain, Ruff, Mypy and diff checks passed for the exact deployed commit |
| Deployment phase | R4 stopped-and-flat fix-forward deployment completed with `status=pass`; Product Schedule parsing and StrategyUniverse manifest certification defects were repaired before the final successful release |
| PostgreSQL identity | Alembic and runtime authority identify `0005_tradfi_instrument_center`; Registry, Policy, Seed and runtime capabilities agree with the deployed commit and schema |
| History preservation | The forward migration retained certified terminal lineage without downgrade, dual write, old-schema reader, active-position handover or manual lifecycle DML |
| StrategyUniverse deployment | Eight Universes are Active, zero are Warming, 58 scopes are Active and 15 instruments are eligible |
| Owner controls | Global new ENTRY is disabled at Policy version `11`; Entry write fence is present; Crypto `SOR-001` is paused at Strategy Control version `2`, and TradFi `SOR-US-EQ-PERP-001` is paused at Strategy Control version `1` |
| Runtime ownership | Observation, Lifecycle and Reconciliation are active and enabled; Entry is inactive and disabled while the Entry write fence remains installed |
| Runtime stability | Observation, Lifecycle and Reconciliation report zero restarts in the completed postflight sample |
| Current PostgreSQL activity | No active Ticket, non-flat Position, unresolved Exchange Command or open Incident exists; current certification is flat and portfolio admission postflight passes |
| Exchange postflight | Binance reports zero non-flat position domains and zero open-order domains; wallet balance is `449.26301574U`, account mode remains compatible and all 15 eligible instruments are configured at `5x` |
| Product session | Eight traded TradFi Equity instruments resolve to `regular`; the two reference instruments currently resolve to `unavailable` and do not authorize ENTRY |
| Current live acceptance | The R4 runtime is production-installed and readonly-certified, but no new real ENTRY is currently authorized because Global Entry is disabled, Entry is stopped/fenced and both SOR StrategyGroups are paused |
| Controlled flatten acceptance | The earlier natural controlled-flatten Ticket remains certified terminal, reconciled, settled and reviewed; no new controlled flatten or lifecycle DML was performed by this deployment |
| Owner Console | The existing public HTTPS Owner Console and Nginx isolation were preserved; this R4 deployment did not replace or rewrite unrelated Nginx service configuration |
| Multi-asset capability | Product Compatibility, Instrument Center, bounded Product/Session refresh, independent `SOR-US-EQ-PERP-001` semantics and direct official-chain TradFi ENTRY capability are deployed under the shared `policy-main / Policy v4` capital authority |
| Full capability | Entry Promotion, TradFi Strategy resume, `promote-full` and the final requirement audit remain explicit follow-up actions and were not bundled into this release |
| Scope boundary | Crypto `SOR-001` remains paused; funding ownership and broader Incident-quality work were not changed by this release |

## Deployment Repairs Closed

| Defect | Root cause | Production resolution |
| --- | --- | --- |
| TradFi `warm_facts_invalid` | Binance returns the live Equity schedule under `marketSchedules.EQUITY.sessions`, while the parser expected a symbol-keyed schedule | Product Schedule parsing now accepts the production response shape; the production-shaped regression formed seven Warming Facts with zero Signal, Ticket or Command |
| StrategyUniverse readonly certification failure | Manifest comparison incorrectly depended on Event row ordering | Certification now compares the manifest semantically and independently of Event order; the final readonly postflight passes identity and semantic-digest checks |
| Initial R4 bootstrap timeout | A pre-fix failed Observation cadence had already scheduled the next attempt at the following closed 15-minute bar | The deployment resumed through the official bounded bootstrap path after the next natural closed bar; no synthetic lifecycle write or exchange mutation was used |

## Current Performance Snapshot

The 2026-08-13 postflight verifies immediate release safety and authority
alignment. It is not a representative strategy-performance or host-capacity
benchmark.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Worker stability | Observation, Lifecycle and Reconciliation are active/enabled with zero restarts; Entry remains inactive/disabled | Readonly observation and safety lifecycle cadence are stable without granting new trade authority |
| Entry boundary | Policy version `11` has `new_entry_submit_enabled=false`; Entry Fence is present; both SOR controls are paused | Deployed capability cannot create a new real Ticket until separate Owner-controlled promotion and resume actions pass their current gates |
| Internal truth | Certification reports zero Ticket, Position, Command and Incident residue; eight Universes are Active with zero Warming | PostgreSQL authority is internally clean and ready for a later controlled activation decision |
| External truth | Binance reports zero positions and open orders; 15 eligible instruments remain at `5x` | External flatness agrees with internal flatness and the approved capital configuration |
| Release identity | Current release, runtime metadata and PostgreSQL schema identify `3fa2e21c` and `0005_tradfi_instrument_center` | No old/new writer identity overlap remains after the R4 release |
| Product readiness | Eight traded TradFi instruments are in regular session; two reference instruments are unavailable | Product/session facts are readable without treating unavailable references as executable instruments |

## Remaining Critical Path

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Global Entry Promotion | Revalidate exact commit, schema, flatness, Policy and Binance facts; enable the official Entry path and remove the Entry Fence only through the approved promotion workflow |
| 2 | TradFi Strategy activation | Explicitly resume `SOR-US-EQ-PERP-001` after Global Entry is promoted; keep Crypto `SOR-001` paused unless the Owner separately changes that strategy control |
| 3 | First natural TradFi lifecycle | One in-scope signal progresses through AdmissionDecision, CapacityClaim, immutable Ticket, durable Command, protection, exit, Reconciliation, Settlement and Review |
| 4 | External and internal closure | Exchange has no residual position or order; PostgreSQL has no active Ticket, reservation, unresolved Command or Incident for the completed episode |
| 5 | Full policy promotion | Run and certify `promote-full` only from current exact production facts and an accepted terminal reviewed Ticket |
| 6 | Final requirement audit | Re-run local and Tokyo evidence and close every remaining acceptance item |

## Current Stop Conditions

Exchange writes remain fail-closed for wrong identity, invalid account mode,
stale or contradictory facts, same-domain occupancy, missing budget or Initial
Stop, duplicate or unknown command outcome, schema/code mismatch, old-writer
overlap, or official-path bypass.

The `0005_tradfi_instrument_center` R4 deployment is complete and sealed at
`3fa2e21ce52bc3c203c721be4b696dc4265fcf96`. Global Entry remains disabled,
Entry remains stopped and fenced, and both `SOR-001` and
`SOR-US-EQ-PERP-001` remain paused. The deployed TradFi capability therefore
exists without current exchange-write authority. Later Entry Promotion,
Strategy resume and `promote-full` are separate Owner-controlled operations.
