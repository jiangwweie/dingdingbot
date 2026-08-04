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
| Verified at | `2026-08-04 18:29 CST`; direct PostgreSQL, systemd, release-marker and Binance readonly evidence |
| Production commit | `b88415faeff025be50f6140dbd8f93efaaf3c98f` |
| Production tag | `tokyo-runtime-2026.08.04.2`; annotated, immutable, and verified on `origin` |
| Production release | `/opt/brc/releases/brc-trading-kernel-b88415faeff0` |
| Production-commit certification | `1079 passed`; full unit/architecture, integration and full-chain suites, Ruff, Mypy and diff checks pass |
| Deployment phase | The sealed `0003_portfolio_admission_observability` authority received one regular release; target-bound Batch refresh, condition-wait, same-SHA fix-forward resume and official Entry promotion are verified |
| PostgreSQL identity | Alembic, runtime metadata, Registry, armed Policy authority, Seed and runtime capabilities agree with the production commit and schema |
| History preservation | The database-bound `0002` preservation digest and proof remain exact after migration; terminal lineage was retained without downgrade, dual write, old-schema reader or manual lifecycle DML |
| StrategyUniverse deployment | The six approved vNext Event Universes are exact Active with no Warming Universe; the target-bound seven-member Certification Batch completed from direct Reconciliation evidence |
| Dynamic policy | Policy version `5` is active with the approved v4 portfolio AdmissionDecision, Exposure Family, directional-risk and minimum-materialization boundaries; new ENTRY submission is enabled |
| Runtime ownership | Observation, Entry, Lifecycle and Reconciliation are active and enabled; the Entry write fence is absent after official promotion |
| Runtime stability | Two post-promotion samples show zero Worker restarts across all four persistent services |
| Current PostgreSQL activity | Readonly certification passes with no active Ticket domain, non-flat Position, active Budget Reservation, unresolved Exchange Command or open Incident |
| Exchange postflight | Binance is `independent_sides` and `cross`; the seven approved instruments remain configured at `5x`, with no non-flat position or open-order domain |
| Current live acceptance | Official Entry promotion is complete; the runtime can now admit a new natural in-scope Ticket through the guarded kernel path |
| Full capability | `promote-full` remains outside this deployment and still requires a reviewed natural v4 Ticket closure and final requirement audit |
| Scope boundary | Funding ownership and broader Incident-quality work were not changed by this release |

## Current Performance Snapshot

The 2026-08-04 deployment postflight verifies immediate release stability, not
a representative host-capacity benchmark.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Worker stability | Observation, Entry, Lifecycle and Reconciliation remained active/enabled across two post-promotion samples; all restart counters remained zero | The full persistent runtime cadence is stable after promotion |
| Entry boundary | Official promotion armed the persisted Policy, started Entry while fenced and removed the write fence last | New ENTRY authority was granted only after fresh database, systemd and Binance gates passed |
| Internal truth | Flat readonly certification passed twice with no runtime activity or open Incident | The migrated PostgreSQL authority is clean and internally consistent |
| External truth | Binance remained flat with no open-order domain; account mode and configured leverage stayed exact | External postflight agrees with internal flatness |
| Release identity | Current symlink, release markers, runtime environment and PostgreSQL metadata all identified the same commit and schema | No old/new writer identity overlap was observed |

A longer resource-envelope sample remains a separate operational observation;
it is not a gate retroactively added to this completed deployment.

## Remaining Critical Path

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Natural acceptance | A new in-scope v4 signal creates one Ticket and protected position through the official Entry path |
| 2 | External truth closure | Exchange is flat and has no residual ENTRY, protection, TP, EXIT, or cancel order |
| 3 | Internal truth closure | Ticket terminal, budget released, Netting Domain released, Reconciliation matched |
| 4 | Economics closure | Settlement and Review persist exact realized economics, including explicit funding availability |
| 5 | Incident audit | Zero open runtime incident and zero unknown command outcome |
| 6 | Full policy promotion | Run and certify `promote-full` only after steps 1-5 pass |
| 7 | Final requirement audit | Re-run local and Tokyo evidence and close every acceptance item |

## Current Stop Conditions

Exchange writes remain fail-closed for wrong identity, invalid account mode,
stale or contradictory facts, same-domain occupancy, missing budget or Initial
Stop, duplicate or unknown command outcome, schema/code mismatch, old-writer
overlap, or official-path bypass.

The `0003` production deployment, regular release and official Entry promotion
are complete and sealed. The broader rebuild program is not final until one new
natural v4 Ticket reaches terminal flatness with no residual orders, released
budget, successful Reconciliation, Settlement, Review, zero Incident,
certified `promote-full`, and the final requirement audit.
