---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-08-04
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
| Verified at | `2026-08-04 16:56 CST`; direct PostgreSQL, systemd, release-marker and Binance readonly evidence |
| Production commit | `4ecc60aeb674b620dafed1a41d0de1187e312b44` |
| Production tag | `tokyo-runtime-2026.08.04.1`; annotated, immutable, and verified on `origin` |
| Production release | `/opt/brc/releases/brc-trading-kernel-4ecc60aeb674` |
| Production-commit certification | `1070 passed`; full unit/architecture, integration and full-chain suites, Ruff, Mypy and diff checks pass |
| Deployment phase | Exact stopped, flat, forward-only `0002_sor_v3_strategy_group_capacity -> 0003_portfolio_admission_observability` compatible upgrade is sealed |
| PostgreSQL identity | Alembic, runtime metadata, Registry, Policy v4, Seed and runtime capabilities agree with the production commit and schema |
| History preservation | The database-bound `0002` preservation digest and proof remain exact after migration; terminal lineage was retained without downgrade, dual write, old-schema reader or manual lifecycle DML |
| StrategyUniverse deployment | The six approved vNext Event Universes are exact Active with no Warming Universe; all seven approved instruments have fresh eligible certification |
| Dynamic policy | Policy version `4` is active with portfolio AdmissionDecision, Exposure Family, directional-risk and minimum-materialization authority; new ENTRY submission remains disabled |
| Runtime ownership | Observation, Lifecycle and Reconciliation are active and enabled; Entry is inactive, disabled and protected by `/etc/brc/trading-kernel.write-fenced` |
| Runtime stability | Two post-release samples show zero Worker restarts; Reconciliation restart count did not grow |
| Current PostgreSQL activity | Readonly certification passes with no active Ticket domain, non-flat Position, active Budget Reservation, unresolved Exchange Command or open Incident |
| Exchange postflight | Binance is `independent_sides` and `cross`; the seven approved instruments remain configured at `5x`, with no non-flat position or open-order domain |
| Current live acceptance | The v4 release is deployed and safety workers are live; Entry promotion and any new natural Ticket are separate explicit post-release actions |
| Full capability | `promote-full` remains outside this deployment and still requires a reviewed natural v4 Ticket closure and final requirement audit |
| Scope boundary | Funding ownership and broader Incident-quality work were not changed by this release |

## Current Performance Snapshot

The 2026-08-04 deployment postflight verifies immediate release stability, not
a representative host-capacity benchmark.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Worker stability | Observation, Lifecycle and Reconciliation remained active/enabled across two samples; all restart counters remained zero | The target safety cadence is stable immediately after cutover |
| Entry boundary | Entry remained inactive/disabled; Policy v4 kept new ENTRY disabled and the write fence remained present | Schema deployment did not implicitly grant trading authority |
| Internal truth | Flat readonly certification passed twice with no runtime activity or open Incident | The migrated PostgreSQL authority is clean and internally consistent |
| External truth | Binance remained flat with no open-order domain; account mode and configured leverage stayed exact | External postflight agrees with internal flatness |
| Release identity | Current symlink, release markers, runtime environment and PostgreSQL metadata all identified the same commit and schema | No old/new writer identity overlap was observed |

A longer resource-envelope sample remains a separate operational observation;
it is not a gate retroactively added to this completed deployment.

## Remaining Critical Path

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Entry promotion decision | Explicitly promote Entry only after a separate Owner decision for the deployed v4 authority |
| 2 | Natural acceptance | A new in-scope v4 signal creates one Ticket and protected position through the official Entry path |
| 3 | External truth closure | Exchange is flat and has no residual ENTRY, protection, TP, EXIT, or cancel order |
| 4 | Internal truth closure | Ticket terminal, budget released, Netting Domain released, Reconciliation matched |
| 5 | Economics closure | Settlement and Review persist exact realized economics, including explicit funding availability |
| 6 | Incident audit | Zero open runtime incident and zero unknown command outcome |
| 7 | Full policy promotion | Run and certify `promote-full` only after steps 1-6 pass |
| 8 | Final requirement audit | Re-run local and Tokyo evidence and close every acceptance item |

## Current Stop Conditions

Exchange writes remain fail-closed for wrong identity, invalid account mode,
stale or contradictory facts, same-domain occupancy, missing budget or Initial
Stop, duplicate or unknown command outcome, schema/code mismatch, old-writer
overlap, or official-path bypass.

The `0003` production deployment is complete and sealed while Entry remains
intentionally fenced. The broader rebuild program is not final until a separate
Entry promotion is authorized, one new natural v4 Ticket reaches terminal
flatness with no residual orders, released budget, successful Reconciliation,
Settlement, Review, zero Incident, certified `promote-full`, and the final
requirement audit.
