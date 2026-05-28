# BRC-R5-002 Admission Gate State

Date: 2026-05-27

## Summary

BRC-R5-002 is implemented through Phase 17. It is a funded validation admission
system, not a strict strategy approval gate. The default posture is to admit
with constraints when uncertainty can be bounded and reviewed.

## Implemented

- PG-backed strategy family registry and version-pinned strategy family facts.
- PG-backed admission rule config, request, evidence packet, Owner market regime
  input, decision, trial constraint snapshot, Owner risk acceptance, and audit log.
- `RiskCapitalAdapter` interface plus explicit pending and Phase 2 resolution adapters.
- Evaluation skeleton that reads pinned facts, calls the adapter, creates a
  constraint snapshot, creates an admission decision, and appends audit evidence.
- BRC Owner Console API endpoints for strategy family registry and admission
  read/create/evaluate flows.
- Phase 2 `BrcAdmissionRiskCapitalAdapter` resolution contract that can emit
  `installable` constraints under safe non-runtime conditions.
- Phase 3 `create_gated_trial_from_admission` Operation preflight skeleton.
- Phase 4 admission-trial binding skeleton. Operation confirm can reserve a
  `binding_reserved` admission-trial binding only; it does not create a campaign,
  create a runtime carrier, install constraints, place orders, or start a trial.
- Phase 5 campaign carrier creation skeleton. A separate Operation can create a
  BRC campaign shell from a reserved admission binding and advance the binding to
  `campaign_created`. This shell is metadata only: runtime is not installed,
  strategy is not active, constraints are not installed, and no orders are placed.
- Phase 6 runtime constraint installation skeleton. A separate Operation can
  install the admission campaign's installable constraint snapshot into campaign
  metadata and advance the binding to `runtime_constraints_installed`. This is
  still metadata only: runtime does not start, strategy remains inactive,
  auto execution remains disabled, trial remains inactive, and no orders are
  placed.
- Phase 7 runtime carrier readiness skeleton. A separate Operation can mark the
  admission campaign metadata `carrier_ready=true` and
  `runtime_status=carrier_ready_not_started` after constraints are installed.
  This is readiness metadata only: runtime does not start, strategy remains
  inactive, auto execution remains disabled, trial remains inactive, and no
  orders are placed.
- Phase 8 runtime start readiness skeleton. A separate Operation can mark the
  carrier-ready admission campaign metadata `runtime_start_ready=true` and
  `runtime_status=runtime_start_ready_not_started`. This is start-readiness
  metadata only: runtime does not start, strategy remains inactive, auto
  execution remains disabled, trial remains inactive, and no orders are placed.
- Phase 9 execution mode enforcement contract skeleton. A separate Operation can
  evaluate intended trial trade actions against `execution_mode` and record
  non-executable `observe_only` / `no_entry` evidence in
  `brc_trial_trade_intents`. It does not create orders, execution intents,
  runtime starts, strategy activation, live paths, or auto execution.
- Phase 10 runtime start handoff preflight skeleton. A separate Operation can
  mark the runtime-start-ready admission campaign metadata
  `runtime_handoff_ready=true` and
  `runtime_status=runtime_handoff_ready_not_started`. This is handoff-readiness
  metadata only: runtime does not start, `runtime_started` remains false,
  strategy remains inactive, trial remains inactive, and no orders are placed.
- Phase 11 runtime start preflight-only skeleton. A separate Operation can check
  whether a handoff-ready admission campaign satisfies the future runtime start
  conditions. Confirm is disabled/not implemented and cannot start runtime,
  activate strategy, enable auto execution, create orders, or create execution
  intents. The latest actual campaign state remains
  `runtime_handoff_ready_not_started`.
- Phase 12 runtime start state transition. The same
  `start_runtime_from_admission_handoff` Operation can now start admission-backed
  runtime state only, writing `runtime_started=true` and
  `runtime_status=runtime_started_strategy_inactive`. Strategy remains inactive,
  trial remains not started, auto execution remains disabled, and no order or
  execution intent is created.
- Phase 13 strategy activation readiness skeleton. A separate Operation can mark
  runtime-started admission campaign metadata `strategy_activation_ready=true`
  and `runtime_status=strategy_activation_ready_not_active`. This is readiness
  metadata only: strategy does not activate, the signal loop does not start,
  auto execution remains disabled, and no trade intent, execution intent, or
  order is created.
- Phase 14 strategy activation state transition skeleton. A separate Operation
  can mark campaign metadata `strategy_state=strategy_active_no_execution`,
  `strategy_activation_state=active_no_execution`, and
  `runtime_status=strategy_active_no_execution`. This is strategy metadata only:
  no signal loop starts, no strategy execution is enabled, no auto execution is
  enabled, and no trade intent, execution intent, or order is created.
- Phase 15 signal loop readiness skeleton. A separate Operation can mark
  campaign metadata `signal_loop_ready=true` and
  `runtime_status=signal_loop_ready_not_started`. This is readiness metadata
  only: signal loop does not start, no strategy signal is generated, auto
  execution remains disabled, and no trade intent, execution intent, or order is
  created.
- Phase 16 signal loop start state skeleton. A separate Operation can mark
  campaign metadata `signal_loop_started=true`, `signal_loop_enabled=true` with
  `signal_loop_enabled_scope=non_trading_loop_state`, and
  `runtime_status=signal_loop_started_no_signal`. This starts loop state
  metadata only: no strategy signal is generated, no trade intent is created,
  no execution intent is created, auto execution remains disabled, trial remains
  inactive, and no order is created.
- Phase 17 signal evaluation skeleton. A separate Operation can record
  non-trading signal evaluation metadata and mark
  `runtime_status=signal_evaluated_no_intent`. This may set
  `signal_evaluated=true` and `signal_generated=true`, but only with explicit
  no-intent/no-order flags: no trade intent is created, no execution intent is
  created, auto execution remains disabled, trial remains inactive, and no
  order is created.

## API Summary

- `GET /api/brc/strategy-families`
- `POST /api/brc/strategy-families`
- `GET /api/brc/strategy-families/{strategy_family_id}`
- `POST /api/brc/strategy-families/{strategy_family_id}/versions`
- `POST /api/brc/admissions/evidence-packets`
- `POST /api/brc/admissions/owner-regime-inputs`
- `POST /api/brc/admissions/requests`
- `GET /api/brc/admissions/requests/{admission_request_id}`
- `POST /api/brc/admissions/requests/{admission_request_id}/evaluate`
- `GET /api/brc/admissions/decisions`
- `GET /api/brc/admissions/decisions/{admission_decision_id}`
- `POST /api/brc/admissions/risk-acceptances`
- `GET /api/brc/admissions/trial-bindings`
- `GET /api/brc/admissions/trial-bindings/{binding_id}`

## Domain Model

Phase 1 uses separate tables for the high-value versioned/auditable facts:

- `brc_strategy_families`
- `brc_strategy_family_versions`
- `brc_admission_rule_configs`
- `brc_admission_requests`
- `brc_owner_market_regime_inputs`
- `brc_admission_evidence_packets`
- `brc_admission_decisions`
- `brc_trial_constraint_snapshots`
- `brc_owner_risk_acceptances`
- `brc_admission_audit_log`
- `brc_admission_trial_bindings`
- `brc_trial_trade_intents`

Regime contracts, safeguards, degradation policy, evidence payload, rule details,
risk disclosure, known gaps, warnings/blockers, and constraints details are JSONB
in Phase 1.

## RiskCapitalAdapter Behavior

Admission Gate does not compute sizing. It emits risk intent and requested risk
profile. `AdmissionService` only calls the adapter and persists the returned
snapshot.

The Phase 2 default adapter is `BrcAdmissionRiskCapitalAdapter`.

`PendingRiskCapitalAdapter` still exists for fail-safe unresolved behavior and
returns `pending_risk_capital_resolution` with `sizing_computed=false`.

## Installable Constraint Contract

`trial_constraint_snapshot.constraints_json` carries the installable/pending
contract:

- `source`: `risk_capital_adapter`, `fallback_policy`, or `unavailable`
- `risk_profile`
- `execution_mode`
- `trial_env`
- `trial_stage`
- `account_facts_snapshot_ref`
- `account_source`
- `truth_level`
- `reconciliation_status`
- `max_loss_budget`
- `max_notional`
- `max_leverage`
- `max_attempts`
- `allowed_symbols`
- `allowed_timeframes`
- `review_requirements`
- `cooldowns`
- `blockers`
- `warnings`
- `limitations`

`pending_risk_capital_resolution` means the decision may be reviewed but cannot
be installed by a future Operation confirm. `installable` means constraints are
concrete enough for Owner risk acceptance and future Operation preflight, but
Phase 2 still does not install runtime state.

## Admission Trial Binding

Phase 4 adds `brc_admission_trial_bindings` as a persistent reservation between
an admission decision and a future BRC campaign/runtime carrier. Phase 5 uses the
same binding to link a reserved admission to a campaign shell.

Supported active statuses:

- `binding_reserved`
- `campaign_created`
- `runtime_constraints_installed`

Modeled but not used by Phase 10:

- `planned`
- `runtime_installed`

Terminal/non-active statuses:

- `cancelled`
- `expired`
- `invalidated`

`binding_reserved` is not a trial-started state. It must keep `campaign_id` and
`runtime_carrier_id` null. It only records that the admission decision,
installable constraint snapshot, pinned playbook, account facts boundary, and
Owner risk acceptance were ready enough to reserve a future binding plan.

`campaign_created` means a BRC campaign carrier shell exists for metadata and
review linkage only. It is not runtime installation, strategy activation,
runtime constraint enforcement, live enablement, or order authorization.

`runtime_constraints_installed` means the installable constraint snapshot was
copied into the admission-created campaign metadata. It is not runtime started,
not strategy active, not trial started, not live enabled, and not order-capable.

`carrier_ready` is a campaign metadata state, not a binding status. It means the
admission campaign has passed readiness checks for a future runtime carrier. It
is not runtime started, not strategy active, not trial started, not live enabled,
not `auto_within_budget`, and not order-capable.

`runtime_start_ready` is a campaign metadata state, not a binding status. It
means the carrier-ready admission campaign has passed checks for a future
runtime start handoff. It is not `runtime_started`, not `strategy_active`, not
`trial_started`, not live enabled, not `auto_within_budget`, and not
order-capable.

`runtime_handoff_ready` is a campaign metadata state, not a binding status. It
means the runtime-start-ready admission campaign has passed a handoff preflight
for a future runtime-start Operation. It is not `runtime_started`, not
`strategy_active`, not `trial_started`, not live enabled, not
`auto_within_budget`, and not order-capable.

The campaign shell metadata includes:

- `created_from_admission=true`
- `admission_binding_id`
- `admission_decision_id`
- `strategy_family_version_id`
- `playbook_id`
- `constraint_snapshot_id`
- `trial_env`
- `trial_stage`
- `execution_mode`
- `runtime_status=not_installed`
- `strategy_status=not_active`
- `constraints_installed=false`
- `orders_placed=false`
- `live_ready=false`

After Phase 6 installation, the campaign shell metadata additionally includes:

- `constraints_installed=true`
- `installed_constraint_snapshot_id`
- `installed_constraints_summary`
- `installed_at`
- `installed_by_operation_id`
- `installed_by_preflight_id`
- `runtime_status=constraints_installed_not_started`
- `runtime_started=false`
- `runtime_active=false`
- `strategy_active=false`
- `trial_started=false`
- `auto_within_budget_enabled=false`
- `owner_confirm_each_entry_enabled=false`

After Phase 7 carrier readiness preparation, the campaign shell metadata
additionally includes:

- `carrier_ready=true`
- `runtime_status=carrier_ready_not_started`
- `prepared_at`
- `prepared_by_operation_id`
- `prepared_by_preflight_id`
- `carrier_readiness_summary`
- `runtime_started=false`
- `runtime_active=false`
- `strategy_active=false`
- `trial_started=false`
- `auto_within_budget_enabled=false`
- `owner_confirm_each_entry_enabled=false`
- `orders_placed=false`

After Phase 8 runtime start readiness preparation, the campaign shell metadata
additionally includes:

- `runtime_start_ready=true`
- `runtime_status=runtime_start_ready_not_started`
- `start_ready_at`
- `start_ready_by_operation_id`
- `start_ready_by_preflight_id`
- `runtime_start_readiness_summary`
- `runtime_started=false`
- `runtime_active=false`
- `strategy_active=false`
- `trial_started=false`
- `auto_within_budget_enabled=false`
- `owner_confirm_each_entry_enabled=false`
- `orders_placed=false`

After Phase 10 runtime handoff readiness preparation, the campaign shell metadata
additionally includes:

- `runtime_handoff_ready=true`
- `runtime_status=runtime_handoff_ready_not_started`
- `handoff_ready_at`
- `handoff_ready_by_operation_id`
- `handoff_ready_by_preflight_id`
- `runtime_handoff_readiness_summary`
- `runtime_started=false`
- `runtime_active=false`
- `strategy_active=false`
- `trial_started=false`
- `auto_within_budget_enabled=false`
- `owner_confirm_each_entry_enabled=false`
- `orders_placed=false`

## Execution Mode Enforcement Contract

Phase 9 defines `execution_mode` behavior without adding execution authority:

- `observe_only`: records a would-have-traded trial intent as `decision=recorded`.
  It does not execute, create an order, or create an execution intent.
- `no_entry`: blocks `entry` and `increase` as `decision=blocked` with a
  `not_executed_reason`; `exit` and `reduce` can be recorded as non-executable
  evidence. No order is created.
- `auto_within_budget`: checks required installed constraints completeness
  only. It returns that runtime execution would be required, but actual auto
  execution remains disabled.
- `owner_confirm_each_entry`: reserved and unavailable; no execution flow is
  implemented.

`brc_trial_trade_intents` is an evidence ledger only. It is not an order table,
not an execution-intent table, and must not feed order execution.

## Testnet Behavior

For `trial_env=testnet` and `trial_stage=development_validation`, the adapter can
return conservative installable fallback constraints when no real capital sizing
exists. These constraints are marked `source=fallback_policy` and `live_usable=false`.
They are not live constraints and do not authorize runtime execution.

## Live Funded Validation Behavior

For `trial_env=live` and `trial_stage=funded_validation`:

- account facts unavailable rejects/blocks admission;
- reconciliation mismatch rejects/blocks admission;
- unknown unmanaged exposure rejects/blocks admission;
- missing risk/capital resolution returns pending, not installable;
- installable constraints require clean account facts plus explicit concrete
  risk/capital resolution fields.

## Owner Risk Acceptance

Owner risk acceptance can be persisted only for `installable` constraints.
Pending constraints return a clear API/service error and cannot be treated as
accepted risk.

## Operation Preflight

`create_gated_trial_from_admission` is registered in Operation Layer capabilities
as binding-reservation-only:

- `operation_type=create_gated_trial_from_admission`
- display name: `Admission Binding Reservation`
- `capability_status=binding_reservation_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_RESERVE_ADMISSION_BINDING`

Preflight validates:

- admission decision exists and is `admit` or `admit_with_constraints`;
- decision is not expired;
- constraint snapshot exists and is `installable`;
- pending constraints cannot proceed;
- Owner risk acceptance exists for `funded_validation`;
- risk acceptance references the same request, decision, family version, env,
  stage, and constraint snapshot;
- playbook is pinned or provided safely;
- account facts snapshot ref exists;
- live funded validation still has acceptable account facts;
- audit is writable;
- no active BRC campaign exists when checkable.
- no active admission-trial binding already exists for the same decision.

The preflight response exposes admission, strategy family, constraint, risk
acceptance, env/stage, execution mode, blockers, warnings, and next-step
summaries. It also states that confirm would create only a binding reservation
and that no runtime trial will start, no campaign will be created, no runtime
constraints will be installed, and no orders will be placed.

Confirm in Phase 4 creates a `binding_reserved` row and returns audit/binding
refs. It is idempotent at the Operation result level and does not create
campaigns, runtime carriers, runtime constraints, orders, live execution,
withdrawals, or transfers.

Phase 5 adds a separate Operation:

- `operation_type=create_campaign_from_admission_binding`
- display name: `Admission Campaign Shell`
- `capability_status=campaign_shell_creation_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_CREATE_ADMISSION_CAMPAIGN_SHELL`

Preflight requires:

- an existing `binding_reserved` admission-trial binding;
- the linked admission decision is still admissible and not expired;
- the linked constraint snapshot is still `installable`;
- funded validation still has matching Owner risk acceptance;
- playbook remains pinned;
- no `campaign_id` already exists on the binding;
- live funded validation still has acceptable account facts when applicable;
- audit is writable;
- no active BRC campaign already exists when checkable.

Confirm creates a BRC campaign shell and updates the binding to
`campaign_created`. It does not create or switch a runtime carrier, install
runtime constraints, start strategy execution, place orders, enable live,
withdraw, or transfer. Double confirm returns the persisted Operation result
without creating a duplicate campaign.

Phase 6 adds a separate Operation:

- `operation_type=install_runtime_constraints_from_admission_campaign`
- display name: `Install Admission Campaign Constraints`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_INSTALL_ADMISSION_CAMPAIGN_CONSTRAINTS`

Preflight requires:

- an existing admission-trial binding in `campaign_created`;
- a non-empty `campaign_id` linked to the binding;
- the linked campaign metadata admission refs match the binding;
- the linked constraint snapshot exists and is still `installable`;
- funded validation still has matching Owner risk acceptance;
- `strategy_family_version_id` still matches the admission decision;
- playbook remains pinned;
- account facts are acceptable and not explicitly stale when checkable;
- audit is writable;
- runtime constraints are not already installed unless the request is
  idempotent for the same snapshot and `constraints_installed_not_started`
  state;
- no active conflicting runtime carrier exists when checkable.

Preflight explicitly reports that constraints would be installed, runtime will
not start, strategy will not activate, no orders will be placed, and the trial
remains inactive after install.

Confirm writes constraints metadata into the BRC campaign shell, advances the
binding to `runtime_constraints_installed`, writes admission and campaign audit
refs, and returns the installed constraints summary. Confirm must not start
runtime, activate strategy, create orders, enable live, install an executable
strategy runner, or change execution state to active. A duplicate confirm for
the same installed snapshot is idempotent and returns no-op semantics.

Phase 7 adds a separate Operation:

- `operation_type=prepare_runtime_carrier_from_admission_campaign`
- display name: `Prepare Admission Runtime Carrier`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_PREPARE_ADMISSION_RUNTIME_CARRIER`

Preflight requires:

- an existing admission-trial binding in `runtime_constraints_installed`;
- a non-empty `campaign_id` linked to the binding;
- campaign metadata exists and is admission-created;
- `constraints_installed=true`;
- `runtime_status=constraints_installed_not_started`, unless the same carrier
  readiness is already idempotently prepared as `carrier_ready_not_started`;
- `runtime_started=false`;
- `strategy_active=false`;
- `trial_started=false`;
- `orders_placed=false`;
- `installed_constraint_snapshot_id` exists and matches the binding snapshot;
- `strategy_family_version_id` is present;
- playbook remains pinned;
- `execution_mode` is one of the modeled admission execution modes;
- account facts freshness is acceptable;
- audit is writable;
- runtime is not already active;
- no active conflicting runtime carrier exists when checkable.

Preflight explicitly reports that carrier readiness would be prepared, runtime
will not start, strategy will not activate, auto execution will not be enabled,
no orders will be placed, and the trial remains inactive after readiness
preparation.

Confirm writes carrier readiness metadata into the BRC campaign shell and writes
admission and campaign audit refs. It does not change the binding status beyond
`runtime_constraints_installed`; that status remains the latest admission
binding milestone. Confirm must not start runtime, activate strategy, install an
executable strategy runner, create orders, enable live, change runtime state to
active, cancel, close, flatten, withdraw, transfer, or mark `trial_started=true`.
A duplicate confirm for the same prepared carrier is idempotent and returns
no-op semantics.

Phase 8 adds a separate Operation:

- `operation_type=prepare_runtime_start_from_admission_carrier`
- display name: `Prepare Admission Runtime Start`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_PREPARE_ADMISSION_RUNTIME_START`

Preflight requires:

- an existing admission-trial binding in `runtime_constraints_installed`;
- a non-empty `campaign_id` linked to the binding;
- campaign metadata exists and is admission-created;
- `carrier_ready=true`;
- `runtime_status=carrier_ready_not_started`, unless the same start readiness
  is already idempotently prepared as `runtime_start_ready_not_started`;
- `runtime_started=false`;
- `strategy_active=false`;
- `trial_started=false`;
- `orders_placed=false`;
- `constraints_installed=true`;
- `installed_constraint_snapshot_id` exists and matches the binding snapshot;
- `execution_mode` is one of the modeled admission execution modes;
- for `auto_within_budget`, installed constraints summary exists while auto
  execution remains disabled;
- for `observe_only` and `no_entry`, the mode can be prepared while runtime
  enforcement remains a future phase;
- account facts freshness is acceptable;
- audit is writable;
- no conflicting active runtime, trial, or strategy exists when checkable.

Preflight explicitly reports that runtime start readiness would be prepared,
runtime will not start, strategy will not activate, auto execution will not be
enabled, no orders will be placed, and the next phase must handle execution mode
enforcement.

Confirm writes runtime start readiness metadata into the BRC campaign shell and
writes admission and campaign audit refs. It does not change the binding status
beyond `runtime_constraints_installed`; that status remains the latest admission
binding milestone. Confirm must not start runtime, activate strategy, install an
executable strategy runner, create orders, enable live, change runtime state to
active, cancel, close, flatten, withdraw, transfer, or mark `trial_started=true`.
A duplicate confirm for the same prepared runtime start readiness is idempotent
and returns no-op semantics.

Phase 9 adds a separate Operation:

- `operation_type=evaluate_trial_trade_intent`
- display name: `Evaluate Trial Trade Intent`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_EVALUATE_TRIAL_TRADE_INTENT`

Preflight requires:

- campaign exists;
- campaign metadata has `runtime_start_ready=true`;
- `runtime_status=runtime_start_ready_not_started`;
- `runtime_started=false`;
- `strategy_active=false`;
- `orders_placed=false`;
- `execution_mode` exists and is modeled;
- installed constraint snapshot exists;
- audit is writable.

Confirm may record a non-executable `brc_trial_trade_intents` row for
`observe_only` / `no_entry`. For `auto_within_budget`, confirm only returns the
constraints completeness check and does not persist an order or execution
intent. `owner_confirm_each_entry` remains unavailable/not implemented. Confirm
must not start runtime, activate strategy, enable auto execution, create orders,
create execution intents, create live paths, cancel, close, flatten, withdraw,
or transfer.

Phase 10 adds a separate Operation:

- `operation_type=prepare_runtime_handoff_from_admission_campaign`
- display name: `Prepare Admission Runtime Handoff`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_PREPARE_ADMISSION_RUNTIME_HANDOFF`

Preflight requires:

- campaign exists;
- binding exists when `binding_id` is provided, or can be resolved by campaign;
- campaign metadata exists and is admission-created;
- `carrier_ready=true`;
- `runtime_start_ready=true`;
- `runtime_status=runtime_start_ready_not_started`, unless the same handoff
  readiness is already idempotently prepared as
  `runtime_handoff_ready_not_started`;
- `runtime_started=false`;
- `strategy_active=false`;
- `trial_started=false`;
- `orders_placed=false`;
- `constraints_installed=true`;
- `installed_constraint_snapshot_id` exists;
- `execution_mode` is valid;
- execution-mode enforcement contract is available;
- for `observe_only`, the trade intent ledger is available;
- for `no_entry`, blocked-entry recording is available;
- for `auto_within_budget`, constraints completeness can be checked while auto
  execution remains disabled;
- account facts freshness is acceptable;
- audit is writable;
- no conflicting active runtime or trial exists when checkable.

Preflight explicitly reports that runtime handoff readiness would be prepared,
runtime will not start, `runtime_started` will not be set true, strategy will
not activate, auto execution will not be enabled, no orders will be placed, and
the next phase must explicitly start runtime through a separate Operation.

Confirm writes runtime handoff readiness metadata into the BRC campaign shell and
writes admission and campaign audit refs. It does not change the binding status
beyond `runtime_constraints_installed`; that status remains the latest admission
binding milestone. Confirm must not start runtime, set `runtime_started=true`,
activate strategy, set `strategy_active=true`, create orders, create execution
intents, enable live, or mark `trial_started=true`. A duplicate confirm for the
same prepared runtime handoff readiness is idempotent and returns no-op
semantics.

Phase 11 added a separate preflight-only Operation:

- `operation_type=start_runtime_from_admission_handoff`
- display name: `Start Runtime From Admission Handoff Preflight`
- `capability_status=operation_preflight_available`
- `executable_through_operation=false`
- confirmation phrase: none; confirm is disabled/not implemented

Preflight requires:

- campaign exists;
- campaign metadata exists and is admission-created;
- `runtime_handoff_ready=true`;
- `runtime_status=runtime_handoff_ready_not_started`;
- `runtime_started=false`;
- `strategy_active=false`;
- `trial_started=false`;
- `orders_placed=false`;
- `constraints_installed=true`;
- `carrier_ready=true`;
- `runtime_start_ready=true`;
- `execution_mode` is valid;
- execution-mode enforcement contract is present;
- for `observe_only`, the trial trade intent ledger is available;
- for `no_entry`, blocked-entry recording is available through the same
  non-executable ledger contract;
- for `auto_within_budget`, installed constraints completeness can be checked,
  but actual execution remains disabled;
- account facts freshness is acceptable;
- audit is writable;
- runtime profile/environment mapping is safe;
- no conflicting active runtime/trial exists when checkable;
- no emergency stop or hard lock is active when checkable.

Preflight explicitly reports start conditions, blockers, warnings, whether a
future start would be possible, and that runtime will not start in Phase 11. If
confirm is called, it returns blocked/not implemented and must not mutate runtime
active state, set `runtime_started=true`, set `strategy_active=true`, mark
`trial_started=true`, create orders, or create execution intents.

Phase 12 upgrades the same Operation to a runtime-state-only transition:

- `operation_type=start_runtime_from_admission_handoff`
- display name: `Start Runtime From Admission Handoff`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_START_ADMISSION_RUNTIME`

Preflight still requires:

- campaign exists;
- campaign metadata exists and is admission-created;
- `runtime_handoff_ready=true`;
- `runtime_status=runtime_handoff_ready_not_started`, unless the campaign is
  already idempotently in `runtime_started_strategy_inactive`;
- `runtime_started=false`, unless the campaign is already idempotently in
  `runtime_started_strategy_inactive`;
- `strategy_active=false`;
- `trial_started=false`;
- `orders_placed=false`;
- `constraints_installed=true`;
- `carrier_ready=true`;
- `runtime_start_ready=true`;
- valid `execution_mode`;
- execution-mode enforcement contract is present;
- account facts freshness is acceptable;
- audit is writable;
- runtime profile/environment mapping is safe;
- no emergency stop or hard lock is active when checkable;
- no conflicting active runtime/trial exists when checkable.

Confirm may write only runtime start state metadata:

- `runtime_started=true`
- `runtime_status=runtime_started_strategy_inactive`
- `runtime_started_at`
- `runtime_started_by_operation_id`
- `runtime_started_by_preflight_id`
- `strategy_active=false`
- `trial_started=false`
- `orders_placed=false`
- `auto_execution_enabled=false`
- `auto_within_budget_enabled=false`

Confirm must not activate a strategy runner, set `strategy_active=true`, mark
`trial_started=true`, enable auto execution, create an order, create an
execution intent, enable live trading, cancel, close, flatten, withdraw, or
transfer. A repeated confirm on the same operation returns the existing result.
A new operation against an already `runtime_started_strategy_inactive` campaign
returns noop semantics rather than duplicating the transition.

Phase 12.5 alignment review keeps the Phase 12 runtime-state transition intact
and adds no new operation. The authoritative state chain is:

- admission facts and decision live in admission tables;
- admission binding status advances only through admission/constraints
  milestones and remains `runtime_constraints_installed` after runtime state is
  started;
- campaign metadata expresses runtime state, including
  `runtime_started=true` and
  `runtime_status=runtime_started_strategy_inactive`;
- `constraints_installed=true`, `carrier_ready=true`,
  `runtime_start_ready=true`, and `runtime_handoff_ready=true` remain prerequisite
  metadata for this runtime state;
- `strategy_active=false`, `trial_started=false`, `orders_placed=false`,
  `auto_execution_enabled=false`, and `auto_within_budget_enabled=false` remain
  required safety fields after runtime state start.

`runtime_started_strategy_inactive` means runtime state exists for the admission
campaign. It is not strategy activation, not trial start, not live enablement,
not auto execution, not order-capable execution, and not an execution intent
source. Phase 13 adds strategy activation readiness metadata only. Phase 14 adds
strategy metadata activation in `strategy_active_no_execution` state only.
Signal loop enablement, observe-gate runtime integration, order-capable strategy
execution, and `auto_within_budget` actual execution remain later phases after
explicit execution-mode runtime enforcement.

Phase 13 introduces a separate readiness operation:

- `operation_type=prepare_strategy_activation_from_admission_runtime`
- display name: `Prepare Strategy Activation From Admission Runtime`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_PREPARE_STRATEGY_ACTIVATION`

Preflight requires:

- campaign exists;
- campaign metadata exists and is admission-created;
- `runtime_started=true`;
- `runtime_status=runtime_started_strategy_inactive`;
- `strategy_active=false`;
- `trial_started=false`;
- `orders_placed=false`;
- `auto_execution_enabled=false`;
- `auto_within_budget_enabled=false`;
- valid `execution_mode`;
- pinned `playbook_id`;
- present `strategy_family_version_id`;
- `installed_constraint_snapshot_id` exists;
- account facts freshness is acceptable;
- audit is writable;
- no active strategy conflict when checkable;
- no unresolved safety blockers.

Confirm may write only strategy activation readiness metadata:

- `strategy_activation_ready=true`
- `runtime_status=strategy_activation_ready_not_active`
- `strategy_activation_ready_at`
- `strategy_activation_ready_by_operation_id`
- `strategy_activation_ready_by_preflight_id`
- `strategy_active=false`
- `trial_started=false`
- `orders_placed=false`
- `auto_execution_enabled=false`
- `auto_within_budget_enabled=false`

Confirm must not set `strategy_active=true`, mark `trial_started=true`, start a
strategy runner, start a signal loop, create a trade intent, create an execution
intent, create an order, enable auto execution, enable live trading, cancel,
close, flatten, withdraw, or transfer. Repeated confirm is idempotent, and a new
operation against an already prepared campaign returns noop semantics rather than
duplicating the transition.

Phase 14 introduces a separate non-execution activation operation:

- `operation_type=activate_strategy_from_admission_runtime`
- display name: `Activate Strategy From Admission Runtime`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_ACTIVATE_STRATEGY_NO_EXECUTION`

Preflight requires:

- campaign exists;
- campaign metadata exists and is admission-created;
- `runtime_started=true`;
- `runtime_status=strategy_activation_ready_not_active`;
- `strategy_activation_ready=true`;
- `strategy_active=false`;
- `trial_started=false`;
- `orders_placed=false`;
- `auto_execution_enabled=false`;
- `auto_within_budget_enabled=false`;
- valid `execution_mode`;
- execution-mode enforcement contract exists;
- pinned `playbook_id`;
- present `strategy_family_version_id`;
- `installed_constraint_snapshot_id` exists;
- account facts freshness is acceptable;
- audit is writable;
- no active strategy conflict when checkable;
- no already order-capable state flags are true.

Confirm may write only non-execution strategy state metadata:

- `strategy_state=strategy_active_no_execution`
- `strategy_activation_state=active_no_execution`
- `runtime_status=strategy_active_no_execution`
- `strategy_active=true`
- `strategy_execution_enabled=false`
- `signal_loop_enabled=false`
- `signal_loop_started=false`
- `auto_execution_enabled=false`
- `auto_within_budget_enabled=false`
- `trial_started=false`
- `orders_placed=false`
- `trade_intent_created=false`
- `execution_intent_created=false`
- `order_created=false`
- `strategy_activated_at`
- `strategy_activated_by_operation_id`
- `strategy_activated_by_preflight_id`

Confirm must not start a strategy runner, start a signal loop, create a trade
intent, create an execution intent, create an order, enable auto execution, mark
`trial_started=true`, enable live trading, cancel, close, flatten, withdraw, or
transfer. Repeated confirm is idempotent, and a new operation against an already
`strategy_active_no_execution` campaign returns noop semantics rather than
duplicating the transition.

Phase 15 introduces a separate signal loop readiness operation:

- `operation_type=prepare_signal_loop_from_admission_strategy`
- display name: `Prepare Signal Loop From Admission Strategy`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_PREPARE_SIGNAL_LOOP`

Preflight requires:

- campaign exists;
- campaign metadata exists and is admission-created;
- `runtime_status=strategy_active_no_execution`;
- `strategy_activation_state=active_no_execution`;
- `strategy_active=true`;
- `strategy_execution_enabled=false`;
- `signal_loop_enabled=false`;
- `signal_loop_started=false`;
- `trial_started=false`;
- `orders_placed=false`;
- `execution_intent_created=false`;
- `auto_execution_enabled=false`;
- `auto_within_budget_enabled=false`;
- valid `execution_mode`;
- execution-mode enforcement contract exists;
- pinned `playbook_id`;
- present `strategy_family_version_id`;
- `installed_constraint_snapshot_id` exists;
- account facts freshness is acceptable;
- audit is writable;
- no active signal loop conflict when checkable.

Confirm may write only signal loop readiness metadata:

- `signal_loop_ready=true`
- `runtime_status=signal_loop_ready_not_started`
- `signal_loop_ready_at`
- `signal_loop_ready_by_operation_id`
- `signal_loop_ready_by_preflight_id`
- `signal_loop_enabled=false`
- `signal_loop_started=false`
- `signal_generated=false`
- `strategy_execution_enabled=false`
- `trial_started=false`
- `orders_placed=false`
- `trade_intent_created=false`
- `execution_intent_created=false`
- `order_created=false`
- `auto_execution_enabled=false`
- `auto_within_budget_enabled=false`

Confirm must not start a signal loop, generate a strategy signal, create a trade
intent, create an execution intent, create an order, enable auto execution, mark
`trial_started=true`, enable live trading, cancel, close, flatten, withdraw, or
transfer. Repeated confirm is idempotent, and a new operation against an already
`signal_loop_ready_not_started` campaign returns noop semantics rather than
duplicating the transition.

Phase 16 introduces a separate signal loop start state operation:

- `operation_type=start_signal_loop_from_admission_strategy`
- display name: `Start Signal Loop From Admission Strategy`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_START_SIGNAL_LOOP_NO_SIGNAL`

Preflight requires:

- campaign exists;
- campaign metadata exists and is admission-created;
- `runtime_status=signal_loop_ready_not_started`;
- `signal_loop_ready=true`;
- `strategy_state=strategy_active_no_execution`;
- `strategy_activation_state=active_no_execution`;
- `strategy_active=true`;
- `strategy_execution_enabled=false`;
- `signal_loop_enabled=false`;
- `signal_loop_started=false`;
- `signal_generated=false`;
- `trade_intent_created=false`;
- `execution_intent_created=false`;
- `order_created=false`;
- `orders_placed=false`;
- `trial_started=false`;
- `auto_execution_enabled=false`;
- `auto_within_budget_enabled=false`;
- valid `execution_mode`;
- execution-mode enforcement contract exists;
- pinned `playbook_id`;
- present `strategy_family_version_id`;
- `installed_constraint_snapshot_id` exists;
- account facts freshness is acceptable;
- audit is writable;
- no active signal loop conflict when checkable.

Confirm may write only signal loop state metadata:

- `signal_loop_started=true`
- `signal_loop_enabled=true`
- `signal_loop_enabled_scope=non_trading_loop_state`
- `runtime_status=signal_loop_started_no_signal`
- `signal_loop_started_at`
- `signal_loop_started_by_operation_id`
- `signal_loop_started_by_preflight_id`
- `signal_generated=false`
- `trade_intent_created=false`
- `execution_intent_created=false`
- `order_created=false`
- `orders_placed=false`
- `strategy_execution_enabled=false`
- `trial_started=false`
- `auto_execution_enabled=false`
- `auto_within_budget_enabled=false`

Confirm must not generate a strategy signal, create a trade intent, create an
execution intent, create an order, enable auto execution, mark
`trial_started=true`, enable live trading, cancel, close, flatten, withdraw, or
transfer. Repeated confirm is idempotent, and a new operation against an already
`signal_loop_started_no_signal` campaign returns noop semantics rather than
duplicating the transition.

Phase 17 introduces a separate signal evaluation operation:

- `operation_type=evaluate_signal_from_admission_strategy`
- display name: `Evaluate Signal From Admission Strategy`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_EVALUATE_SIGNAL_NO_INTENT`

Preflight requires:

- campaign exists;
- campaign metadata exists and is admission-created;
- `runtime_status=signal_loop_started_no_signal`;
- `signal_loop_started=true`;
- `signal_loop_enabled_scope=non_trading_loop_state`;
- `signal_generated=false`, unless the campaign is already idempotently
  `signal_evaluated_no_intent`;
- `trade_intent_created=false`;
- `execution_intent_created=false`;
- `order_created=false`;
- `orders_placed=false`;
- `trial_started=false`;
- `auto_execution_enabled=false`;
- `auto_within_budget_enabled=false`;
- valid `execution_mode`;
- pinned `playbook_id`;
- present `strategy_family_version_id`;
- `installed_constraint_snapshot_id` exists;
- account facts freshness is acceptable;
- audit is writable.

Confirm may write only signal evaluation metadata:

- `signal_evaluated=true`
- `signal_generated=true`
- `runtime_status=signal_evaluated_no_intent`
- `signal_evaluated_at`
- `signal_evaluated_by_operation_id`
- `signal_evaluated_by_preflight_id`
- `signal_snapshot_json`
- `signal_evaluation_input_json`
- `signal_evaluation_summary_json`
- `trade_intent_created=false`
- `execution_intent_created=false`
- `order_created=false`
- `orders_placed=false`
- `trial_started=false`
- `auto_execution_enabled=false`
- `auto_within_budget_enabled=false`

Confirm must not create a trade intent, create an execution intent, create an
order, enable auto execution, mark `trial_started=true`, set order-capable
flags, enable live trading, cancel, close, flatten, withdraw, or transfer.
Repeated confirm is idempotent, and a new operation against an already
`signal_evaluated_no_intent` campaign returns noop semantics rather than
duplicating the evaluation record.

Phase 18 introduces Execution Permission Resolution and non-executable trial
trade intent recording for live read-only detection:

- `operation_type=record_trial_trade_intent_from_signal_evaluation`
- display name: `Record Trial Trade Intent From Signal Evaluation`
- `capability_status=operation_preflight_available`
- `executable_through_operation=true`
- confirmation phrase: `CONFIRM_RECORD_TRIAL_TRADE_INTENT`

Execution permission is monotonic and ordered as:

- `read_only`
- `signal_only`
- `intent_recording`
- `execution_intent_allowed`
- `order_allowed`

`TRADING_ENV` continues to describe the connection environment, for example
simulation, testnet, or live. `BRC_EXECUTION_PERMISSION_MAX` describes the
maximum allowed action depth in the BRC execution chain. The two settings are
intentionally separate: live connectivity does not imply permission to record
intents, create execution intents, or place orders.

The live read-only detection target configuration is:

```text
TRADING_ENV=live
BRC_EXECUTION_PERMISSION_MAX=intent_recording
```

The operation layer calls `ExecutionPermissionResolver` with
`requested_permission=intent_recording`. The resolver combines configured max,
API key capability, account facts/reconciliation, risk/capital constraints,
runtime safety, and operation-specific permission. `final_permission` is the
minimum contributor permission. Unknown contributors fail closed to a safe lower
level; unknown API key capability cannot produce `execution_intent_allowed` or
`order_allowed`.

Preflight requires:

- campaign exists;
- campaign metadata exists and is admission-created;
- `runtime_status=signal_evaluated_no_intent`;
- `signal_evaluated=true`;
- `signal_generated=true`;
- `trade_intent_created=false`, unless already idempotently recorded;
- `trial_trade_intent_created=false`, unless already idempotently recorded;
- `execution_intent_created=false`;
- `order_created=false`;
- `orders_placed=false`;
- `trial_started=false`;
- `auto_execution_enabled=false`;
- `auto_within_budget_enabled=false`;
- valid `execution_mode`;
- pinned `playbook_id`;
- present `strategy_family_version_id`;
- `installed_constraint_snapshot_id` exists;
- account facts freshness is acceptable;
- audit is writable;
- `ExecutionPermissionResolution.final_permission >= intent_recording`.

Execution mode behavior remains non-executable:

- `observe_only` records a would-have-traded intent with `decision=recorded`
  and `not_executed_reason=observe_only`;
- `no_entry` records entry/increase as `decision=blocked` with
  `not_executed_reason=no_entry`; exit/reduce can be recorded only as evidence;
- `auto_within_budget` records a candidate evidence intent with
  `not_executed_reason=live_read_only_detection_no_execution`; actual auto
  execution remains disabled;
- `owner_confirm_each_entry` remains reserved and unavailable.

Confirm may create a `brc_trial_trade_intents` evidence record, store the
permission-resolution snapshot, and write campaign metadata:

- `trial_trade_intent_created=true`
- `trade_intent_created=true`
- `runtime_status=trial_trade_intent_recorded_no_execution`
- `execution_permission=<final_permission>`
- `execution_permission_resolution`
- `execution_intent_created=false`
- `order_created=false`
- `orders_placed=false`
- `trial_started=false`
- `auto_execution_enabled=false`
- `auto_within_budget_enabled=false`

The `brc_trial_trade_intents` table is an evidence ledger only. It is not an
order table, does not feed execution intents or orders, and does not make a
strategy order-capable. Owner confirmation cannot raise permission above the
resolver result.

## BRC-R5-003 Phase 1: Live Read-only Detection Runner

BRC-R5-003 Phase 1 pauses the trading execution chain and adds a local
read-only detection runner skeleton:

- service: `BrcLiveReadOnlyDetectionRunner`
- read provider: `ExchangeGatewayReadOnlySnapshotProvider`
- module: `src/application/brc_live_read_only_detection_runner.py`
- scope: one `campaign_id` or `binding_id`, limited symbols, manual start,
  fixed interval, local process only
- authority: existing BRC Operation Layer operations
- output: signal evaluation evidence, execution-permission resolution snapshot,
  optional trial trade intent evidence

Required local environment:

```text
TRADING_ENV=live
BRC_EXECUTION_PERMISSION_MAX=intent_recording
EXCHANGE_TESTNET=false
EXCHANGE_NAME=binance
```

The runner refuses to start unless
`BRC_EXECUTION_PERMISSION_MAX=intent_recording` exactly. Lower permissions
cannot record trial trade intent evidence. Higher permissions are also refused
because this runner is specifically a live read-only detection runner, not an
execution runner. A higher resolver capability must be handled by a separate
future operation and runner.

`ExchangeGatewayReadOnlySnapshotProvider` wraps only existing read methods:

- `fetch_account_balance`
- `fetch_positions`
- `fetch_open_orders`
- `fetch_ticker_price`

It does not call `create_order`, `place_order`, `cancel_order`, close, flatten,
withdrawal, or transfer methods.

Each iteration:

1. verifies runner config is live read-only intent-recording mode;
2. reads live market snapshot and live account facts through injected read-only
   providers;
3. checks audit writability;
4. checks pause, stop, hard-lock, emergency-stop, and global-kill-switch style
   runtime safety flags when available;
5. calls `evaluate_signal_from_admission_strategy`;
6. calls `record_trial_trade_intent_from_signal_evaluation` only if the
   Operation Layer preflight and `ExecutionPermissionResolution` allow
   `intent_recording`;
7. records iteration evidence.

The runner provides signal evaluation input snapshots:

- symbol
- timestamp
- market snapshot
- account facts snapshot
- runtime safety snapshot
- runner iteration id

The trial trade intent operation remains the permission boundary. If
`final_permission < intent_recording`, the runner records skipped evidence and
does not write `brc_trial_trade_intents`.

The runner must never call execution-intent or order APIs. It also asserts that
operation results do not report:

- `execution_intent_created=true`
- `order_created=true`
- `orders_placed=true`
- `auto_execution_enabled=true`

The runner does not implement:

- multi-strategy scheduling
- server daemon mode
- auto start on boot
- Feishu control
- LLM strategy selection
- execution-intent conversion
- order placement
- cancel, close, flatten, withdrawal, or transfer

How to run in this phase is intentionally local-code only: instantiate
`BrcLiveReadOnlyDetectionRunner` with the existing BRC `BrcOperationService`, a
live read-only market/account snapshot provider, an audit-writable check, and a
runtime-safety reader. No HTTP trading endpoint is added.

## BRC-R5 Safety Hardening: Execution Bypass Fixes

Before entering live read-only observation and strategy-family design, BRC-R5
adds two defense layers against signal-to-order bypasses:

- `main.py` only binds `SignalPipeline.signal_executor` when
  `BRC_EXECUTION_PERMISSION_MAX=order_allowed`.
- For `read_only`, `signal_only`, and `intent_recording`, the pipeline executor
  is explicitly `None`.
- `ExecutionOrchestrator.execute_signal` now checks BRC execution permission at
  method entry. When permission is below `order_allowed`, it returns a blocked
  result with reason `BRC_EXECUTION_PERMISSION_NOT_ORDER_ALLOWED` before capital
  checks, local order creation, exchange submission, or order lifecycle calls.

This is defense-in-depth. Even if a caller bypasses the pipeline wiring gate,
`execute_signal` itself still refuses the signal-to-order path unless the
configured permission is `order_allowed`.

`dev_testnet_router` is mounted at `/api/dev/testnet/brc` and remains
operator-session protected. Endpoint audit:

| Method | Path | Classification | `gateway.place_order` | `execute_signal` | cancel/close/flatten/transfer |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/dev/testnet/brc/campaigns` | metadata-write | no direct call | no | no |
| POST | `/api/dev/testnet/brc/switch-playbook` | metadata-write | no direct call | no | no |
| POST | `/api/dev/testnet/brc/{symbol_key}/arm-attempt` | metadata-write | no direct call | no | no |
| POST | `/api/dev/testnet/brc/{symbol_key}/execute-controlled-entry` | testnet-controlled, order-capable through gated orchestrator | indirect through orchestrator when gates pass | yes | no |
| POST | `/api/dev/testnet/brc/{symbol_key}/execute-controlled-close` | testnet-controlled close through gated orchestrator | no direct entry call | no | controlled close only |
| POST | `/api/dev/testnet/brc/mock-pnl` | metadata-write | no direct call | no | no |
| POST | `/api/dev/testnet/brc/finalize` | metadata-write | no direct call | no | no |

Audit conclusion: `dev_testnet_router` does expose controlled testnet
entry/close endpoints by design, but they live under the dev/testnet prefix,
require operator session and mutation gates, and are not generic Owner Console
production order/cancel/close/flatten/withdrawal/transfer endpoints. The new
`execute_signal` permission defense also blocks the controlled-entry path when
BRC execution permission is below `order_allowed`.

## Unsupported Future Phases

Phase 18 / BRC-R5-003 Phase 1 still do not implement:

- runtime execution
- live enablement
- trading endpoints
- auto execution runtime
- owner-confirm-each-entry execution
- `create_gated_trial_from_admission` runtime execution
- actual runtime trial creation
- runtime carrier creation
- runtime carrier switching
- strategy runner installation
- execution-intent conversion
- order-capable strategy execution
- executable observe_only runtime feed
- executable no_entry runtime gate integration
- withdrawal or transfer
- LLM direct execution

## Safety Boundaries

Live funded validation rejects when account facts are unavailable. Testnet
incomplete evidence degrades to warnings and constrained admission instead of
automatic rejection when the adapter can bound it safely.

YAML is not a production source of truth for admission facts.

The next step is separately authorized signal-to-trial-trade-intent conversion
behind Operation Layer, not direct trading execution.
