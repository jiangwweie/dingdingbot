# CLAUDE-DEBT-001 Deletion and Consolidation Map

Generated: 2026-06-16
Branch: codex/owner-runtime-console-v1

---

## Executive Summary

This repository carries significant historical mass across five axes:

1. **Scripts bloat** — 189 Python scripts in `scripts/`, most are one-off proof/packet/verification artifacts from iterative runtime execution pipeline development. At least 60% are candidates for archive or deletion.
2. **Artifact accumulation** — `output/` (175MB), `local-archives/` (469MB), `archive/` (81MB), `reports/` (88MB), `data/` (214MB SQLite) total ~1GB of non-source mass.
3. **Adapter/bridge/packet proliferation** — The domain layer contains 35 `runtime_execution_*` files (12,355 lines) forming a deep chain of thin value objects (packet → enablement → authorization → rehearsal → handoff → adapter → evidence → proof). Many are single-purpose wrappers around the same ExecutionIntent.
4. **Naming drift and semantic duplication** — `intent_local_order_binding` vs `intent_local_order_linkage`, `budgeted_autonomy` vs `budgeted_autonomy_v01`, old SQLite repos vs `pg_*` repos, `config_manager.py` monolith vs `config/` provider package.
5. **Completed migration residue** — Tokyo governance scripts (11 scripts + 10 tests), `first_real_submit` packet scripts (5 top-level + 5 replay_recovery_history duplicates), `phase5*` test modules, `tiny001*` test modules.

The biggest wins come from: (a) archiving the scripts directory's historical artifacts, (b) deleting old SQLite repository files that have `pg_*` replacements, (c) consolidating the intent binding/linkage naming drift, and (d) cleaning up completed migration artifacts.

---

## System-Slimming Principles

1. **Delete what the system no longer imports.** If a file exists but nothing in `src/` or active `scripts/` imports it, it is dead weight.
2. **Archive what was historically valuable but is no longer on the critical path.** Move to `archive/` with a date tag; do not delete git history.
3. **Merge what splits a single concept across two names.** Naming drift creates cognitive load and merge conflicts.
4. **Keep what the current runtime pipeline actually touches.** The Owner supervisor model → admission → observation → signal → FinalGate → Operation Layer → finalize chain is the active spine.
5. **Do not touch Codex-owned core files** unless the task card explicitly allows it.

---

## Candidate Table

| Action | Confidence | File/Area | Current Role | Why It Is Debt | Replacement/Target | Risk | Verification Needed |
|--------|-----------|-----------|--------------|----------------|-------------------|------|-------------------|
| **delete** | HIGH | `src/api_server.py` | Deprecated standalone API server (36 lines, self-declares DEPRECATED) | File says "DEPRECATED" in docstring and logs warning on import | `src/main.py` embeds the API server | None | Confirm no imports exist |
| **delete** | HIGH | `src/infrastructure/backtest_repository.py` | Old SQLite backtest repo | Has `pg_backtest_repository.py` replacement; only imported by archived scripts and `api_research_jobs.py` | `pg_backtest_repository.py` | Low — need to update 2 interface imports | Check `api_research_jobs.py` and `api_console_research.py` |
| **delete** | HIGH | `src/infrastructure/config_entry_repository.py` | Old SQLite config entry repo | Has `pg_config_entry_repository.py` replacement | `pg_config_entry_repository.py` | Low | Check all imports |
| **delete** | HIGH | `src/infrastructure/config_profile_repository.py` | Old SQLite config profile repo | Has `pg_config_profile_repository.py` replacement | `pg_config_profile_repository.py` | Low | Check all imports |
| **delete** | HIGH | `src/infrastructure/config_snapshot_repository.py` | Old SQLite config snapshot repo | Has `pg_config_snapshot_repository.py` replacement | `pg_config_snapshot_repository.py` | Low — `main.py` still references `data/config_snapshots.db` | Update `main.py` |
| **delete** | HIGH | `src/infrastructure/historical_data_repository.py` | Old SQLite historical data repo | Has `pg_historical_data_repository.py` replacement | `pg_historical_data_repository.py` | Low | Check all imports |
| **delete** | HIGH | `src/infrastructure/order_repository.py` | Old SQLite order repo | Has `pg_order_repository.py` replacement; still imported by `core_repository_factory.py` and `startup_reconciliation_service.py` | `pg_order_repository.py` | Medium — 2 active importers | Update `core_repository_factory.py`, `startup_reconciliation_service.py` |
| **delete** | HIGH | `src/infrastructure/reconciliation_repository.py` | Old SQLite reconciliation repo | Has `pg_reconciliation_repository.py` replacement; still imported by `pg_reconciliation_repository.py` itself and `reconciliation.py` | `pg_reconciliation_repository.py` | Medium | Update 2 importers |
| **delete** | HIGH | `src/infrastructure/research_repository.py` | Old SQLite research repo | Has `pg_research_repository.py` replacement; still imported by `api_research_jobs.py` and `research_control_plane.py` | `pg_research_repository.py` | Medium | Update 2 importers |
| **delete** | HIGH | `src/infrastructure/runtime_profile_repository.py` | Old SQLite runtime profile repo | Has `pg_runtime_profile_repository.py` replacement | `pg_runtime_profile_repository.py` | Low | Check all imports |
| **delete** | HIGH | `src/infrastructure/signal_repository.py` | Old SQLite signal repo | Has `pg_signal_repository.py` replacement; still imported by `signal_pipeline.py` | `pg_signal_repository.py` | Medium | Update `signal_pipeline.py` |
| **delete** | HIGH | `src/infrastructure/config_repository_factory.py` | Factory for old SQLite config repos | Superseded by `pg_config_repositories.py` | `pg_config_repositories.py` | Low | Check imports |
| **delete** | HIGH | `src/infrastructure/core_repository_factory.py` | Factory for old SQLite core repos | References old `order_repository.py` | PG-based factory | Medium | Check imports |
| **delete** | HIGH | `src/infrastructure/repositories/config_repositories.py` (2055 lines) | Duplicate config repository implementations | Overlaps with `pg_config_repositories.py` and `config/` provider package | Consolidate into one | Medium | Check which is actually used |
| **delete** | HIGH | `src/infrastructure/v3_orm.py` (1344 lines) | v3.0 SQLAlchemy ORM (old schema) | Header says "v3.0 SQLAlchemy ORM 模型" — likely superseded by `pg_models.py` | `pg_models.py` | Low | Check imports |
| **archive** | HIGH | `scripts/replay_recovery_history/` (13 files) | Historical replay wrappers with `compat_wrapper.py` | Contains exact duplicates of top-level scripts + a generic compat shim | None needed | None | Confirm no active callers |
| **archive** | HIGH | `scripts/build_tokyo_runtime_governance_*.py` (4 files) | Tokyo governance deploy packet builders | Completed migration artifacts | None needed | None | Confirm deploy is done |
| **archive** | HIGH | `scripts/execute_tokyo_runtime_governance_*.py` (2 files) | Tokyo governance deploy executors | Completed migration artifacts | None needed | None | Confirm deploy is done |
| **archive** | HIGH | `scripts/plan_tokyo_runtime_governance_*.py` (2 files) | Tokyo governance deploy planners | Completed migration artifacts | None needed | None | Confirm deploy is done |
| **archive** | HIGH | `scripts/prepare_tokyo_runtime_governance_*.py` (1 file) | Tokyo governance release prep | Completed migration artifact | None needed | None | Confirm deploy is done |
| **archive** | HIGH | `scripts/probe_tokyo_runtime_governance_*.py` (1 file) | Tokyo governance readonly probe | Completed migration artifact | None needed | None | Confirm deploy is done |
| **archive** | HIGH | `scripts/verify_tokyo_runtime_governance_*.py` (1 file) | Tokyo governance postdeploy verify | Completed migration artifact | None needed | None | Confirm deploy is done |
| **archive** | HIGH | `scripts/audit_tokyo_runtime_governance_*.py` (1 file) | Tokyo governance migration gap audit | Completed migration artifact | None needed | None | Confirm deploy is done |
| **archive** | HIGH | `tests/unit/test_tokyo_runtime_governance_*.py` (10 files) | Tests for completed Tokyo migration | Test code for historical migration | None needed | None | Confirm deploy is done |
| **done** | HIGH | `scripts/runtime_controlled_tiny_live_readiness_*.py` (3 files) | Tiny-live readiness proof scripts | Active files renamed from bridge wording to readiness projection / proof evidence | None needed | None | Completed by `SYS-LONG-0084F` |
| **archive** | HIGH | `scripts/runtime_official_*_proof.py` (15 files) | One-off verification proof scripts | Point-in-time proof artifacts, not reusable | None needed | None | Confirm proofs are captured in reports |
| **archive** | HIGH | `scripts/runtime_legacy_compatibility_isolation_packet.py` | Legacy compatibility isolation | Self-declares legacy | None needed | None | Confirm no active callers |
| **archive** | HIGH | `scripts/runtime_*_packet.py` (34 total in scripts/) | Packet builder scripts | One-off packet generation, not runtime code | None needed | None | Check which are still actively invoked |
| **archive** | MEDIUM | `tests/unit/test_phase5*.py` (7 files, 14 entries with dups) | Phase 5 multi-symbol tests | Phase-numbered test modules for completed phase | None needed | None | Confirm phase 5 is complete |
| **archive** | MEDIUM | `tests/unit/test_tiny001*.py` (8 files) | Tiny live trial tests | Testnet trial-specific tests | None needed | None | Confirm trial is complete |
| **archive** | MEDIUM | `output/` (175MB) | Build artifacts, deploy outputs, test outputs | Non-source artifacts accumulate | `.gitignore` | None | Add to .gitignore |
| **archive** | MEDIUM | `local-archives/` (469MB) | Old archive tarballs | Historical snapshots | Move to external storage | None | Verify not referenced |
| **merge** | HIGH | `src/domain/runtime_execution_intent_local_order_binding.py` + `src/domain/runtime_execution_intent_local_order_linkage.py` | Two near-identical domain models for intent-to-order binding | Same docstring purpose, same structure, naming drift (binding vs linkage) | Keep one, delete the other | Medium | Diff the two files, check importers of each |
| **merge** | HIGH | `src/application/budgeted_autonomy.py` (643 lines) + `src/application/budgeted_autonomy_v01.py` (262 lines) | v01 imports from and extends the original | v01 is a thin wrapper; original is the real logic | Fold v01 additions into original | Low | Check which is imported where |
| **merge** | MEDIUM | `src/application/config_manager.py` (2051 lines) + `src/application/config/` package (2020 lines) | Two config systems coexist | Old monolith + new provider pattern | Migrate all callers to `config/` package, delete `config_manager.py` | High — widely imported | Map all `config_manager` importers |
| **merge** | MEDIUM | `src/infrastructure/config_entry_repository.py` + `src/infrastructure/pg_config_entry_repository.py` + `src/infrastructure/repositories/config_repositories.py` | Three config repository implementations | Old SQLite + PG + "repositories" package | Keep only `pg_config_entry_repository.py` | Medium | Verify no active callers of old |
| **rename** | MEDIUM | `src/infrastructure/hybrid_signal_repository.py` | Hybrid signal repo (SQLite + PG?) | Name unclear; "hybrid" implies transitional | Clarify: is this active? If so, document; if not, delete | Low | Check imports |
| **keep** | HIGH | `src/application/brc_operation_layer.py` (6843 lines) | Core Operation Layer | Active spine of the runtime pipeline | N/A | N/A | N/A |
| **keep** | HIGH | `src/application/brc_admission_service.py` (5826 lines) | Core admission service | Active spine | N/A | N/A | N/A |
| **keep** | HIGH | `src/application/execution_orchestrator.py` | Core execution orchestrator | Codex-owned core file | N/A | N/A | N/A |
| **keep** | HIGH | `src/domain/runtime_execution_*` (active subset) | Runtime execution domain models | Active pipeline models | N/A | N/A | N/A |
| **keep** | MEDIUM | `src/application/llm_advisory_*` (6 files, 1794 lines) | LLM advisory plane | Experimental but coherent subsystem | N/A | N/A | Confirm active usage |
| **keep** | MEDIUM | `src/application/personal_campaign_*` (4 files, 1439 lines) | Personal campaign sandbox | Paper observation / promotion gate | N/A | N/A | Confirm active usage |
| **keep** | MEDIUM | `src/application/cpm_*` (2 app + 5 domain, 2192 lines) | Campaign Performance Model | Historical evaluator / replay / stress | N/A | N/A | Confirm active usage |
| **keep** | MEDIUM | `src/application/strategy_trial_*` (5 files, 2713 lines) | Strategy trial governance | Active trial path | N/A | N/A | Confirm active usage |
| **keep** | MEDIUM | `src/application/mi001_*` (4 files, 2857 lines) | MI-001 trial migration | Active trial path | N/A | N/A | Confirm active usage |
| **keep** | LOW | `trading-console/` | Old frontend (predecessor to owner-runtime-console) | May still serve a purpose | N/A | N/A | Clarify relationship |
| **keep** | LOW | `design-system/brc-owner-console/` (3 files, 24KB) | Design system tokens | Small, may be referenced by owner-runtime-console | N/A | N/A | Check if referenced |
| **keep** | LOW | `docker/` | Docker compose for local dev | Active dev infrastructure | N/A | N/A | N/A |
| **keep** | LOW | `deploy/systemd/` | Systemd units for signal watcher | Active deploy config | N/A | N/A | N/A |

---

## Glue Layer Hotspots

### 1. `runtime_execution_*` Adapter Chain (domain: 35 files, 12,355 lines)

The domain layer contains an extremely deep chain of thin value objects that model every micro-step of the execution pipeline:

```
ExecutionIntent
  → intent_adapter (257 lines)
  → intent_local_order_binding (248 lines)
  → intent_local_order_linkage (248 lines)   ← DUPLICATE
  → order_lifecycle_adapter (248 lines)
  → order_lifecycle_adapter_result (495 lines)
  → order_lifecycle_handoff (417 lines)
  → order_registration_draft (270 lines)
  → submit_adapter (241 lines)
  → submit_authorization (265 lines)
  → submit_idempotency (280 lines)
  → submit_rehearsal (666 lines)
  → submit_outcome_review (664 lines)
  → submit_prerequisite_evidence_proof (567 lines)
  → controlled_submit (372 lines)
  → exchange_submit_enablement (474 lines)
  → exchange_submit_packet (432 lines)
  → exchange_submit_adapter_result (420 lines)
  → exchange_submit_action_authorization (365 lines)
  → exchange_submit_execution_result (576 lines)
  → exchange_submit_recovery_resolution (319 lines)
  → first_real_submit_enablement_packet (353 lines)
  → first_real_submit_evidence_preparation (282 lines)
  → first_real_submit_outcome_accounting (287 lines)
  → local_registration_enablement (282 lines)
  → local_registration_gate (219 lines)
  → local_registration_action_authorization (364 lines)
  → attempt_mutation (280 lines)
  → attempt_outcome_policy (406 lines)
  → attempt_reservation (361 lines)
  → post_submit_budget_settlement (418 lines)
  → protection_plan (283 lines)
  → protection_failure_policy (253 lines)
  → exchange_gateway_readiness (265 lines)
  → duplicate_submit_replay_proof (431 lines)
```

Each file is a Pydantic model with 1-3 enums, a result class, and sometimes a builder function. Many have overlapping concerns (e.g., `submit_adapter` vs `exchange_submit_adapter_result`, `submit_authorization` vs `exchange_submit_action_authorization`).

**Recommendation:** Codex should evaluate whether this chain can be collapsed from ~35 files to ~15 by merging closely related steps (e.g., all "submit authorization" variants into one module).

### 2. `runtime_*_service.py` Application Layer (30+ files)

The application layer mirrors the domain chain with service wrappers:

```
runtime_execution_intent_adapter_service.py
runtime_fresh_submit_authorization_binding_service.py
runtime_fresh_submit_authorization_resolution_service.py
runtime_official_submit_handoff_service.py
runtime_persisted_draft_source_readiness_bridge_service.py
runtime_execution_first_real_submit_enablement_packet_service.py
runtime_execution_first_real_submit_evidence_preparation_service.py
runtime_executable_submit_readiness_service.py
runtime_exchange_gateway_readiness_service.py
runtime_exchange_close_projection_recovery_service.py
runtime_exchange_submit_projection_recovery_service.py
runtime_post_submit_finalize_service.py
runtime_strategy_signal_evaluation_service.py
runtime_strategy_signal_intent_draft_source_service.py
runtime_strategy_signal_planning_service.py
runtime_strategy_signal_scheduler_assembly.py
runtime_strategy_signal_scheduler_planning_service.py
runtime_closed_trade_lifecycle_review_service.py
runtime_closed_trade_review_facts_service.py
runtime_next_attempt_strategy_planning_service.py
runtime_live_position_monitor_service.py
runtime_position_exit_plan_service.py
runtime_final_gate_preview_service.py
runtime_symbol_isolation_audit.py
...
```

Many of these are thin wrappers that call one domain function and return the result. The "bridge" in `runtime_persisted_draft_source_readiness_bridge_service.py` is a telltale glue-layer name.

### 3. Old Repository → PG Repository Shadow Layer

9 old SQLite repository files coexist with their `pg_*` replacements. The old ones are still imported by active code (`core_repository_factory.py`, `startup_reconciliation_service.py`, `signal_pipeline.py`, `reconciliation.py`, `research_control_plane.py`, interface modules). This creates a dual-path risk where code may accidentally write to SQLite instead of PG.

### 4. `config_manager.py` vs `config/` Package

`config_manager.py` (2051 lines) is the old monolithic config system. `config/` (2020 lines across 7 files) is the new provider-based pattern. Both are imported by active code. This is the highest-risk consolidation target because config is imported everywhere.

---

## Semantic Drift Hotspots

### 1. `binding` vs `linkage` — Intent-to-Order Mapping

- `runtime_execution_intent_local_order_binding.py` (248 lines)
- `runtime_execution_intent_local_order_linkage.py` (248 lines)

Both have near-identical docstrings: "explicit boundary after local CREATED-order registration and before exchange submit." Both import the same dependencies. This is classic naming drift from iterative development.

### 2. `adapter` vs `adapter_result` — Submit Adaptation

- `runtime_execution_submit_adapter.py` (241 lines)
- `runtime_execution_exchange_submit_adapter_result.py` (420 lines)
- `runtime_execution_order_lifecycle_adapter.py` (248 lines)
- `runtime_execution_order_lifecycle_adapter_result.py` (495 lines)

Four files for two adapter concepts, each split into "adapter" and "adapter_result."

### 3. `authorization` Proliferation

At least 7 distinct "authorization" domain models:
- `runtime_execution_submit_authorization.py`
- `runtime_execution_exchange_submit_action_authorization.py`
- `runtime_execution_local_registration_action_authorization.py`
- `runtime_fresh_submit_authorization_binding.py`
- `runtime_fresh_submit_authorization_resolution.py`
- `runtime_reduce_only_close_authorization.py`
- `standing_authorization.py`

The first four are all about "can we submit?" but modeled as separate types.

### 4. `enablement` vs `readiness` vs `gate`

Three near-synonyms used as distinct concepts:
- `runtime_execution_exchange_submit_enablement.py` (474 lines)
- `runtime_execution_local_registration_enablement.py` (282 lines)
- `runtime_executable_submit_readiness.py` (354 lines)
- `runtime_execution_exchange_gateway_readiness.py` (265 lines)
- `runtime_execution_local_registration_gate.py` (219 lines)

### 5. `operator` vs `supervisor` vs `owner`

Three roles overlap in the codebase:
- `brc_operator_workflow.py` — operator workflow
- `operator_auth.py` — operator authentication
- `owner_bounded_execution.py` — owner execution
- `owner_action_carrier_catalog.py` — owner carrier catalog
- `runtime_active_observation_supervisor.py` — supervisor script
- `runtime_live_signal_operator_supervisor.py` — operator supervisor script

The OWNER_RUNTIME_OPERATING_MODEL.md clarifies the current model is "Owner supervisor," making "operator" naming legacy.

### 6. `packet` vs `evidence` vs `proof`

Three terms for "a structured data bundle that proves something":
- 34 scripts have "packet" in their name
- Domain files use "evidence" (`submit_prerequisite_evidence_proof.py`, `first_real_submit_evidence_preparation.py`)
- 15 scripts have "proof" in their name

---

## Duplicate Concepts / Redundant States

### 1. `budgeted_autonomy.py` + `budgeted_autonomy_v01.py`

`budgeted_autonomy_v01.py` (262 lines) imports everything from `budgeted_autonomy.py` (643 lines) and adds a thin `BudgetedAutonomyDailyState` extension. The "v01" suffix is a version marker that should have been folded in.

### 2. `runtime_execution_intent_local_order_binding` = `runtime_execution_intent_local_order_linkage`

As noted above — two files modeling the same concept with different names.

### 3. Old SQLite repos vs `pg_*` repos

9 old files with `pg_*` replacements:
- `backtest_repository.py` → `pg_backtest_repository.py`
- `config_entry_repository.py` → `pg_config_entry_repository.py`
- `config_profile_repository.py` → `pg_config_profile_repository.py`
- `config_snapshot_repository.py` → `pg_config_snapshot_repository.py`
- `historical_data_repository.py` → `pg_historical_data_repository.py`
- `order_repository.py` → `pg_order_repository.py`
- `reconciliation_repository.py` → `pg_reconciliation_repository.py`
- `research_repository.py` → `pg_research_repository.py`
- `runtime_profile_repository.py` → `pg_runtime_profile_repository.py`

### 4. `first_real_submit` Scripts — Top-Level + Replay Duplicates

5 scripts exist in both `scripts/` and `scripts/replay_recovery_history/first_real_submit/`:
- `build_runtime_first_real_submit_action_authorization_packet.py`
- `build_runtime_first_real_submit_exchange_arm_authorization_packet.py`
- `build_runtime_first_real_submit_final_review_packet.py`
- `build_runtime_first_real_submit_local_registration_authorization_packet.py`
- `build_runtime_first_real_submit_owner_packet.py`

### 5. `trading-console/` vs `owner-runtime-console/`

Two frontend directories coexist. `trading-console/` appears to be the predecessor; `owner-runtime-console/` is the current Owner Console. If `trading-console` is fully superseded, it should be archived.

### 6. `config_manager.py` (2051 lines) vs `config/` package (2020 lines)

~4000 lines of config code when ~2000 would suffice.

---

## Safe First Cuts

These can be done with high confidence and low risk:

1. **Delete `src/api_server.py`** — Self-declares deprecated, 36 lines, logs error on import.
2. **Delete `src/infrastructure/v3_orm.py`** — Old v3.0 ORM, superseded by `pg_models.py`. Verify no imports first.
3. **Archive `scripts/replay_recovery_history/`** — 13 files of historical replay wrappers. Contains a generic `compat_wrapper.py` that re-exports archived modules.
4. **Archive all `scripts/*tokyo_runtime_governance*`** — 11 scripts for a completed migration.
5. **Archive all `tests/unit/test_tokyo_runtime_governance_*`** — 10 test files for completed migration.
6. **Archive `scripts/runtime_legacy_compatibility_isolation_packet.py`** + its test — Self-declares legacy.
7. **Done: rename `scripts/runtime_controlled_tiny_live_bridge_*.py`** — 3 tiny-live proof scripts now use readiness projection names.
8. **Delete duplicate `first_real_submit` scripts** in `scripts/replay_recovery_history/first_real_submit/` (keep top-level copies).
9. **Add `output/`, `local-archives/`, `data/*.db`, `logs/` to `.gitignore`** if not already there.
10. **Delete empty `tasks/` directory** (0 bytes).

---

## Dangerous Cuts Requiring Codex Ownership

These changes touch active code paths or Codex-owned files:

1. **Old SQLite repository deletion** — Requires updating all importers (`core_repository_factory.py`, `startup_reconciliation_service.py`, `signal_pipeline.py`, `reconciliation.py`, `research_control_plane.py`, `api_research_jobs.py`, `main.py`). Each import must be redirected to the `pg_*` equivalent. **This is the highest-value consolidation** but touches Codex-owned files (`startup_reconciliation_service.py`, `reconciliation.py`).

2. **`config_manager.py` → `config/` migration** — `config_manager.py` (2051 lines) is imported throughout the codebase. Migrating all callers to the `config/` package is a large refactor. Must be done incrementally with import redirection.

3. **`runtime_execution_*` domain chain consolidation** — Collapsing 35 files to ~15 requires deep understanding of which steps are truly independent vs which are artificial splits. This is an architecture decision.

4. **`runtime_execution_intent_local_order_binding` vs `linkage` merge** — Need to diff the two files and determine which importers use which. May require updating domain and application layers simultaneously.

5. **`budgeted_autonomy` + `budgeted_autonomy_v01` merge** — Need to verify all callers of `v01` and ensure the merged version preserves the extension.

6. **`trading-console/` archival** — Need to confirm no active users or references. May still serve as a reference for the Owner Console rebuild.

---

## Suggested Cleanup Waves

### Wave 1: Safe Deletions and Archives (No Code Changes)
**Effort:** 1 hour
**Risk:** Near zero

- Delete `src/api_server.py`
- Archive `scripts/replay_recovery_history/`
- Archive all 11 `*tokyo_runtime_governance*` scripts + 10 tests
- Archive `scripts/runtime_legacy_compatibility_isolation_packet.py` + test
- Done: renamed `scripts/runtime_controlled_tiny_live_bridge_*.py` to readiness projection/proof entrypoints
- Archive 15 `scripts/runtime_official_*_proof.py` files
- Archive `scripts/runtime_*_packet.py` (34 files) — verify which are still active first
- Delete empty `tasks/` directory
- Add artifact directories to `.gitignore`

### Wave 2: Old Repository Cleanup (Import Redirects)
**Effort:** 2-4 hours
**Risk:** Low-medium (test suite validates)

- Delete 9 old SQLite repository files
- Update all importers to use `pg_*` equivalents
- Delete `config_repository_factory.py` and `core_repository_factory.py`
- Delete `v3_orm.py`
- Run full test suite

### Wave 3: Naming Drift Consolidation
**Effort:** 2-3 hours
**Risk:** Medium

- Merge `intent_local_order_binding` and `intent_local_order_linkage` (pick one name)
- Merge `budgeted_autonomy_v01` into `budgeted_autonomy`
- Rename `operator_auth.py` → `owner_auth.py` if the operator model is retired

### Wave 4: Config System Unification
**Effort:** 4-8 hours
**Risk:** High (config is imported everywhere)

- Migrate all `config_manager.py` callers to `config/` package
- Delete `config_manager.py` (2051 lines)
- Delete `config_profile_service.py` and `config_snapshot_service.py` if subsumed

### Wave 5: Domain Chain Rationalization
**Effort:** 8-16 hours
**Risk:** High (architecture decision)

- Codex evaluates the 35-file `runtime_execution_*` chain
- Merge closely related models (e.g., all authorization variants, all adapter+result pairs)
- Target: ~15 domain files replacing 35

### Wave 6: Artifact Cleanup
**Effort:** 1 hour
**Risk:** None (external storage)

- Move `local-archives/` (469MB) to external storage
- Move old `reports/` to external storage
- Clean `output/` build artifacts
- Archive or delete old SQLite databases in `data/`

---

## Appendix: File Counts by Category

| Category | Files | Lines (approx) |
|----------|-------|----------------|
| `src/application/` | 136 | ~60,000 |
| `src/domain/` | 114 | ~35,000 |
| `src/infrastructure/` | 91 | ~25,000 |
| `src/interfaces/` | 12 | ~22,000 |
| `scripts/` | 189 | ~30,000 (est) |
| `tests/unit/` | 297 | ~112,000 |
| `archive/` (Python) | 420 | ~81MB total |
| `output/` | — | 175MB |
| `local-archives/` | — | 469MB |
| `reports/` | — | 88MB |
| `data/` (SQLite) | 20+ | 214MB |

Total non-source mass: ~940MB
