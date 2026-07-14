---
title: STRATEGY_GOVERNANCE_PIPELINE_DB_DESIGN
status: CURRENT_DESIGN
authority: docs/current/STRATEGY_GOVERNANCE_PIPELINE_DB_DESIGN.md
last_verified: 2026-07-03
---

# Strategy Governance Pipeline DB Design

## Purpose

This document defines the target **Strategy Governance Pipeline** for moving a
strategy from research evidence into the front edge of the pre-trade runtime.

The immediate implementation priority remains the **RuntimeControlStateRepository**
and DB-backed control-state migration defined in:

```text
docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md
docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md
docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md
```

This pipeline design is recorded now so strategy intake does not keep growing
as Markdown and JSON handoff files. It is not a request to implement a new
pipeline before the P0 DB/source-boundary work.

## Decision

The Strategy Governance Pipeline should become a **P1 DB-backed admission and
state-projection layer** built on top of the Runtime Control State DB.

The sequence is:

```text
research/docs/replay
-> import and normalize
-> DB strategy candidate
-> governance decision
-> admission request
-> StrategyGroup registry/version/facts/policy/scope rows
-> Tradeability Decision
-> Candidate Pool
-> fresh-signal promotion
-> action-time lane input
```

The pipeline must not become:

```text
new report layer
-> more hand-edited JSON
-> manual Owner gate operation
-> live order authority
```

## Known Current Facts

| Fact | Current evidence |
| --- | --- |
| Current strategy evaluation already defines stages from research to live-submit readiness | `docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md` |
| Engineering intake already requires a thesis, risk envelope, first blocker, next action, and kill condition | `docs/current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md` |
| Tradeability Decision already defines the current can-trade read model | `docs/current/TRADEABILITY_DECISION_CONTRACT.md` |
| Pre-Trade Runtime already supports five active StrategyGroups with multiple candidate symbols | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| WIP limits active StrategyGroups, not candidate symbols inside an active StrategyGroup | `docs/current/WIP_AND_STOP_RULE_CONTRACT.md` |
| DB table design already includes registry, RequiredFacts, Owner policy, candidate scope, runtime coverage, readiness, promotion, action-time, and runtime safety tables | `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| Current PG/current projections already represent partial pipeline steps | Strategy research intake, trial asset admission, Tradeability Decision, Candidate Pool, and Daily Table must be represented by DB rows or PG-backed current projections rather than standalone JSON/MD builders |
| Existing PG models already contain strategy family, admission, trial binding, observation, and forward-review tables | `src/infrastructure/pg_models.py` |

## Problem

The project has pieces of a strategy governance pipeline, but they are not yet a
single state machine.

| Current piece | What it does | Current weakness |
| --- | --- | --- |
| Strategy research docs and replay | Explain candidate semantics and evidence | Not a production source; can drift from runtime scope |
| Handoff packs | Summarize strategy semantics for main control | Stored as repo MD/JSON; too easy to treat as runtime truth |
| Intake scripts | Produce review or admission artifacts | Output-first; not a durable current-state store |
| Registry contracts | Define the strategy asset layer | Not yet DB-backed as the runtime consumption source |
| Tradeability Decision | Answers can-trade and first blocker | Still depends on file-backed sources during migration |
| Candidate Pool | Expands per-symbol readiness and promotion state | Should be DB/read-model backed, not output-chain backed |
| Daily Table | Summarizes current live-enablement management | Should be generated from DB-backed read models |

The failure mode is:

```text
strategy document says admitted
retired handoff JSON says trial candidate
retired policy JSON says scoped
runtime coverage file says missing
Candidate Pool picks one source by file availability
```

That is not a strategy-quality problem. It is a source-boundary and state
projection problem.

## Scope

### In Scope

The pipeline design covers:

- normalized research candidate import;
- strategy governance decisions;
- admission requests and decisions;
- mapping accepted candidates into StrategyGroup registry/version rows;
- RequiredFacts and risk-envelope normalization;
- Owner policy and candidate-scope handoff into DB;
- Tradeability/Candidate Pool projection;
- promotion into action-time lane input after fresh satisfied signals.

### Out Of Scope

This design does not implement:

- Alembic migrations;
- SQLAlchemy models;
- import CLI commands;
- Owner runtime status output;
- detector code;
- FinalGate or Operation Layer changes;
- exchange writes;
- live profile, sizing, notional, leverage, or credential mutation.

## Relationship To DB Migration

The pipeline should be built after the P0 DB/source-boundary work, not before
it.

| Layer | Priority | Purpose | Pipeline dependency |
| --- | --- | --- | --- |
| RuntimeControlStateRepository | P0 | Compress dynamic state reads behind one boundary | Required before pipeline state can be trusted |
| Owner policy and candidate scope DB | P0 | Remove policy/symbol/scope JSON authority | Required before admission can create usable scope |
| Runtime coverage and facts DB | P0 | Replace latest output files as runtime facts | Required before readiness/promotion can be computed reliably |
| Read-model export-only outputs | P0/P1 | Keep JSON/MD exports without making them authority | Required for agent compatibility during migration |
| Strategy Governance Pipeline DB | P1 | Convert strategy research/intake into DB admission state | Depends on registry, policy, facts, and candidate scope DB |
| Owner pipeline automation | P2 | Make strategy intake easier to operate | Depends on stable DB pipeline state |

The right ordering is:

```text
first make runtime/control state DB-backed
then migrate any archive-only strategy handoff provenance into DB admission data
then optimize the strategy governance pipeline
```

## Target Pipeline States

The pipeline has one broad idea:

```text
research value
-> engineering intake
-> final-owned strategy asset
-> scoped runtime observation
-> pre-trade readiness
-> fresh-signal promotion
-> action-time input
```

| State | Meaning | Source of truth after migration | Real order authority |
| --- | --- | --- | --- |
| `research_candidate` | A strategy idea or vocabulary item exists in research | Research archive plus import metadata | No |
| `experiment_worthy` | Thesis, regime fit, risk, and evidence justify further work | DB research candidate review | No |
| `engineering_intake_ready` | One first blocker, one next action, risk envelope, and kill condition exist | DB governance decision | No |
| `trial_asset_admission_candidate` | Main control prepares final-owned admission | DB admission request | No |
| `admitted_trial_asset` | StrategyGroup exists as a final-owned asset | DB registry/version/policy projection | No |
| `armed_observation` | Runtime may observe scoped symbols without submit authority | DB candidate scope and watcher coverage | No |
| `pretrade_ready` | Non-market blockers are closed for a scoped candidate symbol | DB readiness row | No |
| `promotion_candidate` | Fresh signal and facts are satisfied; candidate may approach action-time | DB promotion candidate | No |
| `action_time_lane_input` | At most one narrowed lane enters action-time fact refresh | DB action-time lane input | No by itself; official gates still required |

Existing contract labels such as `tiny_live_intake_candidate`,
`tiny_live_ready`, `live_submit_ready`, `paper_observation_candidate`, and
`role_only_intake_candidate` remain valid. The pipeline should store both:

```text
pipeline_state = normalized pipeline state
contract_stage = current contract vocabulary
```

This avoids breaking current artifacts while making DB state easier to query.

## State Transition Rules

| From | To | Required condition | First blocker when missing |
| --- | --- | --- | --- |
| `research_candidate` | `experiment_worthy` | Thesis, regime fit, rough evidence, and failure modes are expressible | `review_only_warning` or strategy review rejection |
| `experiment_worthy` | `engineering_intake_ready` | One-page engineering brief has first blocker, next action, risk envelope, and kill condition | `schema_invalid` for missing intake fields, or `review_only_warning` |
| `engineering_intake_ready` | `trial_asset_admission_candidate` | Main control chooses to spend admission effort inside WIP/stop rules | `scope_not_attached` or strategy review deferral |
| `trial_asset_admission_candidate` | `admitted_trial_asset` | Registry version, RequiredFacts draft, risk envelope, and policy boundary are recorded | `artifact_missing`, `schema_invalid`, or `policy_scope_missing` |
| `admitted_trial_asset` | `armed_observation` | Candidate scope, watcher target, detector, and non-submit runtime observation are attached | `detector_not_attached`, `watcher_tick_missing`, or `runtime_profile_scope_missing` |
| `armed_observation` | `pretrade_ready` | Per-symbol facts compute, blockers classify, and non-live action-time path is known | `computed_not_satisfied`, `replay_live_rule_mismatch`, or `action_time_boundary_not_reproduced` |
| `pretrade_ready` | `promotion_candidate` | Fresh signal appears, facts are satisfied, and risk state is acceptable | `market_wait_validated` when only signal is absent |
| `promotion_candidate` | `action_time_lane_input` | Scope permits rehearsal or live-submit candidate and arbitration selects one lane | `runtime_profile_scope_missing`, `policy_scope_missing`, or `active_position_resolution` |
| `action_time_lane_input` | `live_submit_ready` | Action-time facts, candidate/auth evidence, Runtime Safety State, FinalGate, Operation Layer, protection, account, and exchange facts pass | `hard_safety_stop` or exact execution-gate blocker |

## DB Entity Design

### Reuse First

The pipeline should reuse existing and planned tables instead of creating a
parallel strategy database.

| Domain | Reuse target | Role |
| --- | --- | --- |
| Strategy family identity | `brc_strategy_families`, `brc_strategy_family_versions`, `brc_strategy_family_registry` | Broad family and version provenance |
| Admission workflow | `brc_admission_requests`, `brc_admission_decisions`, `brc_admission_trial_bindings` | Formal request/decision/binding path |
| Strategy asset identity | `brc_strategy_groups`, `brc_strategy_group_versions` | Runtime-facing StrategyGroup registry |
| Required facts | `brc_required_fact_contracts` | Structured fact contract |
| Owner policy | `brc_owner_policy_events`, `brc_owner_policy_current` | Scoped authorization and current policy projection |
| Candidate scope | `brc_strategy_group_candidate_scope`, `brc_runtime_scope_bindings` | Multi-symbol pre-trade scope |
| Runtime observation | `brc_watcher_runtime_coverage`, `brc_runtime_fact_snapshots`, `brc_live_signal_events` | Server-backed runtime facts |
| Readiness and promotion | `brc_pretrade_readiness_rows`, `brc_promotion_candidates`, `brc_action_time_lane_inputs` | Runtime-front progression |
| Runtime safety | `brc_runtime_safety_state_snapshots` | Live-submit safety read model |

### P1 Additions

The minimum additional pipeline tables should be small and admission-oriented.

#### `brc_strategy_research_import_runs`

Purpose: record import batches from research/docs/archives into normalized DB
candidates.

| Column | Type | Rule |
| --- | --- | --- |
| `import_run_id` | `String(128)` PK | Stable import run ID |
| `source_kind` | `String(64)` | `research_archive`, `handoff_pack`, `manual_seed`, `backfill` |
| `source_ref` | `String(512)` | Archive ID, repo path at migration time, or object-store ref |
| `source_checksum` | `String(128)` nullable | Input checksum when available |
| `status` | `String(64)` | `parsed`, `normalized`, `partial`, `rejected`, `superseded` |
| `candidate_count` | `Integer` | Number of candidates parsed |
| `accepted_count` | `Integer` | Number normalized into candidate rows |
| `rejected_count` | `Integer` | Number rejected with reason |
| `created_at_ms` | `BIGINT` | Import time |
| `created_by` | `String(128)` | `system`, `codex_seed`, or migration actor |
| `metadata` | `JSONB` | Non-authority import notes |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_strategy_research_import_runs_status` | Status enum listed above |
| `idx_brc_strategy_research_import_runs_source` | `(source_kind, created_at_ms)` |

#### `brc_strategy_research_candidates`

Purpose: normalized research-side candidate before it becomes a final-owned
StrategyGroup asset.

| Column | Type | Rule |
| --- | --- | --- |
| `research_candidate_id` | `String(128)` PK | Stable candidate ID |
| `import_run_id` | `String(128)` nullable | Import run ref |
| `proposed_strategy_group_id` | `String(128)` nullable | Proposed StrategyGroup ID |
| `owner_label` | `String(256)` | Short label |
| `pipeline_state` | `String(64)` | `research_candidate`, `experiment_worthy`, `engineering_intake_ready`, `rejected`, `parked` |
| `contract_stage` | `String(64)` | Current contract vocabulary when applicable |
| `asset_class` | `String(64)` | Example: `crypto_perpetual` |
| `supported_symbols` | `JSONB` | Candidate symbols or baskets |
| `supported_sides` | `JSONB` | `long`, `short`, `both`, or strategy-specific |
| `regime_fit` | `Text` | Regime/session/product fit |
| `edge_thesis` | `Text` | Strategy thesis |
| `trade_logic` | `Text` | Entry/exit/protection idea |
| `required_facts_draft` | `JSONB` | Draft fact keys and sources |
| `risk_envelope_draft` | `JSONB` | Loss unit, attempt cap, hard stops, path risks |
| `first_blocker_class` | `String(128)` nullable | Contract blocker when not ready |
| `next_action` | `Text` nullable | One next action |
| `kill_condition` | `Text` nullable | Required before engineering intake ready |
| `evidence_refs` | `JSONB` | Archive or review refs, not full replay blobs |
| `created_at_ms` | `BIGINT` | Insert time |
| `updated_at_ms` | `BIGINT` | Update time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_strategy_research_candidates_pipeline_state` | Pipeline state enum listed above |
| `ck_brc_strategy_research_candidates_intake_ready` | `engineering_intake_ready` requires first blocker, next action, risk envelope, and kill condition |
| `idx_brc_strategy_research_candidates_state` | `(pipeline_state, updated_at_ms)` |
| `idx_brc_strategy_research_candidates_group` | `(proposed_strategy_group_id)` |

#### `brc_strategy_governance_decisions`

Purpose: append-only decision ledger for strategy governance transitions.

| Column | Type | Rule |
| --- | --- | --- |
| `governance_decision_id` | `String(128)` PK | Stable decision ID |
| `subject_type` | `String(64)` | `research_candidate`, `strategy_group`, `candidate_scope` |
| `subject_id` | `String(128)` | Subject row ID |
| `strategy_group_id` | `String(128)` nullable | StrategyGroup when known |
| `decision` | `String(64)` | `keep_observing`, `revise`, `promote`, `park`, `kill`, `go_live`, `do_not_go_live`, `block_for_safety` |
| `promotion_scope` | `String(64)` nullable | `intake_only`, `trial_admission`, `armed_observation`, `tiny_live_ready_review`, `l4_eligibility_review` |
| `from_pipeline_state` | `String(64)` nullable | Previous state |
| `to_pipeline_state` | `String(64)` nullable | New state |
| `first_blocker_class` | `String(128)` nullable | Remaining blocker |
| `decision_reason` | `Text` | Plain reason |
| `evidence_refs` | `JSONB` | DB/archive/read-model refs |
| `owner_policy_required` | `Boolean` | True only for scoped Owner policy decisions |
| `authority_boundary` | `Text` | Must state no order authority unless official runtime later grants it |
| `decided_at_ms` | `BIGINT` | Decision time |
| `decided_by` | `String(128)` | Owner/system/agent/review process |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_strategy_governance_decisions_scope` | `decision='promote'` requires non-null `promotion_scope` |
| `ck_brc_strategy_governance_decisions_no_order_authority` | Authority boundary must not imply exchange write |
| `idx_brc_strategy_governance_decisions_subject` | `(subject_type, subject_id, decided_at_ms)` |
| `idx_brc_strategy_governance_decisions_group` | `(strategy_group_id, decided_at_ms)` |

#### `brc_strategy_pipeline_state_current`

Purpose: current projection for product and agent planning. This is a read
projection, not a separate authority source.

| Column | Type | Rule |
| --- | --- | --- |
| `pipeline_current_id` | `String(160)` PK | Deterministic scope ID |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `research_candidate_id` | `String(128)` nullable | Origin candidate |
| `pipeline_state` | `String(64)` | Target pipeline state |
| `contract_stage` | `String(64)` | Current contract stage |
| `tradeability_decision_ref` | `String(192)` nullable | Tradeability read-model ref |
| `readiness_row_ref` | `String(192)` nullable | Pretrade readiness ref |
| `promotion_candidate_ref` | `String(192)` nullable | Promotion ref |
| `action_time_lane_input_ref` | `String(192)` nullable | Action-time ref |
| `first_blocker_class` | `String(128)` nullable | Current first blocker |
| `next_action` | `Text` nullable | One next action |
| `source_watermark` | `JSONB` | Source rows and versions |
| `computed_at_ms` | `BIGINT` | Projection time |
| `valid_until_ms` | `BIGINT` nullable | Freshness when runtime-derived |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_strategy_pipeline_state_current_group` | Unique current row per StrategyGroup |
| `idx_brc_strategy_pipeline_state_current_state` | `(pipeline_state, computed_at_ms)` |

## Import And Normalization Flow

The import path should treat old documents as migration input, not runtime
truth.

```text
research doc / archive-only handoff provenance / replay summary
-> parse into candidate draft
-> validate required intake fields
-> store normalized candidate row
-> record governance decision
-> create or update admission request
-> create registry/version/facts/policy/scope rows only after accepted decision
```

| Step | Input | Output | Failure behavior |
| --- | --- | --- | --- |
| Parse | Research archive, archive-only handoff provenance, seed row | Import run and raw parse result | Mark run `partial` or `rejected` |
| Normalize | Parsed candidate | `brc_strategy_research_candidates` | Reject missing thesis, side, risk, or evidence refs |
| Intake validate | Normalized candidate | `engineering_intake_ready` candidate | Block if first blocker, next action, risk envelope, or kill condition is absent |
| Governance decision | Candidate and evidence | `brc_strategy_governance_decisions` | Park, revise, reject, or promote with explicit scope |
| Admission request | Promoted candidate | `brc_admission_requests` or successor admission row | Block if policy or facts cannot be expressed |
| Registry projection | Accepted admission | `brc_strategy_groups`, versions, RequiredFacts | Block if schema invalid or authority boundary missing |
| Runtime projection | Registry/policy/scope | Tradeability and Candidate Pool rows | Block if runtime scope, coverage, or facts are absent |

## Read Models

The pipeline should expose generated read models, but those read models must be
exports from DB state.

| Read model | Backing rows | Purpose |
| --- | --- | --- |
| Strategy Pipeline State | research candidates, governance decisions, admission, registry, Tradeability refs | Explain where each StrategyGroup sits from research to action-time front door |
| Tradeability Decision | registry, policy, facts, scope, runtime safety refs | Answer can-trade and first blocker |
| Candidate Pool | candidate scope, runtime coverage, fact snapshots, signals, readiness rows | Answer per-symbol readiness and promotion state |
| Daily Live Enablement Table | strategy pipeline current, Candidate Pool, Tradeability, Runtime Safety | Pick current management focus without suppressing fresh-signal promotion |
| Owner runtime status | policy, Tradeability, Runtime Safety, pipeline summary | Show running/waiting/needs-intervention state |

## Authority Model

The pipeline preserves the global authority split:

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

| Pipeline layer | May decide | Must not decide |
| --- | --- | --- |
| Research candidate | Whether an idea is worth review | Runtime scope, live submit, order sizing |
| Governance decision | Promote, revise, park, kill, or request admission | FinalGate, Operation Layer, exchange write |
| Admission request | Whether a final-owned asset should be created | Action-time freshness or live-submit safety |
| Registry/version | Strategy semantics, RequiredFacts, risk envelope | Current can-trade answer |
| Owner policy | Scope, tier, profile, notional, leverage, attempt cap | Bypass stale facts, protection, FinalGate, Operation Layer |
| Tradeability Decision | Can-trade now and first blocker | Create orders or mutate runtime profile |
| Candidate Pool | Per-symbol readiness and promotion candidates | Real submit authority |
| Action-time lane input | One narrowed pre-submit lane | Submit without Runtime Safety, FinalGate, Operation Layer |

## Validators

P1 implementation should add validators in this order.

| Validator | Purpose | Acceptance |
| --- | --- | --- |
| Research import validator | Ensure imported candidates have thesis, side, risk, evidence refs, and no authority fields | Invalid candidates cannot become `engineering_intake_ready` |
| Promotion scope validator | Reject generic `promote` without `promotion_scope` | Every promote decision states intake/admission/observation/tiny-live/L4 scope |
| Admission-to-registry validator | Ensure accepted admissions produce registry version and RequiredFacts rows | No accepted admission without final-owned asset state |
| Pipeline projection validator | Ensure each active StrategyGroup has one current pipeline state | No duplicate current state per StrategyGroup |
| No repo runtime source validator | Ensure production runtime does not read pipeline MD/JSON as authority | Runtime reads DB/repository/code/API only |
| No authority leakage validator | Ensure pipeline rows cannot set live submit, FinalGate, Operation Layer, exchange write, profile, or sizing authority | Pipeline data remains non-executing |

## Migration Plan

### Phase 0: Record Design Only

Current document status.

Deliverables:

- this design document;
- source-map link from `PROJECT_INFORMATION_ARCHITECTURE.md`;
- no code, migration, output, deploy, or runtime permission changes.

### Phase 1: Finish P0 DB Source Boundary

Deliverables:

- direct runtime file-read freeze;
- RuntimeControlStateRepository;
- Owner policy/current projection DB;
- candidate scope DB;
- runtime coverage and facts DB;
- output export-only path.

This phase can move current five StrategyGroups and supported symbols closer to
the action-time front door without waiting for the full strategy pipeline.

### Phase 2: Seed Existing Strategy Packs Into DB

Deliverables:

- import current active StrategyGroups and archive-only handoff provenance into
  registry/version/RequiredFacts rows when provenance is still useful;
- store evidence refs instead of replay blobs;
- create current pipeline state projection for the five active StrategyGroups;
- keep old handoff packs out of current repo authority; use git-history/archive
  provenance only.

### Phase 3: Add Research Candidate Intake

Deliverables:

- `brc_strategy_research_import_runs`;
- `brc_strategy_research_candidates`;
- `brc_strategy_governance_decisions`;
- import validator;
- promotion-scope validator.

### Phase 4: Connect Admission To Runtime Projection

Deliverables:

- accepted admission creates or updates StrategyGroup registry/version/facts;
- Owner policy and candidate scope must be explicit before `armed_observation`;
- Tradeability and Candidate Pool consume DB/repository state;
- no strategy document is read by production runtime.

### Phase 5: Product And Operations Polish

Deliverables:

- Owner-readable strategy pipeline state;
- strategy governance review surface;
- archive/object-store linkage for large evidence;
- dashboards or exports only after DB state is stable.

## Acceptance Criteria

The design is accepted when these statements are true after implementation.

| Criterion | Required result |
| --- | --- |
| Runtime independence | Production runtime and trading decisions do not depend on repo MD/JSON |
| Strategy pack migration | Archive-only handoff provenance becomes DB rows plus archive refs, not current repo authority |
| One current state | Each active StrategyGroup has one current pipeline state projection |
| Admission traceability | Every admitted trial asset traces back to an import, governance decision, or Owner/system admission record |
| Scope precision | Multi-symbol candidate scope is DB-backed and does not imply live-submit authority |
| Promotion precision | Fresh satisfied candidates may become promotion candidates, but only one real-submit lane can be selected |
| No authority leakage | Pipeline data cannot bypass Runtime Safety State, FinalGate, Operation Layer, protection, account, exchange, or active-position checks |
| Export-only files | JSON/MD pipeline views are generated exports and untracked unless explicitly whitelisted |

## Stop Conditions

Do not continue pipeline implementation if any of these occurs:

| Stop condition | Required action |
| --- | --- |
| P0 DB source boundary is not in place | Continue DB/source-boundary work first |
| Import layer becomes a generic JSONB dump | Normalize tables or reject the import path |
| Pipeline state conflicts with Tradeability Decision | Treat Tradeability as current can-trade read model and repair projection |
| Pipeline tries to set submit authority | Fail closed and remove authority fields |
| Strategy docs remain production runtime inputs | Stop and finish source elimination |
| Owner is asked to operate RequiredFacts or action-time gates manually | Repair product/authority boundary |

## Chain Position

```text
chain_position: strategy_governance_pipeline_design
strategy_group_id: active 5 StrategyGroups plus future admitted candidates
symbol: DB-backed candidate scope, not repo handoff symbol lists
stage: P1 design recorded; P0 DB/source-boundary remains first
first_blocker: strategy governance pipeline is currently file/artifact-shaped, not DB state-machine backed
evidence: current contracts and scripts define partial stages, while DB architecture/table design defines target repository and runtime control tables
next_action: finish RuntimeControlStateRepository and P0 DB source migration before implementing pipeline import/admission tables
stop_condition: production runtime/trading decisions read DB/code/API sources only, and strategy packs are archive/import provenance rather than repo runtime authority
owner_action_required: no
authority_boundary: pipeline design is non-executing and must not call FinalGate, Operation Layer, exchange write, mutate live profile, or mutate order sizing
```
