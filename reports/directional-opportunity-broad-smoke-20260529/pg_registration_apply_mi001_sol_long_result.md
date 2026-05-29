# PG Registration Apply MI-001 SOL Long Result

Generated: 2026-05-29

Scope: apply path for `MI-001 SOL/USDT:USDT long` PG-backed metadata/admission registration.

This report is a review artifact only. Runtime source of truth is the PG record chain produced through the apply helper or an equivalent explicit repository transaction.

## 1. Summary

Implemented a minimal apply helper for the existing `MI-001 SOL/USDT:USDT long` dry-run registration payload.

The helper maps the deterministic payload into injected PG repository calls for strategy registry metadata, playbook metadata, admission family/version, broad smoke evidence, Owner plan-preparation approval, trial constraint policy rules, and planned trial binding.

No real PG mutation was executed in this task. The apply path was verified against an in-memory repository-backed test database. No trial was started. No exchange was connected. No real account API was called. No order was created. No execution intent was created. No execution permission was granted. No migration was run. No runtime or live runner was started.

## 2. Path Chosen

Path B: implement apply service/helper and test with injected repositories; do not write current real PG.

Reason:

- Existing repository methods are sufficient for metadata/admission writes.
- Direct mutation of the current local PG is operationally meaningful and should remain explicit.
- This task does not require fresh account facts or concrete capital amounts.
- The safe deliverable is a tested apply path that can be invoked against real PG in a separate, explicit source-of-truth apply step.
- The implementation does not touch execution, order, exchange, runtime, or live runner code.

## 3. Apply Scope

| record_type | apply_status | repository_or_service | runtime_effect | notes |
| --- | --- | --- | --- | --- |
| strategy family | helper implemented and tested | `PgStrategyFamilyRegistryRepository.upsert_family_metadata` | none | Upserts `MI-001` registry metadata only. |
| playbook | helper implemented and tested | `PgStrategyFamilyRegistryRepository.upsert_playbook_metadata` | none | Upserts `MI-001-SOL-LONG-BT-001` playbook metadata only. |
| candidate/admission | helper implemented and tested | `PgBrcAdmissionRepository.create_strategy_family`, `create_strategy_family_version`, `create_admission_request` | none | Uses get-or-create semantics; no runtime start. |
| evidence packet | helper implemented and tested | `PgBrcAdmissionRepository.create_evidence_packet` | none | Stores broad smoke summary and limitations as research evidence only. |
| owner approval | helper implemented and tested | `PgBrcAdmissionRepository.create_owner_risk_acceptance` | none | Owner approval is plan-preparation/risk acceptance only, not trial-start approval. |
| trial constraint snapshot | helper implemented and tested | `PgBrcAdmissionRepository.create_trial_constraint_snapshot` | none | Stores policy rules only; status remains `pending_risk_capital_resolution`. |
| planned trial binding | helper implemented and tested | `PgBrcAdmissionRepository.create_admission_trial_binding` | none | Binding remains `planned`, with no campaign id and no runtime carrier id. |

## 4. Capital Policy Handling

This apply path does not read fresh account facts.

This apply path does not calculate or write concrete `current_equity`, `available_margin`, `max_loss_budget`, or `max_notional` amounts.

It stores the Owner-confirmed policy rules only:

- `capital_source = dedicated_subaccount`
- `trial_risk_capital_rule = current_dedicated_subaccount_equity`
- `max_total_loss_rule = current_dedicated_subaccount_equity`
- `max_leverage = 5`
- `max_notional_rule = min(current_dedicated_subaccount_equity * 5, available_margin * 5 if available, operation_layer_notional_cap_if_exists)`
- `max_attempts = 3`
- no auto top-up, no transfer, no withdrawal, no symbol expansion, no side expansion, no leverage expansion above 5x

Concrete equity, available margin, Operation Layer cap, and kill switch facts are deferred to the PG-backed trial start checklist.

## 5. Source-of-truth Status

| item | status |
| --- | --- |
| MI-001 strategy family | apply helper implemented and tested; real PG apply still explicit |
| MI-001 playbook | apply helper implemented and tested; real PG apply still explicit |
| MI-001 SOL long candidate/admission | apply helper implemented and tested; real PG apply still explicit |
| broad smoke evidence | apply helper implemented and tested; Markdown remains review artifact |
| Owner plan-preparation approval | apply helper implemented and tested; trial start still not approved |
| trial constraint snapshot | policy-rule apply helper implemented and tested; concrete capital unresolved |
| planned trial binding | apply helper implemented and tested; no campaign/runtime effect |
| runtime/trial start | not granted |

## 6. Trial Start Checklist Readiness

Verdict: `needs_registration_apply_to_real_pg`, `needs_fresh_account_facts`, `needs_operation_layer_cap_check`, and `needs_owner_trial_start_approval`.

Reason:

- The source-of-truth apply path now exists and is tested with injected repositories.
- Current real PG was not mutated in this task.
- Fresh cached account facts are still required before concrete risk capital can be checked.
- Operation Layer cap and kill switch checks are still required.
- Owner approval in the registered payload is plan-preparation only; separate trial-start approval remains required.

## 7. Safety Check

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

## 8. Current Strategy Research Progress

| item | status | next |
| --- | --- | --- |
| MI-001 SOL long | current bounded trial preparation candidate; dry-run payload and tested apply helper exist | apply registration helper to real PG source-of-truth records explicitly, then generate PG-backed trial start checklist |
| VI-001 ETH long | backup candidate only | keep parked unless Owner asks for backup candidate registration |
| MI-001 BNB long | high-ranking reference row with shorter local history | keep as reference; do not supersede SOL |
| other strategy families | TB/VB/PC/MR/RB remain reference, parked, or keep-for-later | no expansion now |
| Tier 1 data families | request-ready only | no download or ingestion without Owner confirmation |

## 9. Next Recommended Task

Apply MI-001 SOL registration helper to real PG source-of-truth records.
