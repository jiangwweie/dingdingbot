---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-08-11
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
| Scope boundary | Funding ownership and broader Incident-quality work were not changed by this release |

## Deferred Release Candidate

The Owner reported active production exposure on 2026-08-11 and explicitly
chose natural lifecycle completion instead of manual or deployment-driven
flattening. This report supersedes the prior flat postflight only for current
deployment readiness; exact current PostgreSQL and exchange state has not been
refreshed by this documentation-only action.

| Area | Deferred state |
| --- | --- |
| Candidate commit | `5e902453360f884d2ec2a7d8c6c92568d9459f4a` — `feat(owner-console): add ticket price decision map` |
| Candidate branch | Exact commit is present on `dev` and `origin/dev`; later branch movement does not change the frozen candidate identity |
| Certification | Existing exact Release Certification Manifest is `pass` for Schema `0004_owner_control_plane`; Registry, Owner Policy, runtime authority and command-set semantic digests match the current production certification |
| Production identity | Production remains `1c3063bf520a52c15b144bf613884c7e00147bfc` and `tokyo-runtime-2026.08.10.2`; the candidate has no production tag and has not changed the current release symlink, PostgreSQL identity or services |
| Deferral decision | No Controlled Flatten, no deployment, no Owner Policy change, no Entry service/fence change and no StrategyGroup control change are authorized by this record |
| Activation boundary | When the Owner opens a later deployment window, stop/disable and write-fence Entry without mutating Owner Policy, keep Lifecycle and Reconciliation active until every Ticket finishes naturally, refresh PostgreSQL/systemd/exchange facts, verify the reusable exact certification, and deploy only while internal and external exposure are flat |
| Supersession | Replacing this SHA with a later candidate requires an explicit new record and an exact passing certification for that replacement |

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
| 2 | Deployment-window freeze | Owner explicitly opens the window; Entry is stopped, disabled and write-fenced without changing Owner Policy, safety workers remain active, and current PostgreSQL, systemd, release-marker and exchange facts prove exact internal/external flatness |
| 3 | Deferred candidate release | Reuse the exact certification for `5e902453360f884d2ec2a7d8c6c92568d9459f4a`, refresh action-time gates, deploy through the current regular-release contract and complete postflight while Entry remains fenced |
| 4 | Full policy promotion | Run and certify `promote-full` only from current flat PostgreSQL and Binance facts with exact deployed identity, then restore Entry explicitly after all promotion gates pass |
| 5 | Final requirement audit | Re-run local and Tokyo evidence and close every acceptance item |
| 6 | Deployment simplification | Implement the approved M0.5 R0–R4 release model so later frontend and Owner API releases no longer wait for Kernel flatness |
| 7 | Multi-asset planning | Continue M1 Venue/Product decisions and M2 product design without changing current production authority, capital or Venue scope |

## Current Stop Conditions

Exchange writes remain fail-closed for wrong identity, invalid account mode,
stale or contradictory facts, same-domain occupancy, missing budget or Initial
Stop, duplicate or unknown command outcome, schema/code mismatch, old-writer
overlap, or official-path bypass.

The `0004` production deployment, Owner Console Strategy Workbench, Owner
control plane, controlled flatten acceptance and official Entry restoration are
complete and sealed.
`SOR-001` remains paused by explicit Owner control. The broader rebuild program
is not final until the deferred candidate window, `promote-full` and the final
requirement audit are certified from current direct evidence. Until that
window, production remains on `1c3063bf520a52c15b144bf613884c7e00147bfc`
and active exposure follows the existing certified lifecycle.
