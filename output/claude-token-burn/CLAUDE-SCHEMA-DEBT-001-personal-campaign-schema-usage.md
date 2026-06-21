# CLAUDE-SCHEMA-DEBT-001 Personal Campaign Schema Usage

**Date:** 2026-06-16
**Scope:** `docs/schemas/personal_campaign/` (11 schemas + 10 examples)
**Task type:** Read-only scan, no file modifications

---

## Summary

All 11 schemas have corresponding Pydantic domain models in `src/domain/personal_campaign.py`. None are referenced by `docs/current/` or `scripts/`. Two dedicated test files (`test_personal_campaign_schema_docs.py`, `test_personal_campaign_schema_examples.py`) validate schema structure and example parsing.

**Key finding:** `read_only_runtime_adapter_preview` has zero runtime application references — only tests touch it. `paper_observation_packet` is the sole schema using the "packet" terminology flagged by CLAUDE-DOC-DEBT-001. All other schemas are actively used in runtime code paths.

No schemas are orphaned from the domain layer. The schemas are documentation/validation artifacts, not runtime dependencies — the codebase uses Pydantic models, not JSON Schema validation at runtime.

---

## Schema Usage Table

| Schema | Referenced By (runtime) | Referenced By (tests) | Runtime Relevance | Owner Surface Risk | Recommendation | Evidence |
|--------|------------------------|----------------------|-------------------|-------------------|----------------|----------|
| `campaign_state.schema.json` | execution_orchestrator, campaign_state_service, runtime_context, pg_models, trading_console readmodels, API endpoints (4 files) | schema_docs, schema_examples, p4_campaign_state, plc_state_runtime_event_wiring, trading_console_readmodels, brc_operation_layer, personal_campaign_sandbox, gks_v0, brc_controlled_testnet | **HIGH** — core runtime state | None — active runtime surface | **KEEP** | `src/application/campaign_state_service.py`, `src/application/execution_orchestrator.py`, `src/interfaces/api_console_runtime.py` |
| `strategy_contract.schema.json` | execution_orchestrator, campaign_state_service, promotion_gate, pattern_strategy_signal_adapter, repository_ports, pg_models, pg_campaign_state_repository, strategy_semantics, bounded_risk_campaign, API endpoints (10+ files) | schema_docs, schema_examples, promotion_gate, runtime_adapter, paper_observation, strategy_contract_v2_models, pattern_strategy_signal_adapter, gks_v0, p4_campaign_state, brc_controlled_testnet, personal_campaign_sandbox | **HIGH** — core governance contract | None — enforces disabled_by_default boundary | **KEEP** | `src/application/execution_orchestrator.py`, `src/domain/bounded_risk_campaign.py` |
| `trade_intent.schema.json` | brc_admission, brc_operation_layer, brc_live_read_only_detection, promotion_gate, bounded_risk_campaign, production_strategy_family_admission, pg_models, pg_brc_admission_repository, API endpoints (8+ files) | schema_docs, schema_examples, brc_admission_phase1, brc_operation_layer, brc_console_api_surface, brc_live_read_only_detection, execution_permission, promotion_gate, runtime_adapter, paper_observation, trading_console_readmodels, cpm_* (6 files), sol_high_convexity, strategy_family_registry, historical_research_sampling, production_strategy_family_admission, personal_campaign_sandbox | **HIGH** — core admission signal | None — enforces no_exchange_side_effect | **KEEP** | `src/application/brc_admission_service.py`, `src/domain/brc_admission.py` |
| `feature_snapshot.schema.json` | strategy_candidate_semantics, strategy_candidate_semantics_builders, runtime_adapter, personal_campaign_sandbox (4 files) | schema_docs, schema_examples, promotion_gate, runtime_adapter, paper_observation, strategy_candidate_semantics, personal_campaign_sandbox | **HIGH** — candidate evidence input | None — enforces closed_or_prior boundary | **KEEP** | `src/domain/strategy_candidate_semantics.py`, `src/application/personal_campaign_runtime_adapter.py` |
| `paper_observation_packet.schema.json` | personal_campaign_paper_observation (1 file) | schema_docs, schema_examples, promotion_gate, paper_observation | **MODERATE** — paper observation path | **MEDIUM** — uses "packet" terminology (CLAUDE-DOC-DEBT-001 flag) | **KEEP + RENAME** | `src/application/personal_campaign_paper_observation.py` — active module, but naming should be reviewed |
| `mode_advice.schema.json` | personal_campaign_sandbox (1 file) | schema_docs, schema_examples, personal_campaign_sandbox | **LOW** — sandbox-only advisory | None | **KEEP** (sandbox path still active) | `src/application/personal_campaign_sandbox.py` |
| `human_arm_decision.schema.json` | personal_campaign_sandbox (1 file) | schema_docs, schema_examples, personal_campaign_sandbox | **LOW** — sandbox-only arming | None | **KEEP** (sandbox path still active) | `src/application/personal_campaign_sandbox.py` |
| `risk_order_plan.schema.json` | personal_campaign_sandbox (1 file) | schema_docs, schema_examples, personal_campaign_sandbox | **LOW** — sandbox-only plan | None | **KEEP** (sandbox path still active) | `src/application/personal_campaign_sandbox.py` |
| `execution_receipt.schema.json` | personal_campaign_sandbox (1 file) | schema_docs, personal_campaign_sandbox | **LOW** — sandbox-only receipt | None | **KEEP** (sandbox path still active) | `src/application/personal_campaign_sandbox.py` |
| `position_lifecycle_state.schema.json` | personal_campaign_sandbox (1 file) | schema_docs, personal_campaign_sandbox | **LOW** — sandbox-only lifecycle | None | **KEEP** (sandbox path still active) | `src/application/personal_campaign_sandbox.py` |
| `read_only_runtime_adapter_preview.schema.json` | **NONE** | schema_docs, schema_examples only | **NONE** — zero runtime refs | **LOW** — dead schema, tests validate constraints that no runtime code enforces | **DEFER → ARCHIVE** | No files in `src/application/`, `src/domain/`, `src/interfaces/`, or `src/infrastructure/` reference it |

---

## Safe Archive Candidates

### 1. `read_only_runtime_adapter_preview.schema.json` + example

**Rationale:** Zero runtime application references. Only two test files touch it (`test_personal_campaign_schema_docs.py` line 62, `test_personal_campaign_schema_examples.py` line 109). The domain model class exists in `personal_campaign.py` but is never imported by any runtime module.

**Risk:** The schema enforces `read_only=True`, `authority=read_only_no_order_authority`, and forbids `order_id`/`exchange_order_id`. These constraints are meaningful but untested at runtime — archiving the schema makes this gap visible.

**Action:** Archive to `docs/schemas/_archived/`. Update the two test files to skip or mark as archived. Flag that `ReadOnlyRuntimeAdapterPreview` domain model may also be dead code.

---

## Keep Candidates

### All schemas except `read_only_runtime_adapter_preview`

**Rationale:** Every other schema has at least one runtime application module that imports and uses the corresponding domain model. The schemas serve as documentation artifacts that constrain the Pydantic models' shape. Even the low-relevance sandbox schemas (`mode_advice`, `human_arm_decision`, `risk_order_plan`, `execution_receipt`, `position_lifecycle_state`) are actively used by `personal_campaign_sandbox.py`.

### Special case: `paper_observation_packet`

**Keep, but flag for rename.** This is the only schema using the "packet" terminology that CLAUDE-DOC-DEBT-001 flagged. The runtime module `personal_campaign_paper_observation.py` actively uses `PaperObservationPacket`. A rename would cascade to domain model, schema, tests, and runtime modules — defer to a dedicated cleanup task.

---

## Unknowns

1. **`ReadOnlyRuntimeAdapterPreview` domain model liveness:** The class exists in `personal_campaign.py` but no runtime module imports it. Need to confirm whether this is intentionally reserved for future use or dead code. If dead, the domain model should be archived alongside the schema.

2. **Sandbox path viability:** Five schemas (`mode_advice`, `human_arm_decision`, `risk_order_plan`, `execution_receipt`, `position_lifecycle_state`) are only used by `personal_campaign_sandbox.py`. If the sandbox path is deprecated in favor of the BRC admission flow, these schemas become archive candidates. Need confirmation from Codex on sandbox status.

3. **Schema-to-model drift risk:** The schemas are static JSON files validated by tests, but the Pydantic models may have evolved fields not reflected in the schemas. No runtime code validates payloads against these JSON schemas — they are documentation-only. Consider whether schema validation should be added to test fixtures or removed entirely.

---

## Suggested Cleanup Waves

### Wave 1: Low-risk archive (1 schema)
- Archive `read_only_runtime_adapter_preview.schema.json` + example
- Update `test_personal_campaign_schema_docs.py` and `test_personal_campaign_schema_examples.py`
- Verify `ReadOnlyRuntimeAdapterPreview` domain model is also dead

### Wave 2: Packet terminology cleanup (1 schema, deferred)
- Rename `paper_observation_packet` → `paper_observation` (schema + domain model + tests + runtime modules)
- Cascading rename across ~6 files
- Requires Codex approval due to domain model mutation

### Wave 3: Sandbox schema consolidation (5 schemas, conditional)
- If sandbox path is deprecated: archive `mode_advice`, `human_arm_decision`, `risk_order_plan`, `execution_receipt`, `position_lifecycle_state`
- If sandbox path is active: keep as-is
- Blocked on Codex confirmation of sandbox status

### Wave 4: Schema-model drift audit (all schemas)
- Compare each schema's `properties` against the corresponding Pydantic model's fields
- Flag any fields added to the model but missing from the schema
- This is a documentation hygiene task, not a runtime risk
