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

One PostgreSQL-backed kernel serializes new ENTRY while protected Tickets
continue concurrently across independent Netting Domains.

## Current Verified State

### Software deployed; Owner resumed; Dynamic activation pending

| Area | Directly verified state |
| --- | --- |
| Integration branch | `dev` |
| Snapshot time | 2026-10-12 13:32 Asia/Shanghai; bounded readonly PG / Generic status inspection, not an exchange-flat proof |
| Production commit | `1ac0d4ae8fe10937923cecd9fd4948765c42420c` |
| Production tag | `tokyo-runtime-2026.10.12.2`; exact deployed candidate; project publication does not move this tag |
| Production-commit certification | Exact R3 PASS: 1,581 Unit/Architecture, 1,639 Integration, 54 Full-chain; Ruff, Mypy193 and diff PASS. Earlier Generic/Capacity R4 PASS belongs to the preserved release evidence |
| Kernel / schema | Kernel, API and static release links identify production commit; Alembic/runtime schema `0009_capacity_policy_v0`; no migration in the restoration repair |
| Seed / Registry | `sha256:a053adc206ecb7fa2fe9ee813c779bca5a6feb654a0a5256879e9aaefa1945ed`; source/target integrity certified |
| Owner controls | Policy version `19` has `new_entry_submit_enabled=true`; exact Resume/TOTP proof was verified after Owner action. Capacity B remains same-strategy/side2, continuation2/opening_range2/short1, global3 and unchanged stop-risk/margin/leverage |
| Runtime ownership | Observation, Entry, Lifecycle, Reconciliation and API active; Entry fence absent. Cleanup/reload left Worker/API PIDs unchanged and restart counters0 |
| Owner API / Console | Exact R2/R1 PASS for deployed commit; current API uses Unix socket and frontend /trading/; latest Nginx smoke returned200 |
| Entry restoration | Official paused preparation removed only operational Fence, not Policy; later Owner Resume enabled ENTRY. No repeat promoter/server operation is required |
| Dynamic Selection postflight | Four Specs installed and four authorized pending Dynamic intents; all still `static_baseline` at this read, control version2. No current-epoch successful Snapshot/Authority confirmed. Pending is not activation success |
| PostgreSQL activity | Active Tickets2, nonzero projected positions2, open Incidents0 at the readonly snapshot. No current exchange position/order proof was collected for this documentation task; do not claim flatness or complete lifecycle |
| ExitProfile postflight | Historical release certification:8 Profiles/8 Bindings/8 Current/8 ACTIVATED; no Profile switch/retirement authorized by this documentation release |
| SOR retirement | Crypto `SOR-001` permanently retired and Entry paused/version6 despite historical Dynamic mode; TradFi SOR Entry also paused |
| Resource posture | Cleanup postflight at12:50: root59G/used29G/available29G/50%; available memory1354MiB, load0.86/0.48/0.50. These are dated snapshots, not a representative CPU benchmark |
| Server retention | Owner authorized removal of101 historical Kernel/API/static releases; only current version remains. Systemd journal3-day low-priority bounded hourly rotation/vacuum installed; journal footprint4.1G to1.3G. Databases, credentials, shared Python and unrelated applications untouched |
| Nginx cleanup | Jewelry Demo static directory and both routes removed; nginx -t PASS and graceful reload; CPA/New API/trading HTTP200; no trading restart |
| Deferred evidence | Full long-run soak NOT PASSED; offline MAE/MFE projector not delivered; complete GS-13 task acceptance and new Generic live economic evidence not claimed |
| Probe contract | Actual ENTRY action-fact validity30,000ms; maintenance probe also bounded30s but is separate display/maintenance evidence. This release did not loosen per-order freshness |

Sources: exact committed R3/R4/R2/R1 manifests and archived deployment outputs;
fresh Tokyo PostgreSQL/read-only Generic controls and service/symlink inspection;
Owner Resume/activation actions; bounded cleanup and Nginx postflight. Docs are
not runtime authority.

### Owner Dynamic intents — Beijing time on snapshot date

| Strategy | Frozen Spec | Selection cutoff | Scheduled materialization boundary | Verified state |
| --- | --- | --- | --- | --- |
| CPM | CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1 | 16:00 | 17:00 | Authorized pending; no successful Snapshot confirmed |
| BRF2 | BRF2_RESIDUAL_EXTENSION_V0 | 16:00 | 17:00 | Authorized pending; no successful Snapshot confirmed |
| MPG | MPG_PERSISTENT_LEADERSHIP_SCORE_V1 | 13:00 | 14:00 | Authorized pending; no successful Snapshot confirmed |
| MI | MI_POSITIVE_IMPULSE_RECENCY_V0 | 13:00 | 14:00 | Authorized pending; no successful Snapshot confirmed |

Static ENTRY can continue before a genuine switching Vacuum; existing protected
lifecycle always continues. Current readonly presentation reports
`ALL_CURRENT_MEMBERS_BLOCKED` from historical Static warm expiry; that display
does not independently prove actual Static admission is blocked. It must not be
used to claim healthy opportunity-waiting either. Actual tickets now exist,
but first Dynamic Selection execution/takeover still needs direct evidence.

## Publication Node

The project node `release-2026.10.12.1` consolidates Generic Selection,
ExitProfile Authority, Capacity B, Entry restoration and current documentation.
It is a repository publication on synchronized dev/main, not a new server
deployment or new exchange authorization. Exact Git tag/branch verification is
performed at publication. Historical production tags stay immutable.

## Remaining Critical Path

1. Verify actual first Generic Snapshot, materialization, current Universe and
   Authority after each authorized boundary; distinguish pending/valid-empty/
   fallback/failure without inventing success.
2. Follow naturally admitted Tickets through protection, exit, reconciliation,
   settlement and review; no forced trade, SQL repair or redundant Resume.
3. Keep long-run engineering evidence and offline projector explicitly deferred;
   publish any future proof separately, without claiming existing gates PASS.
4. Review accurate runtime blockers/presentation if needed; document publication
   is not an authorization to bypass freshness, comparison rebase or capacity.

## Current Stop Conditions

No exchange write under wrong identity, stale/contradictory action-time facts,
unknown outcome, same-domain occupancy, missing stop/budget, schema mismatch or
old-writer overlap. Existing exposure keeps its frozen lifecycle. Crypto SOR
must remain disabled. Documentation, main merge and Release publication do not
authorize migration, restart, strategy activation or risk expansion.

## Historical Evidence

Prior measured states and superseded task claims are preserved in
[historical roadmap](../archive/2026-10-12-main-control-roadmap-history.md).
Historical PASS belongs only to its exact candidate, command set and scope.
