# PG Registration MI-001 SOL Long Result

Generated: 2026-05-29

Scope: `MI-001 SOL/USDT:USDT long` PG source-of-truth registration readiness.

This report is a review artifact only. Runtime source of truth must be PG records produced from the dry-run payload after the remaining apply blockers are cleared.

## 1. Summary

Implemented a pure dry-run registration builder for `MI-001 SOL/USDT:USDT long`.

The builder creates deterministic, PG-shaped domain records for:

- strategy family registry metadata;
- strategy family playbook metadata;
- admission strategy family/version;
- broad smoke evidence packet;
- Owner plan-preparation approval / risk acceptance payload;
- trial constraint snapshot payload;
- planned admission trial binding payload.

No PG write was performed. No trial was started. No exchange was connected. No real account API was called. No order was created. No execution intent was created. No execution permission was modified. No migration was run. No runtime or live runner was started.

## 2. Path Chosen

Path B: dry-run registration payload builder.

Reason:

- Existing PG tables and domain objects can represent the target chain without migration.
- Existing repositories can write most records, but a truthful trial constraint apply requires fresh cached `AccountSnapshot.total_balance`, optional `AccountSnapshot.available_balance`, and Operation Layer cap facts.
- This task explicitly forbids connecting to the exchange or calling real account APIs, so concrete `current_dedicated_subaccount_equity`, `max_loss_budget`, and `max_notional` cannot be resolved safely here.
- Writing an installable trial constraint snapshot without those account facts would make a review artifact look like runtime truth.
- The safe implementation is a deterministic dry-run payload that proves field ownership and boundary separation, then leaves actual PG apply as the next bounded task.

## 3. PG Record Chain

| record_type | pg_table_or_repository | status | content_summary | runtime_effect | notes |
| --- | --- | --- | --- | --- | --- |
| strategy family | `brc_strategy_family_registry` / `PgStrategyFamilyRegistryRepository` | dry_run_payload_ready | `MI-001`, Momentum Impulse, SOL-only, active observation candidate equivalent to trial candidate with known risks | none | No capital, order, routing, or runtime authority fields are stored here. |
| playbook | `brc_strategy_family_playbooks` / `PgStrategyFamilyRegistryRepository` | dry_run_payload_ready | `MI-001-SOL-LONG-BT-001`, 12h close-to-close impulse metadata, `would_enter` allowed | none | Metadata only; not an executable strategy registration. |
| candidate/admission | `brc_strategy_families`, `brc_strategy_family_versions`, `brc_admission_requests` / `PgBrcAdmissionRepository` | dry_run_payload_ready | `MI-001-SOL-LONG`, live funded-validation request, `owner_confirm_each_entry`, SOL long only | none | Requested mode is not auto execution and does not grant permission. |
| evidence packet | `brc_admission_evidence_packets` / `PgBrcAdmissionRepository` | dry_run_payload_ready | Broad smoke metrics: 8135 signals, 24h/72h/7d forward evidence, known limitations | none | Research evidence only; not alpha proof. |
| owner approval | `brc_owner_risk_acceptances` / `brc_review_decisions` | dry_run_payload_ready | Owner approved bounded trial plan preparation, dedicated subaccount model, max 5x policy | none | Explicitly not trial-start approval and not automatic execution approval. |
| trial constraint snapshot | `brc_trial_constraint_snapshots` / `PgBrcAdmissionRepository` | dry_run_pending_account_facts | Dedicated subaccount policy, max leverage 5, max attempts 3, no expansion rules | none | Status remains `pending_risk_capital_resolution` until concrete account facts resolve capital. |
| trial binding | `brc_admission_trial_bindings` / `PgBrcAdmissionRepository` | dry_run_payload_ready | Planned binding only, no campaign, no runtime carrier, no order capability | none | Binding is `planned`, not campaign/runtime installation. |

## 4. Source-of-truth Status

| item | status |
| --- | --- |
| MI-001 strategy family | dry-run PG-backed payload ready |
| MI-001 playbook | dry-run PG-backed payload ready |
| MI-001 SOL long candidate/admission | dry-run PG-backed payload ready |
| broad smoke evidence | dry-run PG-backed payload ready; Markdown remains review artifact |
| Owner plan-preparation approval | dry-run PG-backed payload ready; trial start not approved |
| trial constraint snapshot | dry-run pending fresh account facts before apply |
| planned trial binding | dry-run PG-backed payload ready |
| runtime/trial start | not granted |

## 5. Constraint Snapshot Summary

The dry-run trial constraint snapshot includes:

- `capital_source = dedicated_subaccount`
- `trial_risk_capital_rule = current_dedicated_subaccount_equity`
- `max_total_loss_rule = current_dedicated_subaccount_equity`
- `max_leverage = 5`
- `max_notional_rule = min(current_dedicated_subaccount_equity * 5, available_margin * 5 if available, operation_layer_notional_cap_if_exists)`
- `allowed_symbol = SOL/USDT:USDT`
- `allowed_side = long`
- `allowed_candidate = MI-001`
- `max_attempts = 3`
- `one_active_trial_position = true`
- `no_auto_top_up = true`
- `no_transfer = true`
- `no_withdrawal = true`
- `no_symbol_expansion = true`
- `no_side_expansion = true`
- `no_leverage_expansion_above_5x = true`
- `operation_layer_gate_required = true`
- `kill_switch_required = true`
- `trial_start_requires_separate_owner_approval = true`

The snapshot is deliberately `pending_risk_capital_resolution` because no fresh account equity was read in this task.

## 6. Safety Check

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

## 7. Trial Start Checklist Readiness

Verdict: `needs_registration_apply` and `needs_owner_trial_start_approval`.

Reason:

- The dry-run builder can now generate the target PG record payload chain.
- The chain is not written to PG in this task.
- Trial constraints still require a fresh cached account facts snapshot and Operation Layer cap read before concrete capital can be resolved.
- Owner approval currently represented in the dry-run payload is for bounded trial plan preparation only.
- A separate Owner trial-start approval must still be collected and written to PG before any trial-start checklist can pass.

## 8. Current Strategy Research Progress

| item | status | next |
| --- | --- | --- |
| MI-001 SOL long | current bounded trial preparation candidate; dry-run PG registration payload exists | apply dry-run registration to PG records after fresh account facts and Operation Layer cap facts are available |
| VI-001 ETH long | backup candidate only | keep parked unless Owner asks for backup candidate registration |
| MI-001 BNB long | high-ranking reference row with shorter local history | keep as reference; do not supersede SOL in this task |
| other strategy families | TB/VB/PC/MR/RB remain reference, parked, or keep-for-later | no expansion now |
| Tier 1 data families | request-ready only | no download or ingestion without Owner confirmation |

## 9. Next Recommended Task

Apply dry-run registration to PG records.

Minimum scope:

- read fresh cached account facts without calling real account APIs from this task path;
- compute concrete `max_loss_budget` and `max_notional` from the dedicated-subaccount policy;
- write the MI-001 registry metadata and playbook metadata;
- write admission family/version, evidence packet, Owner plan-preparation approval, pending or installable constraint snapshot as appropriate, and planned binding;
- verify no execution intent, no order, no runtime start, and no live runner wiring occurred.
