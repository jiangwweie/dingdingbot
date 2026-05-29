# PG Registration Real Apply MI-001 SOL Long Result

Generated: 2026-05-29

Scope: real PG apply for `MI-001 SOL/USDT:USDT long` metadata/admission registration.

This report is a review artifact only. The source of truth for the applied registration is now the local PG metadata/admission record chain described below.

## 1. Summary

Applied the `MI-001 SOL/USDT:USDT long` registration helper to the local Docker PostgreSQL database.

The apply wrote only metadata/admission/evidence/constraint records:

- strategy family registry metadata;
- strategy family playbook metadata;
- admission strategy family/version;
- admission rule config;
- broad smoke evidence packet;
- Owner market regime input;
- admission request;
- trial constraint snapshot with policy rules only;
- admission decision for plan preparation only;
- Owner plan-preparation risk acceptance;
- planned trial binding.

No trial was started. No exchange was connected. No real account API was called. No order was created. No execution intent was created. No execution permission was granted. No migration was run. No runtime or live runner was started.

## 2. Path Chosen

Path A: execute real PG metadata/admission apply.

Reason:

- DB target was clearly local Docker PG: `postgresql+asyncpg://dingdingbot:***@localhost:5432/dingdingbot`.
- Required metadata/admission/evidence/constraint tables already existed.
- No migration was needed or run.
- The apply helper is idempotent.
- The helper writes through registry/admission repositories only.
- Guard table counts for trial intents, execution intents, orders, and campaigns were unchanged before/after apply.
- Applied binding remains `planned`; it has no campaign id and no runtime carrier id.

## 3. Preflight Result

| check | status | evidence | notes |
| --- | --- | --- | --- |
| db target known | pass | `dingdingbot` database on local Docker PG, user `dingdingbot`, localhost port `5432` | Password masked. |
| non-production environment | pass with caution | Docker container `dingdingbot-pg`; `.env.local` is local-only | `.env.local` has `TRADING_ENV=live` for local read-only mode, but no runtime was started and this task touched metadata only. |
| migrations not run | pass | No Alembic upgrade/downgrade command executed | Existing schema used as-is. |
| required tables exist | pass | All required registry/admission/evidence/constraint tables were present | No schema creation performed. |
| apply idempotent | pass | Second apply returned `already_exists` for admission rows and `upserted` for registry/playbook rows | Guard table counts stayed unchanged. |
| metadata-only writes | pass | Repositories used: `PgStrategyFamilyRegistryRepository`, `PgBrcAdmissionRepository` | No runtime repository used. |
| no runtime writes | pass | `brc_campaigns` count before/after stayed `11` | No campaign created or updated. |
| no execution/order writes | pass | `execution_intents=20`, `orders=83`, `brc_trial_trade_intents=0` before/after | Counts unchanged. |
| no trial start | pass | Binding status is `planned`; `campaign_id=null`; `runtime_carrier_id=null` | Planned binding is metadata only. |
| owner trial-start approval still required | pass | Decision `owner_approved_trial_start=false`; risk disclosure `owner_has_not_approved_trial_start=true` | Owner approval is plan-preparation only. |

## 4. Apply Result

| record_type | apply_status | pg_table_or_repository | record_identifier | runtime_effect | notes |
| --- | --- | --- | --- | --- | --- |
| strategy family | upserted | `brc_strategy_family_registry` / `PgStrategyFamilyRegistryRepository.upsert_family_metadata` | `MI-001:MI-001-smoke-v0` | none | Metadata only; no capital/order/routing authority. |
| playbook | upserted | `brc_strategy_family_playbooks` / `PgStrategyFamilyRegistryRepository.upsert_playbook_metadata` | `MI-001-SOL-LONG-BT-001` | none | Metadata only; no execution/order fields in parameter profile. |
| admission family | created | `brc_strategy_families` / `PgBrcAdmissionRepository.create_strategy_family` | `MI-001` | none | Admission family metadata only. |
| admission version | created | `brc_strategy_family_versions` / `PgBrcAdmissionRepository.create_strategy_family_version` | `MI-001-SOL-LONG-admission-v1` | none | Required execution capabilities are empty. |
| rule config | created | `brc_admission_rule_configs` / `PgBrcAdmissionRepository.create_rule_config` | `brc-admission-rules-default-v1` | none | Boundaries record; no permission grant. |
| evidence packet | created | `brc_admission_evidence_packets` / `PgBrcAdmissionRepository.create_evidence_packet` | `MI-001-SOL-LONG-broad-smoke-evidence-v1` | none | Broad smoke research evidence only. |
| owner regime input | created | `brc_owner_market_regime_inputs` / `PgBrcAdmissionRepository.create_owner_regime_input` | `MI-001-SOL-LONG-owner-regime-v1` | none | Owner review context only. |
| admission request | created | `brc_admission_requests` / `PgBrcAdmissionRepository.create_admission_request` | `MI-001-SOL-LONG-admission-request-v1` | none | Requested mode remains `owner_confirm_each_entry`; no auto execution. |
| trial constraint snapshot | created | `brc_trial_constraint_snapshots` / `PgBrcAdmissionRepository.create_trial_constraint_snapshot` | `MI-001-SOL-LONG-trial-constraints-v1` | none | Policy rules only; status `pending_risk_capital_resolution`. |
| admission decision | created | `brc_admission_decisions` / `PgBrcAdmissionRepository.create_admission_decision` | `MI-001-SOL-LONG-admission-decision-v1` | none | `admit_with_constraints` for plan preparation only. |
| Owner plan-preparation approval | created | `brc_owner_risk_acceptances` / `PgBrcAdmissionRepository.create_owner_risk_acceptance` | `MI-001-SOL-LONG-owner-risk-acceptance-v1` | none | Trial start not approved. |
| planned trial binding | created | `brc_admission_trial_bindings` / `PgBrcAdmissionRepository.create_admission_trial_binding` | `MI-001-SOL-LONG-planned-binding-v1` | none | `planned`, no campaign, no runtime carrier. |

Second apply verification:

- registry/playbook rows: `upserted`;
- admission/evidence/constraint/binding rows: `already_exists`;
- guard table counts unchanged.

## 5. Capital Policy Handling

This apply did not read fresh account facts.

This apply did not call any real account API.

This apply did not calculate or write concrete `current_equity`, `available_margin`, `max_loss_budget`, or `max_notional` amounts.

The applied trial constraint snapshot stores policy rules only:

- `capital_source = dedicated_subaccount`
- `trial_risk_capital_rule = current_dedicated_subaccount_equity`
- `max_total_loss_rule = current_dedicated_subaccount_equity`
- `max_leverage = 5`
- `max_notional_rule = min(current_dedicated_subaccount_equity * 5, available_margin * 5 if available, operation_layer_notional_cap_if_exists)`
- `max_attempts = 3`
- no auto top-up, no transfer, no withdrawal, no symbol expansion, no side expansion, no leverage expansion above 5x

Concrete current equity, available margin, Operation Layer cap, and kill switch checks remain deferred to the PG-backed trial start checklist.

## 6. Source-of-truth Status

| item | status |
| --- | --- |
| MI-001 strategy family | written to PG |
| MI-001 playbook | written to PG |
| MI-001 SOL long candidate/admission | written to PG |
| broad smoke evidence | written to PG; Markdown remains review artifact |
| Owner plan-preparation approval | written to PG; trial start not approved |
| trial constraint snapshot | written to PG as policy rules only; concrete capital unresolved |
| planned trial binding | written to PG; no campaign/runtime effect |
| runtime/trial start | not granted |

## 7. Trial Start Checklist Readiness

Verdict: `ready_to_generate_pg_backed_trial_start_checklist`, with required checks still expected to fail until facts/approval are present.

Remaining blockers to pass checklist:

- `needs_fresh_account_facts`
- `needs_operation_layer_cap_check`
- `needs_owner_trial_start_approval`

Reason:

- MI-001 SOL long registration chain now exists in PG.
- Constraint snapshot is intentionally policy-only and pending concrete risk capital resolution.
- Binding is planned metadata only.
- Owner trial-start approval remains absent.

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
| 是否授予 execution permission？ | no |
| 是否创建 order-capable record？ | no |
| 是否写 runtime/campaign/execution/order 表？ | no |

## 9. Current Strategy Research Progress

| item | status | next |
| --- | --- | --- |
| MI-001 SOL long | PG metadata/admission registration applied; trial start not approved | generate PG-backed trial start checklist |
| VI-001 ETH long | backup candidate only | keep parked unless Owner asks for backup candidate registration |
| MI-001 BNB long | high-ranking reference row with shorter local history | keep as reference; do not supersede SOL |
| other strategy families | TB/VB/PC/MR/RB remain reference, parked, or keep-for-later | no expansion now |
| Tier 1 data families | request-ready only | no download or ingestion without Owner confirmation |

## 10. Next Recommended Task

Generate PG-backed trial_start_checklist_mi001_sol_long.
