---
title: PG_CURRENT_PROJECTION_AUTHORITY_CLOSURE_DESIGN
status: CURRENT_DESIGN
authority: docs/current/PG_CURRENT_PROJECTION_AUTHORITY_CLOSURE_DESIGN.md
last_verified: 2026-07-06
---

# PG Current Projection Authority Closure Design

## Purpose

This document defines the executable design for closing the StrategyGroup
pre-trade runtime around **PG current projections**.

The goal is not to remove every JSON or Markdown export. The goal is to remove
JSON/Markdown/report files from the runtime authority path.

The target architecture is:

```text
PG facts / events / policy / scope
-> one owner projector
-> PG current projection
-> JSON/MD export for humans, validators, and diagnostics
```

The rejected architecture is:

```text
PG rows
+ latest JSON files
+ report-dir files
+ docs JSON
+ code constants
-> scripts pick whichever source is available
```

## Owner Decisions Captured

The following decisions are treated as current design constraints:

| Decision | Rule |
| --- | --- |
| **Replace, not parallel** | Production runtime must not keep PG and file sources as long-term dual authorities. |
| **No MVP / transitional runtime authority** | Temporary comparison is allowed only when it cannot affect runtime, Owner notification, FinalGate, Operation Layer, or exchange-write decisions. |
| **Old semantics are not downgraded forever** | Old valuable semantics must be migrated into PG or rewritten. Otherwise they are deleted or archived. |
| **Multi-symbol and multi-side are strategy-defined** | A StrategyGroup can support multiple symbols and sides only when its strategy/event contract supports them. Shorts must not be auto-mirrored by the Owner or by code defaults. |
| **Operations cleanup is not core runtime** | Report cleanup, release pruning, backup pruning, and disk diagnosis are one-shot ops tools, not runtime authority components. |
| **Deploy backups are latest-only** | Deploy or ops backup state must not accumulate as a historical queue; only the most recent backup slot is retained when backup is explicitly used. |

## Problem Statement

The current runtime is no longer purely file-backed, but it has not fully closed
around PG current projections.

The current shape is:

```text
many builders read PG
-> builders export JSON/MD
-> validators validate JSON
-> publisher writes selected projections back into PG
-> some post-steps and dispatcher paths still consume report-dir JSON
```

This creates five concrete failures.

| Failure | Current shape | Impact |
| --- | --- | --- |
| **Repeated projection work** | Candidate Pool, Daily Table, Goal Status, ticket materializers, and closure materializers run in one heavy sequence | High CPU and unnecessary work when no fresh signal exists |
| **JSON feedback risk** | Generated exports can be read by later steps or validators as if they were authority | Stale export may compete with fresh PG rows |
| **Loose trade identity** | Resume dispatcher can still consume `post-signal-resume-pack.json` | "This trade" is not guaranteed to be uniquely ticket-bound at every step |
| **Legacy diagnostics bleed-through** | Pilot status, dry-run audit, closure evidence, and deploy/probe reports remain near current status | Old diagnostics can look like current blockers |
| **Report accumulation** | Every tick can write many report files and some diagnostic histories | Disk growth and unclear operational surface |

## Definitions

### PG Current Projection

A **PG current projection** is the current machine conclusion over typed PG
facts, events, policy, scope, and safety rows.

It answers questions such as:

```text
Which StrategyGroup + symbol + side is ready?
What is the first blocker?
Is there a fresh signal?
Is there a promotion candidate?
Is there an action-time lane?
Is there an Action-Time Ticket?
Is Runtime Safety State submit_allowed?
Does Owner intervention exist?
```

It is not a generic JSONB dump of a previous artifact.

### Owner Projector

An **owner projector** is the only allowed writer for one current projection
scope.

The ownership rule is:

```text
one model_type + one projection_scope_key -> one owner_projector
```

This is represented by `brc_current_projection_ownership`.

### Export

An **export** is a generated JSON/MD view derived from PG current state. It can
be used for human review, UI display, deployment acceptance, and diagnostics.
It must not be used as a runtime source.

## Target Authority Chain

The production pre-trade chain must resolve through PG:

```text
Strategy/event/scope/policy seed
-> watcher coverage
-> fact snapshots
-> live signal events
-> promotion candidates
-> action-time lane inputs
-> Action-Time Tickets
-> ticket-bound FinalGate preflight
-> ticket-bound Operation Layer handoff
-> ticket-bound protected submit attempt
-> ticket-bound post-submit closure
-> review / settlement
```

The runtime must fail closed when required PG current state is missing. It must
not fall back to old JSON, Markdown, local cache, report-dir artifacts, or code
constants.

## L2-L7 Closure Map

| Layer | Runtime question | PG authority | JSON/MD role |
| --- | --- | --- | --- |
| **L2 Strategy/event semantics** | What can this strategy trade and which sides are valid? | `brc_strategy_groups`, `brc_strategy_group_versions`, `brc_required_fact_contracts`, event spec tables | Registry exports and docs explain semantics only |
| **L3 Owner policy/scope** | What is enabled, paused, scoped, or allowed? | `brc_owner_policy_events`, `brc_owner_policy_current`, `brc_strategy_group_candidate_scope`, `brc_runtime_scope_bindings` | Policy exports for audit only |
| **L4 Facts and signals** | Did a valid fresh signal occur? | `brc_runtime_fact_snapshots`, `brc_live_signal_events` | Fact/detector exports for diagnostics only |
| **L5 Readiness/promotion** | Can this StrategyGroup + symbol + side move forward? | `brc_pretrade_readiness_rows`, `brc_promotion_candidates` | Candidate Pool export only |
| **L6 Action-time identity** | Which single lane is being prepared? | `brc_action_time_lane_inputs`, `brc_action_time_tickets` | Ticket materialization export only |
| **L7 Safety/execution boundary** | Can the ticket pass safety and official execution path? | Runtime Safety State, ticket-bound FinalGate preflight, Operation Layer handoff, protected submit attempt, post-submit closure tables | Preflight/handoff exports for audit only |

## Current Projection Ownership

| Current projection | Owner projector | Current PG table | Forbidden writers |
| --- | --- | --- | --- |
| **Candidate readiness** | `pg_candidate_readiness_projector` | `brc_pretrade_readiness_rows` | detector builders, Daily Table, Goal Status, JSON importers |
| **Promotion candidates** | `pg_promotion_candidate_projector` | `brc_promotion_candidates` | Candidate Pool export importer, resume pack importer |
| **Action-time lane inputs** | `pg_action_time_lane_projector` | `brc_action_time_lane_inputs` | resume dispatcher JSON bridge, Daily Table |
| **Action-Time Tickets** | `pg_action_time_ticket_projector` | `brc_action_time_tickets`, `brc_action_time_ticket_events` | loose StrategyGroup/symbol/side handoff files |
| **Goal Status current** | `pg_goal_status_projector` | `brc_goal_status_current` | product-state refresh legacy writer, retired 70 post-step, server monitor |
| **Runtime Safety State** | `pg_runtime_safety_projector` | runtime safety snapshot table | Candidate Pool, Goal Status, report-dir JSON |
| **Server monitor** | `pg_server_monitor_runner` | `brc_server_monitor_runs`, `brc_server_monitor_notifications` | local heartbeat, local monitor sequence, file dedupe state |
| **Read-model snapshots** | model-specific read-model exporter | `brc_control_read_model_snapshots` | hand-edited docs, historical outputs |

Every production current projection run must write:

```text
projection_run_id
model_type
owner_projector
source_mode=db_backed
projection_target=production_current
input_watermark
source_priority
legacy_diagnostics_affected_current=false
started_at_ms
finished_at_ms
status
```

## JSON/MD Export Contract

JSON and Markdown exports remain allowed only under this contract.

| Export family | Allowed? | Rule |
| --- | --- | --- |
| **Candidate Pool latest** | Yes | Derived from `brc_pretrade_readiness_rows`, `brc_promotion_candidates`, and action-time lane/ticket rows |
| **Daily Table latest** | Yes | Derived from PG current projections and read-model snapshots |
| **Single Lane Packet latest** | Yes | Task export only; cannot wrap market waits into engineering closure |
| **Goal Status latest** | Yes | Export of `brc_goal_status_current` |
| **Server monitor latest** | Yes | Export of `brc_server_monitor_runs` and current projection health |
| **Ticket / preflight exports** | Yes, short-lived | Audit/diagnostic only; ticket identity is PG |
| **Dry-run audit chain** | Manual/diagnostic only | Must not run as current authority or set main blocker |
| **Historical reports** | No as current state | Clean, archive, or migrate to diagnostics |
| **Docs JSON policy / handoff files** | No as runtime source after import | Migrate to policy/registry/scope tables or archive |

Every export must include:

```text
schema
projection_run_id
owner_projector
input_watermark
source_priority
generated_at_ms
code_version or release head
authority_boundary
```

## Product-State Refresh Redesign

`run_server_product_state_refresh_sequence.py` must not remain a single heavy
watcher post-step that runs all work on every tick.

It must become a mode-based orchestrator:

| Mode | Trigger | Required work | Must not do |
| --- | --- | --- | --- |
| `watcher_tick_summary` | Every watcher tick | Minimal watcher/current health export and fresh-signal presence check | Ticket materialization, closure evidence, Daily Table heavy rebuild |
| `control_refresh` | Low-frequency control refresh or explicit Owner Console refresh | Candidate readiness, Daily Table, Goal Status, current projection publish | FinalGate, Operation Layer, post-submit closure |
| `action_time` | Open fresh signal, promotion candidate, action-time lane, or ticket | Account/action-time facts, Action-Time Ticket, ticket-bound preflight/handoff/safety, readiness pack export | Broad diagnostic closure and old dry-run chains |
| `closure` | Protected submit, order, position, reconciliation, or settlement event | Ticket-bound post-submit closure and review refs | Candidate universe rebuild when unrelated |
| `diagnostic_full` | Manual ops/developer diagnostic only | Full export and legacy diagnostics for investigation | Runtime authority mutation |

No-signal ticks must skip:

```text
materialize_pg_promotion_action_time_lane
materialize_action_time_ticket
materialize_action_time_finalgate_preflight
materialize_action_time_operation_layer_handoff
materialize_ticket_bound_runtime_safety_state
materialize_ticket_bound_post_submit_closure
dry-run audit chain
live closure evidence refresh
```

unless PG says an open promotion, lane, ticket, submit, order, or reconciliation
state exists.

## Dispatcher Closure

The resume dispatcher must stop using `post-signal-resume-pack.json` as the
identity source for a candidate trade.

The target dispatcher input is:

```text
open brc_action_time_lane_inputs row
-> open brc_action_time_tickets row
-> ticket_id
```

The dispatcher may export:

```text
resume-dispatch-artifact.json
operation-layer-arm-evidence.json
```

but those exports must reference the PG `ticket_id`, `action_time_lane_input_id`,
`promotion_candidate_id`, and `live_signal_event_id`.

If the dispatcher cannot resolve a unique ticket-bound identity, it must fail
closed with:

```text
blocked_by_missing_pg_ticket_identity
```

It must not infer identity from:

```text
StrategyGroup + symbol + side loose fields
Candidate Pool JSON
Daily Table JSON
Goal Status JSON
resume pack JSON
dry-run audit JSON
```

## Legacy Handling Rules

Legacy artifacts have only three valid outcomes.

| Legacy artifact type | Required outcome |
| --- | --- |
| Valuable strategy semantics | Import/rewrite into strategy registry, RequiredFacts, event spec, or governance tables |
| Valuable runtime diagnostic | Store as `brc_legacy_diagnostics` or archive with evidence refs |
| No current value | Delete or archive outside current authority |

Legacy artifacts must not be kept as "lower-priority current sources". A
lower-priority current source is still a second source of truth.

## Implementation Batches

### Batch P0-A: Projection Ownership Enforcement

Goal:

```text
Every production current projection has one registered owner and lineage.
```

Work:

- Seed/verify `brc_current_projection_ownership` rows.
- Add validator that rejects multiple owner writers for one
  `model_type + projection_scope_key`.
- Ensure `brc_projection_runs` rows are written for production current
  projections.
- Enforce `legacy_diagnostics_affected_current=false` for successful
  `production_current` runs.

Acceptance:

- `brc_goal_status_current` has one owner projector.
- `brc_pretrade_readiness_rows` has one owner projector.
- Production current projection runs are `source_mode=db_backed`.
- Legacy diagnostics cannot populate main current blockers when current
  coverage is complete.

### Batch P0-B: PG Ticket Identity Closure

Goal:

```text
"This trade" is answered only by PG Action-Time Ticket identity.
```

Work:

- Dispatcher reads PG lane/ticket rows instead of `post-signal-resume-pack.json`
  as authority.
- FinalGate preflight, Operation Layer handoff, Runtime Safety State, protected
  submit attempt, and post-submit closure all require `ticket_id`.
- Exports include refs, but refs are not authority.

Acceptance:

- A fresh signal can produce one unique `action_time_ticket_id`.
- Dispatcher fails closed if multiple or zero open ticket identities exist.
- No production submit-adjacent path consumes Candidate Pool JSON, Daily Table
  JSON, Goal Status JSON, or resume pack JSON as trade identity.

### Batch P0-C: Product-State Refresh Mode Split

Goal:

```text
Watcher tick no longer triggers all heavy control, action-time, closure, and
diagnostic work.
```

Work:

- Add mode argument to `run_server_product_state_refresh_sequence.py`.
- Make watcher post-step call `watcher_tick_summary`.
- Trigger `action_time` mode only when PG has open fresh/promotion/lane/ticket
  state.
- Trigger `closure` mode only from submit/order/position/reconciliation events
  or explicit operator diagnostic.
- Move `diagnostic_full` out of normal watcher cadence.

Acceptance:

- No-signal tick does not run ticket/preflight/handoff/safety/closure steps.
- Candidate Pool is not rebuilt three times in one no-signal sequence.
- Goal Status remains fresh enough for Owner Console and server monitor.
- CPU does not spike from no-op materialization work.

### Batch P0-D: JSON Feedback Loop Removal

Goal:

```text
JSON exports are not runtime inputs.
```

Work:

- Replace file validators with PG current projection validators where they are
  used for production acceptance.
- Keep export validators only to verify export fidelity against PG projection
  rows.
- Remove any production CLI options that reintroduce `--candidate-pool-json`,
  `--daily-table-json`, `--goal-status-json`, or `--live-facts-json` as current
  authority inputs.

Acceptance:

- Candidate Pool, Daily Table, Single Lane Packet, Goal Status, and server
  monitor production paths read PG current state only.
- Export validator failures block export publication, not runtime state
  computation.
- Previous-cycle `latest-*.json` cannot influence the next current projection.

### Batch P1-A: Policy/Scope/Registry Import Closure

Goal:

```text
Runtime-facing strategy semantics, Owner policy, candidate universe, and runtime
scope live in PG.
```

Work:

- Import/rewrite strategy registry, strategy versions, RequiredFacts contracts,
  event specs, Owner policy, candidate scope, side scope, and runtime bindings.
- Remove runtime dependence on docs JSON and code constants for active universe
  and side permissions.
- Enforce strategy-defined side support. Do not auto-mirror long/short.

Acceptance:

- Candidate universe comes from PG candidate scope/runtime bindings.
- Strategy side support comes from strategy/event contracts and Owner policy,
  not from default mirrored code.
- Docs JSON is seed/provenance only.

### Batch P1-B: Legacy Deletion Or Migration

Goal:

```text
Old current-seeming artifacts no longer sit beside the runtime authority path.
```

Work:

- Enumerate legacy artifacts.
- For each item, choose exactly one: migrate, rewrite, archive, delete.
- Remove retired bridges and their tests when replacement is complete.

Acceptance:

- No old artifact is documented as a lower-priority runtime current source.
- `brc_legacy_diagnostics` may explain old observations but cannot set current
  blockers.
- Report cleanup remains an ops tool, not runtime authority.

## Required Validators

| Validator | Purpose |
| --- | --- |
| `validate_current_projection_ownership.py` | Ensures one owner projector per current projection scope |
| `validate_pg_current_projection_lineage.py` | Ensures projection runs have DB-backed source mode, watermarks, code version, and no legacy current effect |
| `validate_candidate_readiness_current_projection.py` | Ensures readiness rows are complete for active StrategyGroup + symbol + side scope |
| `validate_action_time_ticket_identity.py` | Ensures open action-time state has at most one unique ticket identity for submit-adjacent work |
| `validate_export_matches_pg_projection.py` | Ensures JSON exports match PG current projection rows |
| `validate_no_runtime_file_authority.py` | Ensures production CLIs do not add direct runtime reads from docs/output/report JSON |

## Systemd Target Shape

The current watcher post-step shape must be reduced.

Target:

```text
brc-runtime-signal-watcher.service
  ExecStart: watcher tick writes PG coverage/facts/signals and latest minimal export
  ExecStartPost: product-state refresh --mode watcher_tick_summary
  ExecStartPost: action-time mode only if PG open lane/ticket exists
  ExecStartPost: dispatcher only with PG ticket identity
```

Not target:

```text
watcher tick
-> full product-state refresh sequence
-> dry-run audit chain
-> closure evidence
-> ticket/preflight/safety materializers
-> dispatcher using resume pack JSON
```

`dry-run-audit-chain` and `diagnostic_full` are manual or deploy-acceptance
diagnostics. They are not normal production tick work.

## Test Strategy

### Unit Tests

- Projection ownership rejects duplicate owner writers.
- Goal Status current cannot be written by legacy product-state paths.
- Candidate readiness rows are deterministic for active scope.
- No-signal refresh mode skips action-time and closure steps.
- Action-time mode requires PG lane/ticket identity.
- Dispatcher rejects missing or ambiguous ticket identity.
- Exports include lineage and authority boundary.

### Integration Tests

- Seed 5 active StrategyGroups and multi-symbol candidate scope.
- Run watcher fact/signal import into PG.
- Run current projector.
- Verify Candidate Pool export matches `brc_pretrade_readiness_rows`.
- Verify Goal Status export matches `brc_goal_status_current`.
- Verify no previous `latest-*.json` can affect a new projection.
- Verify no-signal path remains quiet and does not create tickets.
- Verify fresh-signal path creates one promotion, one lane, one ticket, and
  ticket-bound preflight/safety rows.

### Deployment Acceptance

Before deploy:

```text
validate_current_projection_ownership.py
validate_pg_current_projection_lineage.py
validate_no_runtime_file_authority.py
focused unit tests for refresh modes and dispatcher ticket identity
```

After deploy:

```text
PG DSN reachable
projection ownership rows present
server monitor reads PG current projections
watcher tick no-signal path does not run heavy materializers
fresh-signal simulation/dry-run creates ticket-bound chain without exchange write
```

## Rollback And Failure Behavior

Rollback may revert code to the previous release, but production runtime must
not use old JSON/report files as a fallback authority path.

Failure behavior:

| Failure | Required behavior |
| --- | --- |
| PG unavailable | `temporarily_unavailable`, fail closed, no JSON fallback |
| Missing projection ownership | Block projection publication |
| Missing ticket identity | Block dispatcher/action-time submit-adjacent work |
| Export mismatch | Block export or report publication, not PG current truth |
| Legacy diagnostic mismatch | Store diagnostic only; do not set main blocker |
| Ambiguous action-time lane | Fail closed before FinalGate/Operation Layer |

## Non-Goals

This design does not:

- authorize live-submit;
- bypass FinalGate;
- bypass Operation Layer;
- call exchange-write APIs;
- mutate credentials, live profile, or order sizing defaults;
- optimize strategy parameters;
- build a long-lived ops retention subsystem in the trading core;
- keep old JSON/MD as a lower-priority production authority source.

## Done When

The closure is complete when:

```text
PG current projection is the only production runtime progression surface.
JSON/MD files are exports or diagnostics only.
The dispatcher and submit-adjacent chain are PG ticket-bound.
No-signal watcher ticks do not run heavy action-time/closure materializers.
Old source artifacts are migrated, rewritten, archived, or deleted.
Validators prove ownership, lineage, source ban, and export fidelity.
```

The Owner-facing result should be simple:

```text
Which StrategyGroup + symbol + side can move?
Why did it not move?
If it did move, what is the ticket_id?
What safety state stopped or allowed the next official step?
Does the Owner need to intervene?
```

## Implementation Task Prompt

Use this prompt for a dedicated implementation window:

```text
Task ID: P0-PG-CURRENT-PROJECTION-AUTHORITY-CLOSURE

Goal:
Close the L2-L7 pre-trade runtime around PG current projections. Runtime
progression must read PG current state and ticket-bound identity, not JSON/MD
exports or report-dir artifacts.

Allowed files:
- src/infrastructure/runtime_control_state_repository.py
- scripts/publish_runtime_control_current_projections.py
- scripts/run_server_product_state_refresh_sequence.py
- scripts/runtime_signal_watcher_resume_dispatcher.py
- scripts/materialize_pg_promotion_action_time_lane.py
- scripts/materialize_action_time_ticket.py
- scripts/materialize_action_time_finalgate_preflight.py
- scripts/materialize_action_time_operation_layer_handoff.py
- scripts/materialize_ticket_bound_runtime_safety_state.py
- scripts/materialize_ticket_bound_post_submit_closure.py
- scripts/validate_*projection*.py
- scripts/validate_*ticket*.py
- deploy/systemd/brc-runtime-signal-watcher.service.d/*.conf
- tests/unit/test_*projection*.py
- tests/unit/test_*server_product_state_refresh*.py
- tests/unit/test_*resume_dispatcher*.py
- docs/current/PG_CURRENT_PROJECTION_AUTHORITY_CLOSURE_DESIGN.md

Forbidden files:
- exchange gateway write paths unless explicitly reviewed
- FinalGate bypass paths
- Operation Layer submit implementation except ticket-bound handoff validation
- live profile or sizing defaults
- credentials, env secrets, and runtime-order-capable env files

Requirements:
1. Enforce one owner projector per production current projection.
2. Ensure Candidate Pool, Goal Status, Daily Table, Single Lane Packet, and
   server monitor production paths read PG current state only.
3. Make dispatcher use PG action-time lane / Action-Time Ticket identity, not
   resume pack JSON authority.
4. Split product-state refresh into watcher_tick_summary, control_refresh,
   action_time, closure, and diagnostic_full modes.
5. Ensure no-signal watcher ticks skip ticket/preflight/handoff/safety/closure
   materializers.
6. Keep JSON/MD exports as export-only with lineage and authority boundary.
7. Add validators for ownership, lineage, export fidelity, no runtime file
   authority, and ticket identity.

Acceptance:
- No production runtime path falls back to docs/output/report JSON when PG
  current state is unavailable.
- A fresh-signal path creates one PG promotion candidate, one PG action-time
  lane, and one PG Action-Time Ticket before any submit-adjacent work.
- No-signal path remains quiet and does not run heavy action-time or closure
  materializers.
- Goal Status current is one-owner PG projection and legacy diagnostics cannot
  set main blockers.
- JSON exports match PG current projection and are never consumed as runtime
  authority.

Hard stop:
- Stop if the change would bypass FinalGate, Operation Layer, protected submit,
  or Runtime Safety State.
- Stop if a missing PG row is handled by falling back to JSON/MD/report files.
```
