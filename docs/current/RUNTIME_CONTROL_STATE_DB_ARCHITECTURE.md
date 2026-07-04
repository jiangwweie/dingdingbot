---
title: RUNTIME_CONTROL_STATE_DB_ARCHITECTURE
status: CURRENT_DESIGN
authority: docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md
last_verified: 2026-07-03
---

# Runtime Control State DB Architecture

## Purpose

This document defines the target DB-backed information architecture for the
StrategyGroup pre-trade runtime.

The goal is not to delete every JSON or Markdown file. The goal is to stop
using files as conflicting runtime sources of truth.

The target split is:

```text
Docs explain contracts.
DB stores current policy, registry, runtime, and control state.
Generated JSON/MD exports summarize DB-backed read models.
Archives preserve provenance.
```

This design supports the current V0 runtime target:

```text
five active StrategyGroups
-> multiple candidate symbols per StrategyGroup
-> per-symbol readiness and first blocker
-> fresh-signal promotion
-> at most one action-time lane input
-> official FinalGate and Operation Layer only after action-time gates pass
```

The detailed mainline MD/JSON read/write inventory is maintained in:

```text
docs/current/RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP.md
```

## Decision

Dynamic live-enablement state should move behind a DB-backed
`RuntimeControlStateRepository`.

The repository is the only allowed read boundary for these dynamic domains:

- StrategyGroup registry state that is consumed by runtime builders;
- Owner policy and scoped authorization;
- candidate universe and symbol/side scope;
- watcher/runtime coverage;
- RequiredFacts computation snapshots;
- pre-trade readiness rows;
- promotion candidates;
- action-time lane inputs;
- runtime safety state;
- server monitor quiet/notify state;
- generated control read-model snapshots.

After PG cutover, runtime scripts must read PG current state through typed
repository methods. Repo MD/JSON/output files may be used only as curated seed
inputs, exports, archives, fixtures, or diagnostics. They must not remain a
production runtime fallback.

Short-lived comparison during local migration validation is allowed only when it
cannot affect runtime, trading, Owner notification, FinalGate, or Operation
Layer decisions.

## Owner-Confirmed Cutover Directive

The Owner-confirmed target is:

```text
replace, not parallel
```

This means the PG migration must close the L2-L7 runtime authority path as one
coherent design:

```text
PG strategy/event/scope/policy seed
-> PG watcher coverage
-> PG fact snapshots
-> PG live signal events
-> PG promotion candidates
-> PG action-time lane inputs
-> PG Action-Time Tickets
-> FinalGate ticket input
-> Operation Layer ticket handoff
```

Production runtime must not keep a long-term shape where PG and file sources are
both active authorities. If PG current state is unavailable, real-submit
progression must fail closed rather than falling back to old JSON, Markdown,
output artifacts, local cache, or code constants.

## Known Current Facts

These are current repo facts as of 2026-07-03.

| Fact | Current evidence |
| --- | --- |
| Current information contract already says dynamic state should move to runtime or policy stores | `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md` |
| `docs/current` contains many mixed-purpose JSON/MD files | 66 JSON/MD files under `docs/current` |
| `output` contains many generated or volatile JSON/MD files | 68 JSON/MD files under `output` |
| Candidate Pool reads many raw files directly | `scripts/build_strategy_live_candidate_pool.py` reads Daily Table, Tradeability, Replay/Live Parity, Action-Time Boundary, runtime active monitor, detector facts, and Owner authorization JSON |
| Daily Table reads generated output files directly | `scripts/build_daily_live_enablement_table.py` reads Tradeability, Replay/Live Parity, Action-Time Boundary, MI admission, runtime safety, and optional Candidate Pool JSON |
| Server monitor still reads generated JSON snapshots as primary inputs | `scripts/run_tokyo_runtime_server_monitor.py` reads Daily Table, Candidate Pool, public facts, account-safe facts, watcher status, and deploy health JSON |
| Strategy semantics already have PG-style tables | `src/infrastructure/pg_models.py` includes `brc_strategy_families`, `brc_strategy_family_versions`, `brc_strategy_family_registry`, and `brc_strategy_family_playbooks` |
| Runtime lifecycle already has PG-style tables | `strategy_runtime_instances`, `strategy_runtime_events`, `signal_evaluations`, `order_candidates`, and many `runtime_execution_*` tables exist |
| Owner/policy records already partially exist | `brc_owner_risk_acknowledgements`, `brc_owner_risk_acceptances`, bounded trial authorization tables, and budget authorization tables exist |
| Runtime profile is already modeled | `runtime_profiles` exists |
| Candidate universe is still partly hard-coded | `DEFAULT_CANDIDATE_UNIVERSE` appears in runtime builders and monitor scripts |
| Owner pre-trade authorization is currently a docs JSON input | `docs/current/strategy-group-handoffs/owner-pretrade-runtime-authorization-v0.json` |

## Problem

The current system has five information roles mixed across JSON, Markdown,
output files, and code constants.

| Role | Current problem | Runtime impact |
| --- | --- | --- |
| Strategy semantics | Registry baseline, handoff packs, and code constants can disagree | A strategy may be treated differently by intake, Tradeability, and Candidate Pool |
| Owner policy | Authorization JSON, tier policy JSON, runtime profile, and deployed runtime scope can drift | `live_submit_allowed` can mean different things in different links |
| Runtime facts | Watcher status, public facts, active monitor, and runtime safety are separate files | A fresh signal may not promote because the chain reads a stale source |
| Read models | Daily Table and Candidate Pool are generated, but other scripts then treat them as inputs | Generated views become second-order sources of truth |
| Output governance | Some output files are valid snapshots and others are volatile runtime noise | Git and runtime can accidentally preserve stale facts |

The main architectural failure mode is:

```text
source A says scoped
source B says not attached
source C says market wait
builder D picks one based on file availability
```

That is not a strategy problem. It is a source-of-truth problem.

## Current Mainline File I/O Map

The current live-enablement chain still has several JSON/MD files acting as
runtime sources. The target is not to copy these files into PG. The target is
to replace them with typed events, facts, and current projections, then export
JSON/MD only for compatibility.

| Mainline node | Current reads | Current writes | Current risk | PG target |
| --- | --- | --- | --- | --- |
| Watcher tick / active monitor | systemd runtime, exchange/public inputs, Candidate Pool export as candidate universe, runtime scope files | server report JSON such as `latest-status.json`, local `latest-runtime-active-observation-status.json` | Watcher coverage becomes a file-presence interpretation and a generated view can drive the observer universe | `brc_strategy_group_candidate_scope`, `brc_watcher_runtime_coverage`, plus fact/event rows |
| Public/account fact collectors | exchange APIs, fallback JSON, live-facts report JSON | `latest-binance-usdm-public-facts.json`, `latest-account-safe-facts.json` | Freshness and fallback source can drift across builders | `brc_runtime_fact_snapshots` with observed/valid-until timestamps |
| Strategy detector builders | public facts JSON, strategy constants, local artifacts | detector fact JSON/MD such as SOR/MI/BRF2/MPG outputs | Detector output becomes a downstream file authority | `brc_live_signal_events` and fact snapshots |
| Tradeability Decision | registry baseline JSON, tier policy JSON, runtime safety, replay/live parity, action-time boundary, admission/scope outputs | `latest-strategygroup-tradeability-decision.json/md` | Broad generated read model can become an upstream source for later builders | DB-backed Tradeability read model over current projections |
| Replay/Live Parity Audit | replay JSON, CPM/MPG/SOR detector or watcher outputs | `latest-replay-live-parity-audit.json/md` | Historical parity diagnostics can be confused with current live coverage | diagnostic/read-model rows separate from watcher coverage |
| Candidate Pool | Daily Table, Tradeability, replay/live parity, action-time boundary, detector facts, runtime active monitor, Owner auth JSON | `latest-strategy-live-candidate-pool.json/md` | Generated view recomputes source priority and may become authority | `brc_pretrade_readiness_rows`, `brc_promotion_candidates`, `brc_action_time_lane_inputs` |
| Daily Table | Candidate Pool plus generated fact/readiness outputs | `latest-daily-live-enablement-table.json/md` | Management table can inherit stale generated inputs | DB-backed read-model export from current projections |
| Single Lane Packet | Daily Table JSON | `latest-single-lane-task-packet.json/md` | Market waits can be accidentally wrapped as closure tasks | Task export only, not runtime authority |
| Goal Status | report-dir artifacts, optional Candidate Pool JSON, release manifest, legacy pilot status | `strategygroup-runtime-goal-status.json` | Multiple writers and optional Candidate Pool can let legacy scope mismatch overrule new control state | `brc_goal_status_current` single-owner projection |
| Server monitor | Daily Table, Candidate Pool, public/account facts, watcher/systemd/deploy health JSON, dedupe JSON | server monitor JSON and Feishu dedupe state | Production monitor can become a file aggregator instead of the runtime fact owner | `brc_server_monitor_runs`, `brc_server_monitor_notifications`, current projections |

## Current Conflict Cases

These cases define why the migration must introduce current projection
ownership, not just a DB table for every existing artifact.

| Conflict | Concrete shape | Why it matters | Target rule |
| --- | --- | --- | --- |
| Multiple writers for one current file | `strategygroup-runtime-goal-status.json` can be written by more than one post-step path | Last writer wins even if it used older inputs | One current projection has exactly one owner projector |
| Optional control source | Goal Status can run with or without `--candidate-pool-json` | Same command can produce different authority conclusions | Candidate Pool/current projection is required once it becomes the control-plane source |
| Legacy diagnostic promoted to blocker | `pilot_status.watcher_scope_alignment` can still emit scope mismatch after Candidate Pool proves coverage | Old status can hide real waiting/fresh-signal state | Legacy artifacts may write diagnostics only |
| Watcher universe from generated view | watcher tick reads Candidate Pool export as `--candidate-universe-json` | A previous-cycle read model can define the current observation universe | Watcher reads DB candidate scope/runtime bindings |
| Generated view consumed as source | Candidate Pool, Daily Table, Packet, Goal Status read each other's JSON outputs | Read models become second-order truth | Builders read repository/current projections; JSON is export |
| No shared lineage | Candidate Pool and Goal Status do not share a required `projection_run_id` and input watermark | It is hard to prove they describe the same watcher tick | Every projection records run ID, input watermark, source priority, and owner projector |
| Hard-coded scope | Candidate universes and primary symbols appear in code constants and docs JSON | Owner scope and runtime scope can diverge silently | Candidate scope and runtime bindings are DB current projections |

### Goal Status Case Study

The recent Candidate Pool / Goal Status mismatch is the canonical example.

The intended control order is:

```text
watcher/facts
-> Candidate Pool current projection
-> Daily Table export
-> Single Lane Packet export
-> Goal Status current projection
```

The unsafe transitional shape is:

```text
legacy pilot/status artifacts
plus optional Candidate Pool JSON
plus multiple systemd post-step writers
-> strategygroup-runtime-goal-status.json
```

This can report `runtime_scope_mismatch` or
`selected_strategygroup_scope_mismatch` even after Candidate Pool has proven
server-backed 5x18 coverage. The fix is not to add another packet. The fix is
to make Goal Status Current a single-owner projection that depends on the
Candidate Pool/current readiness projection when that projection is available.
Legacy scope alignment can remain as `legacy_diagnostics`, but it must not set
the main current blocker.

## Alternatives Considered

| Option | Description | Pros | Cons | Decision |
| --- | --- | --- | --- | --- |
| File-only cleanup | Keep JSON/MD as machine sources, tighten validators and gitignore rules | Smallest implementation change | Does not remove semantic drift across policy, runtime, output, and code constants | Reject as long-term architecture |
| Big-bang DB migration | Move all dynamic JSON, output snapshots, strategy registry, policy, facts, and monitor state directly into DB | Clean target state quickly if it works | High blast radius; easy to break live-enablement builders and deployment at once | Reject for first implementation |
| Repository-first phased migration | Add `RuntimeControlStateRepository`, start file-backed, then migrate policy/candidate scope/runtime coverage to DB | Useful as a historical way to compress file reads | Keeps a compatibility layer that can become a second source of truth | Reject as the Owner-confirmed target; may be used only for local non-production comparison if it cannot influence runtime decisions |
| Generic JSONB document store | Store current JSON payloads in one or two generic tables | Fast to import existing artifacts | Preserves ambiguous schemas and makes DB another artifact bucket | Reject except for read-model snapshot history |
| Replace-and-cutover PG migration | Build schema, seed, validators, runtime readers, ticket path, monitor path, and old-source removal together | Matches Owner target; removes dual authority; forces negative tests | Larger implementation batch and requires stronger acceptance testing | Recommended |

The recommended path is replace-and-cutover PG migration. Repository methods
remain useful as typed boundaries, but they must resolve to PG current state in
production after cutover.

## Design Principles

### One Dynamic Source Boundary

Runtime builders must consume dynamic state through one repository boundary:

```text
RuntimeControlStateRepository
```

They must not independently decide whether to read:

- `docs/current/**/*.json`;
- `output/runtime-monitor/latest-*.json`;
- server report JSON;
- code constants;
- local cache files.

### One Current Projection Owner

Every `current_*` state must have exactly one owner projector.

Allowed writers:

- fact collectors write fact snapshots or events;
- detector builders write signal/fact events;
- diagnostic tools write diagnostics;
- one named projector writes each current projection.

Forbidden writers:

- a product-state refresh script must not write the same current state as a
  final post-step builder;
- legacy status artifacts must not overwrite current readiness, scope,
  promotion, action-time, or goal-status projections;
- generated export writers must not make independent blocker decisions.

The required flow is:

```text
facts/events/diagnostics
-> owner projector
-> current projection
-> JSON/MD export
```

The forbidden flow is:

```text
facts/events
-> many scripts
-> many current-like JSON files
-> later script chooses one
```

### Projection Lineage Is Required

Every current projection must record:

- `projection_run_id`;
- `owner_projector`;
- `input_watermark`;
- `source_priority`;
- code version or release head;
- source fact/event IDs where available;
- whether legacy diagnostics were read;
- whether legacy diagnostics affected the current blocker.

For production current projections, legacy diagnostics must not affect the main
blocker when a fresher DB-backed projection exists.

### DB Stores Facts, Not Reports

DB tables should store normalized facts, policy, state, and lineage.

Generated JSON/MD files remain useful, but only as exports:

```text
DB facts -> read model builder -> output JSON/MD
```

This must not become:

```text
output JSON -> runtime source -> another output JSON
```

### Append Events, Project Current State

Owner policy, runtime state changes, monitor runs, and promotion decisions
should be append-only where possible, with explicit current projections.

The write model should preserve provenance. The read model should answer the
current question quickly.

### Strategy Semantics Are Versioned

A StrategyGroup's model semantics are mostly stable, but not timeless.

The DB should represent:

- stable identity;
- versioned thesis and trade logic;
- RequiredFacts contract;
- supported symbol/side/timeframe scope;
- risk envelope;
- promotion, downshift, park, and kill rules.

It should not store large replay corpora or long research documents as primary
runtime facts.

### Owner Policy Is Not Runtime Submit Authority

Owner policy may authorize scope, tier, capital profile, candidate universe,
and trial eligibility.

It must not grant:

- FinalGate bypass;
- Operation Layer bypass;
- exchange write;
- stale-fact execution;
- missing-protection execution;
- duplicate submit;
- live profile mutation;
- order-sizing mutation.

### Generated Views Stay Commit-Bounded

`output/**` remains governed by `config/output_control_snapshots.json`.

DB-backed exports may still write these files for agent compatibility, but the
files are read-model snapshots, not the authority source.

## Target Source Model

| Information class | Target source | Current transitional source | Export/read model |
| --- | --- | --- | --- |
| Governance contract | `docs/current/*.md` | same | none |
| StrategyGroup identity and semantics | DB strategy registry tables | registry baseline JSON and handoff packs | registry export JSON/MD |
| RequiredFacts contract | DB versioned fact contract tables | handoff packs and mapping docs | fact contract export |
| Owner scope and policy | DB owner policy event tables and current projection | Owner explicit decisions plus policy JSON | policy export JSON |
| Candidate universe | DB scoped symbol/side rows | code constants and authorization JSON | Candidate Pool read model |
| Runtime profile and scope binding | DB runtime profile and scope binding tables | `runtime_profiles` plus JSON policy | Runtime Safety State and Candidate Pool |
| Watcher/server coverage | DB coverage snapshots | active monitor JSON and server reports | server monitor export |
| Public/account facts | DB fact snapshots or snapshot refs | output facts JSON | runtime fact export |
| Per-symbol readiness | DB read-model table or materialized projection | Candidate Pool JSON | Candidate Pool JSON/MD |
| Fresh signal and promotion | DB signal/promotion tables | generated detector files | Candidate Pool and action-time lane export |
| Action-time lane input | DB lane input table | generated action-time boundary JSON | action-time export |
| Runtime safety state | DB safety snapshot table | runtime safety JSON | Runtime Safety State JSON/MD |
| Goal Status current | DB goal-status current projection | report-dir goal-status JSON | goal-status JSON export |
| Daily table | DB-backed generated read model | Daily Table JSON | Daily Table JSON/MD |
| Server monitor notification | DB monitor run and notification tables | dedupe JSON and server monitor JSON | server monitor JSON |
| Deploy evidence | deploy reports and archive path | same | not a runtime source |
| Replay corpus and fixtures | repo fixture files | same | replay read model only |

## RuntimeControlStateRepository

### Required Interface

The repository should expose typed methods rather than raw JSON paths:

```text
get_active_strategy_groups()
get_strategy_group_registry(strategy_group_id)
get_strategy_group_version(strategy_group_id)
get_required_fact_contract(strategy_group_id, version_id)
get_owner_policy_current(strategy_group_id)
get_candidate_universe(strategy_group_id)
get_runtime_scope_binding(strategy_group_id, symbol, side)
get_runtime_profile(profile_id)
get_watcher_coverage(strategy_group_id, symbol, side)
get_latest_public_fact_snapshot(strategy_group_id, symbol, side)
get_latest_account_safe_fact_snapshot(profile_id)
get_tradeability_decision(strategy_group_id)
get_pretrade_readiness_rows(strategy_group_id=None)
get_promotion_candidates(status=None)
get_action_time_lane_inputs(status=None)
get_runtime_safety_state(strategy_group_id, symbol=None)
get_goal_status_current()
get_server_monitor_state()
start_projection_run(model_type, owner_projector, input_watermark)
write_control_read_model_snapshot(model_type, payload, source_watermark)
write_goal_status_current(payload, projection_run_id)
```

### Source Modes

| Mode | Allowed use | Production runtime authority |
| --- | --- | ---: |
| `file_backed` | Local inventory, seed extraction, or historical compatibility tests only | No |
| `hybrid` | Local migration comparison only; must not affect runtime, monitor, FinalGate, or Operation Layer | No |
| `db_backed` | Production source after cutover | Yes |

The important target is not merely that builders call one repository class. The
important target is that production repository methods resolve to PG current
state and fail closed when required PG state is unavailable.

## Target Flow

```mermaid
flowchart TD
  Docs["docs/current contracts"] --> Repo["RuntimeControlStateRepository"]
  RegistrySeed["handoff packs and registry seed"] --> Importer["seed/import tools"]
  OwnerPolicy["Owner policy events"] --> DB["Runtime Control State DB"]
  Watcher["server watcher and detectors"] --> DB
  RuntimeFacts["public/account/runtime facts"] --> DB
  Importer --> DB
  DB --> Repo
  DB --> ProjectionRuns["Projection run and lineage records"]
  Repo --> Tradeability["Tradeability Decision builder"]
  Repo --> CandidatePool["Candidate Pool builder"]
  Repo --> DailyTable["Daily Table builder"]
  Repo --> GoalStatus["Goal Status projector"]
  Repo --> ServerMonitor["Tokyo server monitor"]
  Tradeability --> Export["output JSON/MD exports"]
  CandidatePool --> Export
  DailyTable --> Export
  GoalStatus --> Export
  ServerMonitor --> Notify["Feishu quiet/notify"]
```

## Domain Boundaries

### Strategy Registry Boundary

The registry defines strategy assets. It does not decide current actionability.

The DB should hold:

- StrategyGroup identity;
- current version;
- edge thesis;
- supported symbols/sides/timeframes;
- RequiredFacts contract;
- risk envelope;
- promotion/downshift/park/kill rules;
- lifecycle stage.

Tradeability and runtime safety remain read models over registry, policy, and
runtime facts.

### Owner Policy Boundary

Owner policy records scoped authorization and governance state.

It should hold:

- enabled/paused/parked/killed state;
- tier and stage decisions;
- symbol/side scope;
- runtime profile selection;
- notional/leverage/loss-unit/attempt-cap scope;
- pre-trade candidate authorization;
- action-time rehearsal allowance;
- live-submit scope state.

It must not call execution gates or create order authority.

### Runtime Fact Boundary

Runtime facts are current operational facts observed by the system.

They include:

- watcher liveness;
- server-backed runtime coverage;
- detector outputs;
- public market facts;
- account-safe facts;
- active position and open-order facts;
- protection readiness;
- FinalGate and Operation Layer readiness references.

Facts need source, observed timestamp, freshness window, and expiry.

### Read Model Boundary

Tradeability Decision, Candidate Pool, Daily Table, Runtime Safety State, and
Owner Console state are read models.

They may be stored in DB for audit and exported to JSON/MD for agent
compatibility. They must not become hand-edited authority.

## File Treatment

| File class | DB migration treatment |
| --- | --- |
| `docs/current/*.md` contracts | Stay in repo as human/agent authority |
| Strategy handoff JSON | Become seed/import inputs and provenance refs |
| Owner policy JSON | Migrate into owner policy events and current projection |
| Runtime tier policy JSON | Migrate into policy/tier tables or seed config |
| Candidate universe constants | Migrate into scoped candidate universe rows |
| Output control snapshots | Stay generated exports; DB is source |
| Volatile output facts | Move to DB snapshots or stay untracked diagnostic exports |
| Replay fixtures | Stay as repo fixtures, not DB current state |
| Deploy/session reports | Stay deploy evidence, not runtime source |
| Systemd/deploy config | Stay files; not DB runtime control state |

## Cutover Plan

### Step 0: Source Audit And Guardrails

Produce a file-source audit for the current live-enablement chain:

```text
path
source class
writer
reader
authority role
DB target
migration priority
```

Add tests or validators that fail if new runtime builders read critical JSON
paths directly instead of using the repository.

### Step 1: PG Schema, Seed, And Negative Constraints

Create the PG schema, curated initial seed, and negative constraints for:

- active StrategyGroups;
- event specs and RequiredFacts;
- Owner policy and candidate scope;
- runtime profile, sizing, execution, protection, and budget scope;
- watcher coverage, fact snapshots, live signal events, promotion candidates,
  action-time lanes, and Action-Time Tickets.

The initial seed must contain only confirmed clean semantics. Old live signals,
old action-time lanes, old packets, replay opportunities, and generated
timestamps must not be imported as current state.

### Step 2: Runtime Readers And Writers Switch To PG

Switch these runtime surfaces to PG current state:

- watcher scope;
- candidate universe;
- Owner policy;
- runtime coverage;
- fact snapshots;
- live signal events;
- Candidate Pool;
- Daily Table;
- Goal Status;
- server monitor;
- forensics / chain-position explanations.

### Step 3: Ticket, FinalGate, Operation Layer Handoff

Close the official pre-submit chain:

- Action-Time Ticket identity;
- ticket-bound fact, policy, sizing, execution, protection, budget, instrument,
  and account-mode lineage;
- FinalGate input as `ticket_id` only;
- Operation Layer input as `ticket_id + finalgate_pass_id` only;
- protection and reconciliation lineage back to the ticket.

### Step 4: Old-Source Removal

Remove or make non-authoritative:

- direct runtime reads of Owner policy JSON;
- direct runtime reads of generated output files;
- hard-coded candidate universe and side fallbacks;
- loose FinalGate parameter path;
- loose Operation Layer submit path;
- local cache as production monitor source.

### Step 5: Tokyo Cutover Bootstrap

After deploy, bootstrap current runtime facts from real sources:

- Tokyo watcher coverage;
- live detector events;
- exchange account facts;
- active position and open orders;
- balance;
- systemd/service health;
- server monitor run.

Old `latest-*` JSON, packets, or artifacts must not seed current live state.

### Step 6: Export And Diagnostics

JSON/MD outputs may be regenerated from PG-backed read models for diagnostics,
audit viewing, or agent compatibility.

Those exports remain non-authority.

## Priority Order

| Priority | Migration item | Reason |
| --- | --- | --- |
| P0 | PG schema, seed, and negative constraints | Creates the replacement current-state authority |
| P0 | Owner policy and candidate universe | Directly controls multi-symbol pre-trade scope |
| P0 | Runtime scope binding and coverage | Required for server-backed promotion to action-time |
| P0 | Action-Time Ticket and gate handoff | Prevents loose identity before FinalGate and Operation Layer |
| P1 | StrategyGroup registry overlay | Removes semantic drift between handoff, registry, and runtime |
| P1 | RequiredFacts contract tables | Makes per-symbol readiness and action-time facts deterministic |
| P1 | Candidate readiness and promotion tables | Makes fresh-signal promotion replayable and inspectable |
| P1 | Server monitor run and notification tables | Removes local-cache production dependency |
| P2 | Generic read-model snapshot table | Useful after core sources are stable |
| P2 | Historical artifact import | Provenance only; not needed for first closure |

## Acceptance Criteria

DB migration design is accepted only when all of these are true:

| Requirement | Done when |
| --- | --- |
| Source boundary | Production runtime builders consume PG current state through typed repository methods, not raw dynamic JSON paths |
| Policy source | Owner authorization and candidate universe are DB-backed with one current projection |
| Runtime source | Watcher coverage and fact freshness are DB-backed with timestamps |
| Read model status | Daily Table and Candidate Pool are exports from repository state |
| Output governance | `output/**` remains export-only and validated by output-scope rules |
| Multi-symbol readiness | Five active StrategyGroups can carry candidate symbol rows without code constants redefining scope |
| Promotion safety | Fresh satisfied symbols can become promotion candidates without exchange-write authority |
| Action-time narrowing | At most one action-time lane input is active for real submit |
| Ticket identity | FinalGate consumes `ticket_id`; Operation Layer consumes `ticket_id + finalgate_pass_id` |
| Safety boundary | No FinalGate bypass, Operation Layer bypass, exchange write bypass, live profile mutation, or sizing mutation |
| Rollback | PG failure stops or disables trading progression; production does not fall back to old file authority |

## Rollback Strategy

After PG cutover, rollback must not restore old file authority in production.

Allowed rollback behavior:

```text
disable trading progression
pause affected StrategyGroups
stop FinalGate / Operation Layer progression
repair or forward-fix PG state
regenerate exports from PG after repair
```

Forbidden rollback behavior:

```text
PG unavailable -> read old JSON as current policy
PG unavailable -> use old output action-time lane
PG unavailable -> use loose FinalGate / Operation Layer parameters
local cache -> production monitor truth
```

## Explicit Non-Goals

This design does not:

- optimize strategy parameters;
- change leverage, notional, or live profile defaults;
- authorize real orders;
- replace FinalGate;
- replace Operation Layer;
- turn Owner policy into submit authority;
- require moving Markdown contracts into DB;
- require moving replay corpora into DB;
- require deleting output exports immediately.

## Authority Boundary

This architecture does not authorize:

- FinalGate bypass;
- Operation Layer bypass;
- exchange write;
- order creation;
- withdrawal or transfer;
- credential mutation;
- live profile mutation;
- order-sizing mutation;
- stale-fact execution;
- missing-protection execution;
- duplicate submit;
- conflicting active position or open-order submit.

It defines where runtime control state should live and how generated views
should consume it.

## Chain Position

```text
chain_position: runtime_control_state_source_of_truth
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: db_backed_control_state_design
first_blocker: dynamic runtime and policy state are still split across JSON files, output snapshots, and code constants
next_action: implement PG schema/seed/runtime-reader/ticket cutover and remove old file authority
stop_condition: production runtime reads PG current state, FinalGate/Operation Layer use ticket lineage, and JSON/MD/output are export-only
owner_action_required: no
authority_boundary: DB migration remains non-executing and must not call FinalGate, Operation Layer, or exchange write
```
