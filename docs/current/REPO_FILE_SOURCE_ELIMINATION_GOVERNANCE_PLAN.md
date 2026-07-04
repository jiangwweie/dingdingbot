---
title: REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN
status: CURRENT_DESIGN
authority: docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md
last_verified: 2026-07-03
---

# Repo File Source Elimination Governance Plan

## Purpose

This document defines the governance plan for removing repo MD/JSON files from
system runtime and trading decisions, and for shrinking the git repository so it
does not permanently store state files, reports, or strategy packs.

The target is:

```text
1. System runtime and trading decisions do not depend on any repo MD/JSON.
2. Git no longer keeps long-lived MD/JSON state files, reports, or strategy packs.
```

Owner-confirmed target:

```text
replace, not parallel
```

After PG cutover, repo MD/JSON/output may be contracts, curated seed inputs,
fixtures, exports, diagnostics, archives, or provenance. They must not be
runtime or trading decision authority and must not be production fallback.

This plan extends the DB-backed control-state design in:

```text
docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md
docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md
docs/current/RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP.md
```

## Decision

The repo must stop being a runtime fact store.

The final information split is:

```text
Code defines behavior.
DB stores policy, registry, runtime state, decisions, and monitor facts.
Object/archive storage preserves large evidence and replay assets.
Generated files are local exports only.
Markdown explains architecture and agent bootstrap only.
```

No production runtime chain, trading decision chain, server monitor, Candidate
Pool, Daily Table, Tradeability Decision, Runtime Safety State, FinalGate
precondition, Operation Layer precondition, or Owner notification decision may
read repo MD/JSON as an authority source after migration is complete.

## Known Current Facts

As of 2026-07-03 local repo scan:

| Area | Count | Current meaning |
| --- | ---: | --- |
| `docs/current` top-level MD/JSON | 23 | Mostly governance, contracts, roadmap, and one monitor baseline JSON |
| `docs/current/strategy-group-handoffs` MD/JSON | 45 | Strategy handoffs, policy JSON, replay corpora, review snapshots, registry baseline |
| `output` MD/JSON | 68 | Generated read models, volatile facts, monitor artifacts, historical reports |
| Tracked `docs/current` top-level files | 21 | Current docs and design contracts |
| Tracked `strategy-group-handoffs` files | 45 | Strategy packs and current strategy snapshots |
| Tracked `output` files | 14 | A reduced but still nonzero output footprint |

Current direct runtime-like file dependencies include:

| File family | Current reader examples | Problem |
| --- | --- | --- |
| `strategygroup-registry-baseline.json` | Tradeability, quality wave, owner policy package, regime map | Strategy semantics are file-sourced |
| `main-control-runtime-tier-policy.json` | Tradeability, tier review, goal progress, policy package | Tier/scope policy is file-sourced |
| `owner-pretrade-runtime-authorization-v0.json` | Candidate Pool | Owner authorization is file-sourced |
| `RUNTIME_MONITOR_BASELINE.json` | Daily check, goal progress | Monitor baseline is file-sourced |
| `output/runtime-monitor/latest-*.json` | Candidate Pool, Daily Table, server monitor, daily checks | Generated outputs become inputs to later decisions |
| replay corpora under `strategy-group-handoffs/*/replay` | Review and policy scripts | Replay assets are stored in current docs tree |

## Mainline MD/JSON Read/Write Map

This map is the required migration frame for the current StrategyGroup
live-enablement chain.

| Node | Reads today | Writes today | Key conflict | Target treatment |
| --- | --- | --- | --- | --- |
| Watcher active status | systemd/runtime scope, exchange/public inputs, Candidate Pool export as candidate universe | server `latest-status.json`, local active-observation JSON | File existence can be mistaken for runtime coverage truth and previous-cycle export can drive observation | Read candidate scope from DB and write watcher coverage rows/events |
| Public/account facts | exchange API, fallback JSON, live-facts packet | public/account fact JSON and MD exports | Freshness source differs by consumer | Write `brc_runtime_fact_snapshots` |
| Detector builders | public facts JSON and strategy-specific files/constants | detector facts JSON/MD | Detector facts become file sources for downstream decisions | Write signal events and fact snapshots |
| Tradeability Decision | PG current projections for strategy, policy, scope, facts, signals, and safety; explicit local JSON only under `--allow-local-file-diagnostic` | `latest-strategygroup-tradeability-decision.json/md` | Export can still be mistaken for an upstream source by later builders | Keep production Tradeability DB-backed and treat JSON/MD as export only |
| Replay/Live Parity Audit | replay JSON, CPM/MPG/SOR detector or watcher outputs | `latest-replay-live-parity-audit.json/md` | Historical parity diagnostics can be confused with current live coverage | Store diagnostic/read-model rows separate from watcher coverage |
| Candidate Pool | authorization JSON, Daily Table, Tradeability, detector outputs, active monitor, replay/live and action-time artifacts | `latest-strategy-live-candidate-pool.json/md` | One generated view recomputes many source priorities | Project readiness, promotion, and action-time lane rows |
| Daily Table | Candidate Pool and other generated outputs | `latest-daily-live-enablement-table.json/md` | Management view can lag or inherit stale generated inputs | Export from current projections |
| Single Lane Packet | Daily Table JSON | `latest-single-lane-task-packet.json/md` | Market waits can become fake closure work | Export task packet only when blocker is non-market |
| Goal Status | report-dir artifacts, optional Candidate Pool JSON, release manifest, legacy pilot status | `strategygroup-runtime-goal-status.json` | Multiple writers and legacy scope diagnostics can override current control facts | One `brc_goal_status_current` projector |
| Server monitor | Candidate Pool, Daily Table, public/account facts, systemd/deploy reports, dedupe JSON | monitor latest JSON and Feishu dedupe JSON | Production monitor becomes a file aggregator | Server monitor runs and notification dedupe tables |

## Conflict Points To Eliminate

| Conflict point | Current symptom | Required closure |
| --- | --- | --- |
| Multiple writers for current state | One status JSON can be rewritten by different post-step paths | A current projection has one owner projector |
| Optional core input | Goal Status can run with or without Candidate Pool | Required current projections must be mandatory inputs |
| Legacy artifact precedence | `pilot_status.watcher_scope_alignment` can still produce scope mismatch | Legacy artifacts become diagnostics only |
| Watcher candidate-universe source | Watcher reads Candidate Pool export as candidate universe | Watcher reads DB candidate scope/runtime bindings |
| Broad read-model source | Tradeability reads many files and then feeds Candidate Pool / Daily Table | Tradeability becomes a DB-backed read model over current projections |
| Parity diagnostic source | Replay/live parity can influence readiness classification | Parity rows stay diagnostic unless promoted through current detector/coverage projections |
| Generated output as runtime input | Candidate Pool, Daily Table, Packet, Goal Status read prior JSON outputs | Runtime builders read repository/current projections |
| Same fact family in multiple directories | Public/account facts can exist under app `output/**` and server report dirs | DB fact snapshots become the source; paths become exports |
| Missing shared lineage | Candidate Pool and Goal Status may describe different ticks | Every current projection stores `projection_run_id` and `input_watermark` |
| Mixed output governance | Volatile facts and control snapshots both live under `output/**` | Output becomes export-only and untracked by default |
| Hard-coded candidate universe | Scope lives in code constants and policy JSON | Candidate scope lives in DB current projection |
| Docs JSON policy source | Owner authorization and tier policy are file inputs | Owner policy events/current projection become source |

## Target End State

### Runtime Source Rules

| Source type | Runtime decision allowed? | Target treatment |
| --- | --- | --- |
| Python code and typed schemas | Yes | Defines behavior, enums, validators, repository interfaces |
| DB tables | Yes | Stores policy, registry, runtime facts, safety state, readiness, monitor state |
| External exchange/public APIs | Yes, through official collectors | Current market/account facts with freshness rules |
| Object/archive storage | No direct authority | Evidence and large replay assets only, referenced by DB metadata |
| Repo Markdown | No | Human/agent explanation only |
| Repo JSON | No | Test fixture or non-production seed only |
| `output/**` JSON/MD | No | Local export/read model only |
| Local cache | No | Developer diagnostic only |

### Git Repository Shape

The repo should keep:

| Keep in git | Reason |
| --- | --- |
| Source code | Runtime behavior |
| Alembic migrations | DB schema history |
| Typed Pydantic/domain schemas | Contract enforced by tests |
| Small unit-test fixtures | Deterministic tests |
| Thin architecture docs | Human/agent bootstrap and durable ADRs |
| Deployment templates | Reproducible infrastructure config |

The repo should not keep:

| Remove from long-lived git | Target home |
| --- | --- |
| Current Owner policy JSON | DB owner policy events/current projection |
| Current strategy registry baseline JSON | DB StrategyGroup registry/version tables |
| Current candidate universe JSON/constants as authority | DB candidate scope tables |
| Current readiness/review snapshots | DB read-model snapshots or archive |
| Daily Table / Candidate Pool current JSON | Generated export only, not committed long-term |
| Public/account fact latest JSON | Runtime fact snapshot tables |
| Watcher/latest monitor JSON | Server monitor tables/reports outside repo |
| Strategy handoff packs | DB registry/RequiredFacts/risk envelope plus archive |
| Replay corpora | test fixture subset, object storage, or research archive |
| Historical reports | archive/object storage, not current repo |

## File Disposition Model

Every repo MD/JSON should be classified into one of these dispositions.

| Disposition | Meaning | Long-term git status |
| --- | --- | --- |
| `keep_thin_doc` | Durable human/agent architecture explanation | Tracked, but small |
| `move_to_code_schema` | Contract should become enum/Pydantic/domain code | Remove doc dependency after code migration |
| `move_to_db_seed` | Structured state should enter DB through seed/import tooling | Remove source JSON after migration |
| `move_to_db_runtime_state` | Dynamic runtime fact/state should be DB-only | Do not track |
| `export_only` | File is generated from DB/read model | Not tracked by default |
| `move_to_fixture` | Small deterministic test fixture | Tracked under tests/fixtures only |
| `move_to_archive` | Historical evidence or strategy pack provenance | Not current repo authority |
| `delete_noise` | Local stale/noise artifact | Remove/untrack |

## Current File Family Plan

### Top-Level `docs/current`

| File family | Target disposition | Notes |
| --- | --- | --- |
| Architecture contracts | `keep_thin_doc` | Keep a small set: information architecture, pre-trade runtime, server monitor, DB governance |
| Blocker/status contracts | `move_to_code_schema` plus thin doc | Blocker classes and state enums should be enforced by code/tests |
| Roadmap/current goal docs | `move_to_db_runtime_state` or `move_to_archive` | Roadmap should become work items/status records, not runtime authority |
| Owner operating docs | `keep_thin_doc` | Keep for product/authority language only |
| `RUNTIME_MONITOR_BASELINE.json` | `move_to_db_seed` or typed config | Monitor baseline should not be repo JSON authority |
| New DB design docs | `keep_thin_doc` | They explain migration only |

### `docs/current/strategy-group-handoffs`

| File family | Target disposition | DB target |
| --- | --- | --- |
| StrategyGroup registry baseline | `move_to_db_seed` | `brc_strategy_groups`, `brc_strategy_group_versions` |
| Individual handoff JSON | `move_to_db_seed` then archive | StrategyGroup versions, RequiredFacts, risk envelope |
| Runtime tier policy JSON | `move_to_db_seed` | Owner policy/tier projection |
| Owner pretrade authorization JSON | `move_to_db_seed` | Owner policy events/current projection, runtime scope bindings |
| Current review snapshots | `move_to_db_runtime_state` | review/read-model snapshot tables |
| RequiredFacts map MD | `move_to_code_schema` and DB RequiredFacts rows | RequiredFacts contract table |
| Replay corpora | `move_to_archive` or `move_to_fixture` | Object store or minimal tests/fixtures |
| Handoff index/task-card docs | `move_to_archive` | Not runtime authority |

### `output`

| File family | Target disposition | DB target |
| --- | --- | --- |
| Daily Table | `export_only` | `brc_control_read_model_snapshots` |
| Candidate Pool | `export_only` | readiness/promotion/action-time tables plus read-model snapshot |
| Tradeability Decision | `export_only` | read-model snapshot over DB facts |
| Runtime Safety State | `export_only` | `brc_runtime_safety_state_snapshots` |
| Public/account facts | `move_to_db_runtime_state` | `brc_runtime_fact_snapshots` |
| Watcher/runtime active monitor | `move_to_db_runtime_state` | `brc_watcher_runtime_coverage` |
| Server monitor latest/dedupe | `move_to_db_runtime_state` | server monitor run/notification tables |
| Review-only/historical reports | `move_to_archive` | archive metadata only if needed |
| Local monitor artifacts | `delete_noise` or local-only | No production source role |

### P0 Old-Source Disposition Inventory

The first PG cutover implementation must include a concrete inventory table for
the current production-affecting file sources. A family-level plan is not enough
for implementation acceptance.

Minimum required rows:

| Old source | Required disposition | Runtime replacement | Deletion or archive condition |
| --- | --- | --- | --- |
| `owner-pretrade-runtime-authorization-v0.json` | `move_to_db_seed` then remove as authority | `brc_owner_policy_events`, `brc_owner_policy_current`, `brc_runtime_scope_bindings` | DB seed validated and runtime readers reject JSON authority |
| `main-control-runtime-tier-policy.json` | `move_to_db_seed` then remove as authority | `brc_owner_policy_events`, `brc_owner_policy_current` | Tier/profile policy version exists in DB and tests prove no runtime JSON read |
| `strategygroup-registry-baseline.json` | `move_to_db_seed` then archive | `brc_strategy_groups`, `brc_strategy_group_versions`, RequiredFacts tables | Registry rows seeded, event specs versioned, old JSON no longer read by runtime |
| StrategyGroup `handoff.json` files | `move_to_db_seed` then archive | StrategyGroup versions, event specs, RequiredFacts, risk envelope, evidence refs | Seed/import audit preserves semantics and runtime ignores handoff files |
| `output/runtime-monitor/latest-strategy-live-candidate-pool.json` | `export_only` | readiness, promotion, action-time lane, ticket tables plus read-model snapshot | Watcher, Goal Status, Daily Table, and monitor no longer consume it as source |
| `output/runtime-monitor/latest-daily-live-enablement-table.json` | `export_only` | DB-backed read-model snapshot | Packet/export tools read repository state, not previous JSON |
| `output/runtime-monitor/latest-single-lane-task-packet.json` | `export_only` | task/export projection over DB blockers | No runtime process reads packet as authority |
| `output/runtime-monitor/latest-*-facts.json` | `move_to_db_runtime_state` | `brc_runtime_fact_snapshots` | Fact collectors write DB snapshots and generated files become optional exports |
| server `strategygroup-runtime-goal-status.json` | `export_only` | `brc_goal_status_current` | One DB owner projector writes current status and JSON is generated view |
| server monitor dedupe JSON | `move_to_db_runtime_state` | `brc_server_monitor_notifications` | Notifier dedupe reads/writes PG state |
| `DEFAULT_SIDE_SCOPE` and broad side constants | `delete_noise` / replace with DB scope | `brc_strategy_group_candidate_scope`, `brc_candidate_scope_event_bindings` | Production candidate/scope builders fail if constant fallback is used |

Any old source with reusable semantics must be converted into code schema, DB
seed, DB runtime state, fixture, or archive. Sources that conflict with the new
PG semantics must be deleted or archived; they must not be downgraded into a
hidden fallback path.

### `config`

| File family | Target disposition | Notes |
| --- | --- | --- |
| Output control snapshot manifest | transitional `keep_thin_config` | Needed until output is export-only and untracked |
| Runtime dynamic config | `move_to_db_seed` or typed config | Must not become hidden runtime state |

## Architecture Options

| Option | Description | Pros | Cons | Decision |
| --- | --- | --- | --- | --- |
| Keep files but ban commits | Runtime still reads files; git stops tracking most of them | Quick repo shrink | Runtime/decision drift remains | Reject |
| Move every MD/JSON into DB as document blobs | DB stores full file payloads | Easy import | DB becomes second file system; weak semantics | Reject |
| Big-bang remove all repo files | Delete files and patch all readers at once | Fast if perfect | High production and test breakage risk | Reject |
| Source-boundary first, DB-backed second | Runtime reads `RuntimeControlStateRepository`; DB gradually replaces file-backed sources; files become exports/archives | Can reduce direct file reads | Keeps compatibility pressure and may preserve a second source of truth | Reject as production target; local non-authority comparison only |
| PG replace-and-cutover | Build PG schema, seed, readers/writers, ticket path, monitor path, old-source removal, and negative tests as one cutover design | Matches Owner target and removes file authority | Larger implementation batch | Recommended |

## Recommended Migration Strategy

The migration must happen in this order:

```text
inventory and classify
-> stop new direct file dependencies
-> introduce RuntimeControlStateRepository
-> introduce current projection ownership and lineage
-> PG schema / seed / negative constraints
-> PG-source policy/scope/coverage/facts/promotion/ticket/read models
-> untrack output/state/report files
-> archive strategy packs and large replay files
-> delete runtime file fallback
```

Do not start by deleting files. First remove runtime dependency on them.

## Implementation Plan

### Phase 0: Inventory And Classification

Deliverables:

- generate `repo_file_source_inventory.json` locally;
- classify every MD/JSON under `docs/current`, `output`, and `config`;
- record writer, reader, source role, disposition, and migration target.

Acceptance:

| Check | Done when |
| --- | --- |
| Inventory coverage | Every current MD/JSON has one disposition |
| Runtime dependency map | Every script reading docs/output JSON is listed |
| Deletion safety | No file is removed before its runtime reader is migrated |

### Phase 1: Direct Runtime File Read Freeze

Deliverables:

- add validator that fails new direct reads from runtime paths:
  - `docs/current/**/*.json`;
  - `output/runtime-monitor/latest-*.json`;
  - local monitor cache paths;
- current implemented validator:
  - `scripts/validate_runtime_file_authority_boundary.py`;
  - `config/runtime_file_authority_boundary.json`;
- allow exceptions only for:
  - test fixtures;
  - explicit import/seed tools;
  - export writers;
  - local migration comparison implementation that cannot become production
    current authority.

Acceptance:

| Check | Done when |
| --- | --- |
| New direct reads blocked | CI/test validator catches new raw path reads |
| Exceptions explicit | Each exception has a file, reason, and sunset condition |
| Runtime scripts scoped | Candidate Pool, Daily Table, Tradeability, server monitor become priority migration targets |
| Baseline debt frozen | `python3 scripts/validate_runtime_file_authority_boundary.py --json` passes and blocks new source literals or extra occurrences in monitored mainline files |

### Phase 2: RuntimeControlStateRepository

Deliverables:

- add repository interface;
- add PG-backed implementation and local-only inventory/comparison helpers where needed;
- route Candidate Pool, Daily Table, Tradeability, and server monitor through it;
- keep JSON outputs as exports only.

Acceptance:

| Check | Done when |
| --- | --- |
| Single read boundary | Main runtime builders no longer own raw docs/output path decisions |
| Migration comparison isolated | File-backed comparison exists only in tests/import tools and cannot be selected by Tokyo production runtime |
| DB production ready | Repository source is `db` in production; missing DB state fails closed rather than falling back to files |

### Phase 2B: Current Projection Ownership

Deliverables:

- define one owner projector for each current projection;
- add projection lineage fields: `projection_run_id`, `input_watermark`,
  `source_priority`, and `owner_projector`;
- make legacy artifacts diagnostics-only;
- make Goal Status consume the Candidate Pool/readiness current projection
  instead of optional generated JSON.

Acceptance:

| Check | Done when |
| --- | --- |
| Single writer | Candidate Pool, Daily Table, Goal Status, Runtime Safety State, and server monitor current states each have one owner projector |
| No legacy overwrite | Legacy `pilot_status`/watcher-scope alignment cannot set main current blockers when current coverage projection is complete |
| Shared lineage | Goal Status and Candidate Pool can prove they used the same watcher/fact watermark |
| Export-only status | `strategygroup-runtime-goal-status.json` is a generated export, not a file source |

### Phase 3: P0 DB Source Migration

Migrate the state that directly controls multi-strategy, multi-symbol runtime:

| Current source | Target |
| --- | --- |
| `owner-pretrade-runtime-authorization-v0.json` | Owner policy events/current projection |
| `main-control-runtime-tier-policy.json` | Tier/scope policy tables |
| `DEFAULT_CANDIDATE_UNIVERSE` | Candidate scope table |
| runtime active coverage JSON | Watcher runtime coverage table |
| public/account fact latest JSON | Runtime fact snapshots |

Acceptance:

| Check | Done when |
| --- | --- |
| Policy DB-backed | Candidate Pool derives scope from DB/current projection |
| Coverage DB-backed | `server_runtime_coverage` is row-level DB state, not file presence |
| Fact freshness DB-backed | public/account facts have observed/valid-until timestamps |
| No authority expansion | DB import does not expand symbol, side, leverage, notional, profile, or exchange-write authority |

### Phase 4: Strategy Pack Migration

Migrate strategy packs out of `docs/current/strategy-group-handoffs`.

| Current source | Target |
| --- | --- |
| registry baseline JSON | StrategyGroup registry/version tables |
| handoff JSON | StrategyGroup version, RequiredFacts, risk envelope |
| RequiredFacts map MD | RequiredFacts table and typed schema |
| replay corpora | archive/object store or minimal test fixtures |
| current review snapshots | review/read-model DB snapshots |

Acceptance:

| Check | Done when |
| --- | --- |
| Strategy semantics DB-backed | Tradeability does not read handoff JSON or registry baseline JSON |
| RequiredFacts structured | Fact contracts are DB/code schema, not Markdown parsing |
| Replay removed from current docs | Large replay JSON no longer lives in `docs/current` as current authority |

### Phase 5: Output Export-Only Conversion

Convert `output/**` from tracked artifact bucket to local export directory.

Deliverables:

- update output manifest to transitional status;
- route read-model payloads to DB snapshot table;
- write JSON/MD only as local export when command requests it;
- untrack historical output files after validating DB/read-model replacement.

Acceptance:

| Check | Done when |
| --- | --- |
| No output as source | Runtime scripts do not read `output/**` for decisions |
| Output git footprint near zero | Routine commits include no output files |
| Exports reproducible | DB-backed command can regenerate any allowed export |

### Phase 6: Thin Docs And Archive

Reduce docs to durable architecture and bootstrap only.

Keep only:

- project information architecture;
- runtime source elimination plan;
- DB architecture/table design;
- pre-trade runtime contract;
- server monitor contract;
- authority/safety model;
- agent bootstrap guide.

Archive or delete:

- stale roadmaps;
- old task cards;
- current-state reports;
- duplicate handoff docs;
- strategy packs after DB migration;
- generated MD counterparts.

Acceptance:

| Check | Done when |
| --- | --- |
| Thin docs | `docs/current` has only durable explanation docs |
| No machine authority | No production/runtime script reads docs MD/JSON |
| Archive boundary | Historical material is compressed or externalized and not current authority |

### Phase 7: Remove Transitional File Backing

Runtime fallback to repo files must be removed as part of PG cutover. Do not
accept a production state where PG is available but runtime still falls back to
repo files.

Acceptance:

| Check | Done when |
| --- | --- |
| DB-only production | `RUNTIME_CONTROL_STATE_SOURCE=db` is required in production |
| File-backed disabled | File-backed repository works only in tests/import tools |
| Fail closed | Missing DB state blocks live-submit readiness rather than falling back to repo JSON |

## Validators And Tests

### Required Validators

| Validator | Purpose |
| --- | --- |
| `validate_runtime_file_source_ban.py` | Detect direct runtime reads of repo MD/JSON |
| `validate_repo_file_inventory.py` | Ensure every MD/JSON has disposition and owner |
| `validate_output_export_only.py` | Ensure output files are not runtime inputs or routine commit candidates |
| `validate_db_control_state_seed.py` | Verify imported policy/registry/scope rows preserve boundaries |
| `validate_runtime_control_state_repository.py` | Verify repository returns complete control state and fails closed |
| `validate_current_projection_ownership.py` | Ensure each current projection has one owner writer and required lineage |

### Required Test Classes

| Test class | Required behavior |
| --- | --- |
| Repository parity tests | File-backed and DB-backed repository produce same read model during migration |
| Source-ban tests | Candidate Pool, Daily Table, Tradeability, server monitor do not read raw files |
| Projection ownership tests | Goal Status cannot be written without Candidate Pool/current readiness lineage once that projection is authoritative |
| Policy import tests | Owner policy JSON imports to DB without authority expansion |
| Candidate scope tests | Five StrategyGroups and multi-symbol scopes are DB-backed |
| Coverage/facts tests | stale/missing facts fail closed at Runtime Safety State |
| Export tests | JSON/MD exports can be regenerated from DB snapshots |
| Ticket/gate handoff tests | FinalGate rejects missing `ticket_id`; Operation Layer rejects missing `ticket_id + finalgate_pass_id` |
| Negative semantics tests | Unsupported side/symbol/event, generated_at freshness, replay-as-live, JSON authority inputs, and duplicate signal/ticket/submit paths are rejected |

## Git Governance Rules

### New Rule

Routine commits must not add MD/JSON that represents current state, reports, or
strategy packs.

Allowed MD/JSON in git:

| Class | Allowed path shape |
| --- | --- |
| Thin architecture docs | `docs/current/*.md` only when durable and non-stateful |
| DB/schema migration metadata | migration files and schema code |
| Small test fixtures | `tests/fixtures/**` |
| Deployment templates | `deploy/**`, `.env*.example` |
| Transitional manifest | `config/output_control_snapshots.json` until output is export-only |

Disallowed MD/JSON in git:

| Class | Example |
| --- | --- |
| Current runtime state | `latest-runtime-active-observation-status.json` |
| Generated control read models | `latest-daily-live-enablement-table.json` |
| Public/account fact snapshots | `latest-binance-usdm-public-facts.json` |
| Owner current policy snapshots | `owner-pretrade-runtime-authorization-v0.json` after DB migration |
| Strategy packs | `strategy-group-handoffs/*/handoff.json` after DB migration |
| Large replay corpora | `strategy-group-handoffs/*/replay/*.json` |
| Local monitor reports | `latest-local-monitor-sequence.json` |

### Commit Gate

Before accepting routine commits:

```text
python3 scripts/validate_runtime_file_source_ban.py
python3 scripts/validate_repo_file_inventory.py --git-status
python3 scripts/validate_output_export_only.py --git-status --git-tracked
```

During transition, existing validators may keep their current names, but their
target behavior should converge to the rules above.

## Production Runtime Rule

Production runtime must use:

```text
RUNTIME_CONTROL_STATE_SOURCE=db
```

Production runtime must not use:

```text
RUNTIME_CONTROL_STATE_SOURCE=file
RUNTIME_CONTROL_STATE_SOURCE=local_cache
```

File-backed mode is allowed only for:

- migration parity tests;
- local development with explicit non-production flag;
- one-shot seed/import commands;
- fixture-based unit tests.

It is not a Tokyo production fallback.

## Rollback Strategy

Rollback must restore software behavior without restoring repo file authority.

| Scenario | Rollback behavior |
| --- | --- |
| DB repository read failure | Production fails closed for live-submit readiness |
| DB migration import bug | Roll back DB migration or re-import from archived seed, not from current docs JSON as runtime source |
| Export generation bug | Disable export command; runtime continues from DB |
| Monitor notification bug | Disable notification send or retry from DB monitor state; do not use local heartbeat fallback |
| Strategy registry import bug | Park affected StrategyGroup or revert DB rows; do not re-enable handoff JSON as runtime authority |
| PG current state unavailable | Stop ticket / FinalGate / submit progression and forward-fix PG state; do not restore old file authority |

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| DB becomes a generic JSON dump | Use normalized tables for policy/scope/facts; allow JSONB only for nested evidence |
| Migration breaks current builders | Use local parity tests and forward-fix; do not preserve production file authority |
| Strategy semantics lose provenance | Store evidence refs and archive IDs in DB |
| Git cleanup deletes needed fixtures | Inventory disposition before untracking |
| Runtime silently falls back to files | Production source env must be `db`; fallback disabled in production |
| Owner policy import expands authority | Import validators compare symbol/side/notional/leverage/profile before and after |
| Generated exports become source again | Source-ban validator checks runtime scripts |

## Work Breakdown

### P0-A: Inventory And Ban

```text
Task ID: P0-RUNTIME-FILE-SOURCE-INVENTORY-AND-BAN
Goal: classify all repo MD/JSON and block new direct runtime file reads
Capability unlocked: controlled migration without new file-source drift
```

### P0-B: Repository Boundary

```text
Task ID: P0-RUNTIME-CONTROL-STATE-REPOSITORY-BOUNDARY
Goal: route Candidate Pool, Daily Table, Tradeability, and server monitor through RuntimeControlStateRepository
Capability unlocked: runtime builders no longer select raw MD/JSON sources
```

### P0-C: Current Projection Ownership

```text
Task ID: P0-CURRENT-PROJECTION-OWNERSHIP-CLOSURE
Goal: make each current projection single-writer with projection_run_id, input_watermark, and legacy diagnostics separated from current blockers
Capability unlocked: Goal Status, Candidate Pool, Daily Table, Runtime Safety State, and server monitor cannot overwrite each other with stale file authority
```

### P0-D: Policy And Scope DB Source

```text
Task ID: P0-OWNER-POLICY-CANDIDATE-SCOPE-DB-SOURCE
Goal: migrate Owner authorization, tier policy, candidate universe, and runtime scope to DB-backed current projection
Capability unlocked: five StrategyGroups multi-symbol scope is DB-backed
```

### P0-E: Runtime Coverage And Facts DB Source

```text
Task ID: P0-RUNTIME-COVERAGE-FACTS-DB-SOURCE
Goal: move watcher coverage, public facts, account facts, and runtime safety inputs to DB snapshots
Capability unlocked: fresh-signal promotion can rely on server-backed facts instead of latest JSON files
```

### P0-F: Ticket And Gate Handoff DB Source

```text
Task ID: P0-ACTION-TIME-TICKET-GATE-HANDOFF-DB-SOURCE
Goal: create Action-Time Ticket identity and make FinalGate consume ticket_id while Operation Layer consumes ticket_id + finalgate_pass_id
Capability unlocked: loose JSON/candidate/order parameters can no longer bypass PG lineage
```

### P0-G: Old Authority Removal

```text
Task ID: P0-OLD-FILE-AUTHORITY-REMOVAL
Goal: delete, clean, convert, or archive old MD/JSON/output/code fallback paths that can still decide runtime scope, signals, tickets, gates, or submit identity
Capability unlocked: PG cutover has one production authority path
```

### P1-A: Strategy Pack Migration

```text
Task ID: P1-STRATEGYGROUP-PACK-DB-MIGRATION
Goal: migrate strategy registry, handoffs, RequiredFacts, and risk envelope into DB/code schema
Capability unlocked: Tradeability and Candidate Pool no longer depend on strategy-group-handoffs JSON
```

### P1-B: Output Export-Only Cleanup

```text
Task ID: P1-OUTPUT-EXPORT-ONLY-GIT-CLEANUP
Goal: untrack generated output and regenerate exports from DB read-model snapshots
Capability unlocked: git stops preserving current runtime/report state
```

### P2: Thin Docs Archive

```text
Task ID: P2-DOCS-THINNING-AND-ARCHIVE
Goal: shrink docs/current to durable architecture/bootstrap docs and archive current-state material
Capability unlocked: repo no longer carries strategy/report/doc sprawl as current authority
```

## Completion Definition

The governance target is complete only when:

| Requirement | Done when |
| --- | --- |
| Runtime no repo MD/JSON dependency | Production Candidate Pool, Daily Table, Tradeability, Runtime Safety State, server monitor, FinalGate preconditions, and Operation Layer preconditions read DB/code/API sources only |
| Trading decisions DB-backed | Policy, registry, candidate scope, runtime coverage, facts, live signal events, readiness, promotion, action-time lane state, Action-Time Tickets, FinalGate handoff, and Operation Layer handoff are DB-backed |
| Output export-only | `output/**` is regenerated from DB/read models and not tracked in routine commits |
| Strategy packs retired | `strategy-group-handoffs` is no longer a runtime source; packs are DB rows plus archive provenance |
| Docs thin | Current docs contain durable architecture and bootstrap only |
| Validators enforce boundary | CI or focused tests fail direct runtime reads of repo MD/JSON |
| Safety preserved | No FinalGate bypass, Operation Layer bypass, exchange write bypass, live profile mutation, sizing mutation, stale-fact submit, or missing-protection submit |

## Authority Boundary

This governance plan does not authorize:

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

It only defines how repo files lose runtime authority and how DB/code/API
sources become the production decision boundary.

## Chain Position

```text
chain_position: repo_file_source_elimination
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: governance_plan_ready
first_blocker: runtime and trading decisions still have transitional repo MD/JSON and output JSON source paths
next_action: implement inventory/source-ban validator and RuntimeControlStateRepository boundary
stop_condition: production runtime reads DB/code/API sources only and git no longer carries state/report/strategy-pack MD/JSON as current authority
owner_action_required: no
authority_boundary: file-source elimination is non-executing and must not call FinalGate, Operation Layer, or exchange write
```
