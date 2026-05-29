# PG-backed Trial Config Mapping Result

Generated: 2026-05-29

Scope: map `MI-001 SOL/USDT:USDT long` strategy family, candidate, Owner decision, risk boundary, and bounded trial configuration toward PG-backed source of truth.

This report is a review artifact only. It is not runtime configuration, not admission source of truth, not trial-start authorization, and not a replacement for PG records.

## 1. Summary

This task inspected the current BRC PG-backed registry, admission, operation, evidence, account facts, and historical research structures to decide whether `MI-001 SOL/USDT:USDT long` can move from Markdown review material into PG-backed source-of-truth records.

No trial was started. No exchange was connected. No real account API was called. No order was created. No execution intent was created. No execution permission was modified. No migration was run. No runtime or live runner was started.

Conclusion: current PG structures are sufficient to define a minimal mapping, but the MI-001 PG record chain is not yet materialized. The safe next step is to register MI-001 SOL long into existing PG strategy/admission records and keep Markdown files as review artifacts only.

## 2. Path Chosen

Path B: existing PG structures are partially sufficient, but not suitable for immediate trial-config writes in this task.

Reasons:

- `brc_strategy_family_registry` and `brc_strategy_family_playbooks` can carry MI-001 metadata, hypothesis, symbol universe, signal input requirements, review metrics, and evidence requirements.
- BRC admission tables can carry candidate admission request, evidence packet, owner acceptance, trial constraint snapshot, admission decision, and planned trial binding.
- Operation Layer tables can carry preflight/audit/result facts, but should not become the trial-config source of truth.
- Historical signal evaluation tables can carry compact evidence and Owner reports, but are research evidence, not trial authorization.
- Trial risk policy such as `max_leverage=5`, `max_attempts=3`, dedicated subaccount risk capital, max loss, and max notional should be stored in admission constraint snapshots / risk policy snapshots, not in strategy registry metadata.
- Current MI-001 Owner acceptance and bounded trial plan exist as Markdown review artifacts. Treating them as runtime source of truth would violate the Owner correction.
- No schema migration should be added here without a separate decision on whether existing `brc_trial_constraint_snapshots` is the canonical trial config record or a smaller dedicated trial config table is needed later.

## 3. Existing PG Structures Found

| area | existing_structure | files | can_reuse | gaps |
| --- | --- | --- | --- | --- |
| Strategy Family Registry | `brc_strategy_family_registry`, `brc_strategy_family_playbooks` | `src/domain/strategy_family_registry.py`, `src/infrastructure/pg_strategy_family_registry_repository.py`, `src/infrastructure/pg_models.py`, `migrations/versions/2026-05-28-022_create_strategy_family_registry.py` | yes | Metadata-only. It rejects execution/order fields such as leverage, notional, quantity, venue, order type. It can register MI-001, but cannot store trial risk policy. |
| Admission / Candidate | `brc_strategy_families`, `brc_strategy_family_versions`, `brc_admission_requests`, `brc_admission_decisions`, `brc_admission_trial_bindings` | `src/domain/brc_admission.py`, `src/infrastructure/pg_brc_admission_repository.py`, `src/application/brc_admission_service.py`, `src/infrastructure/pg_models.py`, migrations `018`, `019`, `020` | yes | MI-001 SOL long has no confirmed PG record chain yet. Existing repository is mostly create/fetch oriented, so an idempotent MI-001 registration task should be explicit. |
| Owner Decision / Review | `brc_owner_risk_acceptances`, `brc_review_decisions` | `src/domain/brc_admission.py`, `src/infrastructure/pg_brc_admission_repository.py`, `src/infrastructure/pg_models.py`, migrations `014`, `018` | yes | Markdown Owner acceptance is not PG source of truth. Owner approval for plan preparation should become a PG owner risk acceptance/review fact tied to admission request and constraints. Trial start still needs a separate Owner approval. |
| Operation Audit | `brc_operations`, `brc_preflight_snapshots`, `brc_execution_results` | `src/application/brc_operation_layer.py`, `src/infrastructure/pg_brc_operation_repository.py`, `src/infrastructure/pg_models.py`, migration `017` | partial | Suitable for gate/preflight/audit facts. It should not be used as the canonical strategy/trial config store. |
| Evidence / Historical Signal Evaluation | `brc_admission_evidence_packets`, `brc_historical_signal_evaluation_runs`, `brc_historical_signal_outputs`, `brc_historical_forward_outcomes`, `brc_historical_regime_split_reports` | `src/domain/historical_signal_evaluation.py`, `src/infrastructure/pg_historical_signal_evaluation_repository.py`, `src/infrastructure/pg_models.py`, migrations `025`, `026`, `027` | yes | Broad smoke Markdown evidence should be pinned as compact PG evidence or linked to an existing PG historical run before it becomes admission evidence. |
| Trial Intent / Would-trade Evidence | `brc_trial_trade_intents` | `src/domain/brc_admission.py`, `src/infrastructure/pg_brc_admission_repository.py`, `src/infrastructure/pg_models.py`, migration `021` | no for trial config | Evidence ledger only. Rows are explicitly not orders and must not feed execution. Do not use this table to store trial config. |
| Account Facts | admission `account_facts_snapshot_ref/json`, Owner Console cached `AccountSnapshot` mapping | `src/interfaces/api_brc_console.py`, `src/application/brc_admission_risk_capital.py`, `src/domain/strategy_family_signal.py` | yes, with freshness checks | Account equity can be mapped from cached `AccountSnapshot.total_balance`; available margin from cached `AccountSnapshot.available_balance`. Trial checklist must verify freshness, source, truth level, and reconciliation before use. |
| Config / Runtime Profile | BRC admission rule configs and runtime/profile structures | `src/infrastructure/pg_models.py`, `src/application/brc_admission_risk_capital.py`, runtime files inspected by search only | limited | Do not change runtime profiles for this task. Runtime config is not the source of truth for MI-001 trial admission. |

## 4. Mapping Decision

| concept | recommended_pg_source_of_truth | mapping_status | notes |
| --- | --- | --- | --- |
| MI-001 strategy family | `brc_strategy_family_registry` plus admission `brc_strategy_families` / `brc_strategy_family_versions` | needs PG registration | Use registry for metadata and admission family/version for admission flow. Do not store risk/leverage in registry. |
| MI-001 SOL long candidate | `brc_admission_requests` with evidence packet and family version; side/symbol in constraints/risk intent | needs PG registration | Candidate should be pinned as SOL/USDT:USDT long only. Registry can carry symbol universe, but side belongs in candidate/admission constraints. |
| broad smoke evidence summary | `brc_admission_evidence_packets.payload_json` and optionally historical signal evaluation owner report refs | needs PG evidence pinning | Markdown evidence remains a review artifact until compact evidence is pinned to PG. |
| Owner approval | `brc_owner_risk_acceptances` and/or `brc_review_decisions` | needs owner decision PG mapping | Current Markdown approval is not source of truth. It should become a PG acceptance fact for plan preparation, not trial start. |
| bounded trial plan prepared | `brc_admission_trial_bindings.binding_status = planned` or `binding_reserved`, tied to an admission decision and constraint snapshot | needs trial config PG record | Planned/binding-reserved states already prevent campaign/runtime implication. |
| dedicated subaccount policy | `brc_trial_constraint_snapshots.risk_policy_snapshot_json` and `constraints_json` | mapping planned | Policy should state capital source is dedicated subaccount and `trial_risk_capital = current_subaccount_equity`. |
| max leverage 5x | `brc_trial_constraint_snapshots.constraints_json.max_leverage` | mapping planned | Do not put this in strategy registry or playbook parameter profile because registry rejects execution fields. |
| max attempts 3 | `brc_trial_constraint_snapshots.constraints_json.max_attempts` | mapping planned | Admission risk/capital adapter already expects concrete `max_attempts`. |
| allowed symbol / side | `constraints_json.allowed_symbols`, `risk_intent_json.allowed_side`, admission request metadata | mapping planned | Must be `SOL/USDT:USDT` and `long` only. |
| no expansion rules | `constraints_json`, `risk_policy_snapshot_json`, `risk_disclosure_json`, and planned binding audit metadata | mapping planned | Include no auto top-up, no transfer, no withdrawal, no symbol expansion, no side expansion, no leverage expansion beyond 5x, no Operation Layer bypass. |
| account equity source | `AdmissionRequest.account_facts_snapshot_json` derived from cached `AccountSnapshot.total_balance` | partially ready | Existing account equity mapping is read-only/cache-only. Checklist must require fresh cached facts. |
| available margin source | `AdmissionRequest.account_facts_snapshot_json` derived from cached `AccountSnapshot.available_balance` | partially ready | Used only as a cap input: `available_margin * 5` if available. |
| max total loss rule | `constraints_json.max_loss_budget` plus `risk_policy_snapshot_json.max_total_loss_rule` | mapping planned | For the new policy, max loss equals current dedicated subaccount equity. |
| max notional rule | `constraints_json.max_notional` plus explanatory `risk_policy_snapshot_json.max_notional_rule` | mapping planned | `min(current_subaccount_equity * 5, available_margin * 5 if available, Operation Layer cap if exists)`. |
| operation layer gate required | `constraints_json.review_requirements` and Operation Layer preflight facts | mapping planned | Gate required before trial start. It does not grant execution permission. |
| kill switch required | `constraints_json.safeguards` / `risk_disclosure_json` and Operation Layer readiness | mapping planned | Checklist must prove availability before trial start approval. |
| trial start approval | separate PG Owner approval / Operation Layer operation | not ready | Owner acceptance for plan preparation must not imply trial start. |

## 5. Implementation Summary

This task produced a mapping/readiness report only.

Changed files:

- `reports/directional-opportunity-broad-smoke-20260529/pg_backed_trial_config_mapping_result.md`

No Python code was changed. No migration was added. No PG write command was run.

Why no immediate PG write:

- The existing PG schema can carry the mapping, but MI-001 does not yet have a canonical, idempotent registration path that creates registry metadata, admission family/version, evidence packet, Owner acceptance, trial constraint snapshot, admission decision, and planned binding together.
- The registry domain intentionally rejects forbidden execution/order fields. Trial risk fields such as max leverage, max notional, max loss, side, and expansion rules must be placed in admission constraints, not registry metadata.
- Owner acceptance exists as Markdown review material. It should be converted into a PG owner acceptance/review fact in a separate bounded task rather than silently treated as source of truth.

Why no file config:

- No YAML, JSON, or local runtime config was introduced.
- Markdown remains a human review artifact only.
- The recommended source-of-truth path is PG registry + PG admission + PG owner decision + PG constraints + PG account facts.

Why execution/order was not touched:

- This task only maps strategy/trial configuration ownership.
- It does not require execution orchestrator, order lifecycle, exchange gateway, runtime, live runner, or permission changes.

## 6. Trial Start Checklist Readiness

Verdict: `needs_strategy_family_pg_registration`, `needs_owner_decision_pg_mapping`, and `needs_owner_trial_config_pg_record`.

Reason:

- A PG-backed trial start checklist can be generated from existing PG record types once the MI-001 record chain exists.
- The checklist should not be generated from Markdown files as source of truth.
- The checklist must verify:
  - strategy/candidate exists in PG;
  - Owner plan-preparation approval exists in PG;
  - bounded trial plan prepared state exists in PG;
  - dedicated subaccount policy exists in PG constraints;
  - `max_leverage = 5` exists in PG constraints;
  - `max_attempts = 3` exists in PG constraints;
  - cached account facts are fresh;
  - wallet/account equity is available from cached `AccountSnapshot.total_balance`;
  - available margin is available from cached `AccountSnapshot.available_balance` or explicitly unavailable with conservative cap behavior;
  - Operation Layer cap check is available;
  - kill switch is available;
  - symbol is `SOL/USDT:USDT`;
  - side is `long`;
  - candidate is `MI-001`;
  - no runtime has been started;
  - no execution permission has been granted;
  - separate Owner trial-start approval is still required.

Until those records exist, the checklist status should stay blocked and must not infer readiness from Markdown review artifacts.

## 7. File Config Avoidance Check

| check | answer |
| --- | --- |
| 是否新增 YAML/JSON/local config 作为 runtime source？ | no |
| 是否把 Markdown 当作 source of truth？ | no |
| 是否将配置优先映射到 PG？ | yes |
| 是否保留 Markdown 仅作 review artifact？ | yes |

## 8. Safety Check

| check | answer |
| --- | --- |
| 是否 push？ | no |
| 是否连接交易所？ | no |
| 是否调用真实账户 API？ | no |
| 是否下单？ | no |
| 是否创建 execution intent？ | no |
| 是否触碰 exchange_gateway？ | no |
| 是否触碰 execution/order/live runner？ | no |
| 是否运行 migration upgrade/downgrade？ | no |
| 是否启动 trial？ | no |
| 是否自动授予 trial start？ | no |

## 9. Current Strategy Research Progress

| strategy / family | current_state | PG-backed status | next boundary |
| --- | --- | --- | --- |
| MI-001 SOL/USDT:USDT long | current bounded trial preparation candidate; broad smoke complete; Owner accepted plan preparation in review artifact; bounded trial plan review artifact exists | not yet materialized as canonical PG strategy/admission/owner/trial-config record chain | register into PG registry/admission/owner decision/constraint snapshot before any checklist or trial start |
| VI-001 ETH/USDT:USDT long | backup trial candidate from broad smoke | no current trial PG mapping | keep as backup only; do not expand now |
| MI-001 BNB/USDT:USDT long | high-ranking broad smoke row but shorter local history | no current trial PG mapping | keep as reference; do not supersede SOL without Owner decision |
| Other strategy families | TB/VB/PC/MR/RB and others remain reference, parked, or keep-for-later | historical/registry structures can carry them later | no trial promotion in this task |
| Tier 1 data families | FD/OI/TAKER/BASIS/LS/ATT are request-ready only | no data downloaded or ingested by this task | Owner confirmation required before any Tier 1 data work |

## 10. Next Recommended Task

Register `MI-001 SOL/USDT:USDT long` into PG strategy/admission records.

Minimum scope:

- create/upsert MI-001 metadata in `brc_strategy_family_registry`;
- create/upsert the MI-001 playbook metadata without execution fields;
- create admission strategy family/version facts for SOL long;
- pin broad smoke evidence as an admission evidence packet;
- create Owner plan-preparation approval as PG owner decision/risk acceptance evidence;
- create a trial constraint snapshot with dedicated subaccount policy, `max_leverage=5`, `max_attempts=3`, no expansion rules, and separate trial-start approval required;
- create a planned admission trial binding only, with no campaign/runtime/order/execution implication.
