# ADR-0013: BRC-R5-002 Admission Gate Phase 1

Date: 2026-05-27

Status: Accepted for Phase 1 implementation; amended through Phase 17 signal evaluation

## Context

BRC-R5-002 introduces a Strategy Family Trial Admission Gate for the Owner Console.
The product meaning is not strict strategy approval. It is a funded validation
admission system: when uncertainty can be bounded by budget, execution mode,
review, evidence, and constraints, the system should prefer `admit_with_constraints`
over rejection.

The current BRC stack already has Operation Layer, Account Facts/Reconciliation,
review evidence, runtime stop, dry-run flattening, and bounded campaign ledgers.
Phase 1 must add PG-backed admission facts and a small evaluation skeleton
without creating runtime/campaign trials or enabling live execution.

## Decisions

### D1 Trial Environment Mapping

The admission domain uses `trial_env = testnet | live`. Runtime/deployment still
uses the existing `TRADING_ENV = simulation | live` boundary. Testnet is modeled
as `trial_env=testnet` in admission and maps later to runtime
`TRADING_ENV=simulation` plus an explicit exchange-testnet flag such as
`exchange_testnet=true`.

The mapping belongs at the Operation/runtime installation boundary, not inside
strategy family facts. Phase 1 only stores admission intent.

### D2 Trial Stage

Only two stages exist:

- `development_validation`
- `funded_validation`

`production_observation` is not introduced. `observe_only` is an execution mode,
not a stage.

### D3 Execution Mode

Execution modes are:

- `auto_within_budget`
- `owner_confirm_each_entry`
- `observe_only`
- `no_entry`

`auto_within_budget` is the funded-validation default, but future runtime/risk
gates must enforce it from installed trial constraints. Strategy family code must
not self-police budget, notional, leverage, exposure, or attempt limits.

`owner_confirm_each_entry` is reserved only. Phase 1 persists the enum but
implements no execution behavior.

`observe_only` records trade intent later and places no orders. `no_entry`
blocks new entry. `propose_only` is not retained.

### D4 Risk / Capital Integration

Admission Gate does not compute sizing. It outputs:

- `risk_intent`
- `degradation_intent`
- `requested_risk_profile`

Concrete constraints are resolved through a `RiskCapitalAdapter` interface. The
Phase 1 default adapter returns `pending_risk_capital_resolution` and explicitly
does not fake sizing.

Trial constraint snapshot statuses are:

- `pending_risk_capital_resolution`
- `installable`
- `installed`
- `expired`
- `invalidated`

Phase 1 supports `pending_risk_capital_resolution` and `installable`. Operation
confirm must not accept a pending constraint snapshot.

Phase 2 adds the default `BrcAdmissionRiskCapitalAdapter`. It may return
conservative non-live installable fallback constraints for testnet development
validation. For live funded validation, it may return installable only when
account facts are clean and an explicit risk/capital resolution provides
concrete loss budget, notional, leverage, and attempt limits. Otherwise it
returns pending. AdmissionService remains an orchestrator and does not become a
sizing engine.

### D5 PG-backed Facts

The Phase 1 production fact source is PG. YAML may be used only for seed,
fixture, or export material.

Phase 1 creates separate tables for:

- strategy families
- strategy family versions
- admission rule configs
- admission requests
- owner market regime inputs
- evidence packets
- admission decisions
- trial constraint snapshots
- owner risk acceptances
- admission audit log

Phase 1 stores regime contracts, safeguards, degradation policy, evidence
payload, rule details, risk disclosure, known gaps, warnings/blockers, and
constraint details as JSONB so the model can evolve without premature table
explosion.

### D6 Strategy Family And Playbook

Admission decisions must be pinned to `strategy_family_version_id`.

Phase 1 allows `playbook_id + playbook_catalog_snapshot_json` on strategy family
version and request. Before a future `create_gated_trial_from_admission`
operation can install runtime state, the playbook must be pinned by id and
snapshot.

### D7 Trial Carrier

Phase 1 does not create a parallel trial runtime subsystem. Future installation
should first consider reusing/extending the existing `BoundedRiskCampaign`
carrier and adding an admission-to-campaign binding, rather than introducing an
independent trial carrier.

Phase 4 adds `brc_admission_trial_bindings` as that binding skeleton. The
initial confirm path can create only `binding_reserved`, with nullable
`campaign_id` and `runtime_carrier_id`. `binding_reserved` is not a trial-started
state and must not imply campaign creation, runtime carrier creation, runtime
constraint installation, order placement, or live execution.

Phase 5 reuses `BoundedRiskCampaign` as the campaign carrier shell instead of
creating a parallel trial subsystem. It adds campaign metadata so a campaign can
be marked `created_from_admission=true`, linked to the admission binding,
decision, strategy family version, playbook, and constraint snapshot, and kept
explicitly non-runtime with `runtime_status=not_installed`,
`strategy_status=not_active`, `constraints_installed=false`, and
`orders_placed=false`.

Phase 6 installs the campaign-created admission constraint snapshot as metadata
only. It sets `constraints_installed=true`,
`installed_constraint_snapshot_id`, `installed_at`, `installed_by_operation_id`,
and `runtime_status=constraints_installed_not_started`, and advances the binding
to `runtime_constraints_installed`. This state is explicitly not runtime
started, not strategy active, not trial started, not order-capable, and not
`auto_within_budget`.

Phase 7 prepares runtime carrier readiness as campaign metadata only. It sets
`carrier_ready=true`, `runtime_status=carrier_ready_not_started`,
`prepared_at`, `prepared_by_operation_id`, and `prepared_by_preflight_id`.
`carrier_ready` is not a binding status and does not mean runtime started,
strategy active, trial started, live enabled, auto execution enabled, or
order-capable.

Phase 8 prepares runtime start readiness as campaign metadata only. It sets
`runtime_start_ready=true`,
`runtime_status=runtime_start_ready_not_started`, `start_ready_at`,
`start_ready_by_operation_id`, and `start_ready_by_preflight_id`.
`runtime_start_ready` is not a binding status and does not mean runtime started,
strategy active, trial started, live enabled, auto execution enabled, or
order-capable.

Phase 9 defines the execution-mode enforcement contract and adds
`brc_trial_trade_intents` as a non-executable evidence ledger. `observe_only`
records would-have-traded evidence, `no_entry` blocks entry/increase while
allowing non-executable exit/reduce records, `auto_within_budget` checks
installed constraint completeness only, and `owner_confirm_each_entry` remains
reserved/unavailable. Trial trade intents are not orders and must not feed order
execution.

Phase 10 prepares runtime handoff readiness as campaign metadata only. It sets
`runtime_handoff_ready=true`,
`runtime_status=runtime_handoff_ready_not_started`, `handoff_ready_at`,
`handoff_ready_by_operation_id`, and `handoff_ready_by_preflight_id`.
`runtime_handoff_ready` is not a binding status and does not mean runtime
started, strategy active, trial started, live enabled, auto execution enabled,
or order-capable.

### D8 Operation Layer Integration

Future work should add `operation_type=create_gated_trial_from_admission`.
Preflight must verify admission decision, installable constraints, owner risk
acceptance when funded validation is requested, account facts boundaries, and
runtime/campaign eligibility.

Phase 3 registers `operation_type=create_gated_trial_from_admission` as
preflight-only. Phase 4 upgrades it to binding-reservation-only:

- `capability_status=binding_reservation_available`
- `executable_through_operation=true`
- `confirmation_phrase=CONFIRM_RESERVE_ADMISSION_BINDING`

Preflight still validates readiness, installable constraints, risk acceptance,
playbook pinning, account facts, audit writability, and active campaign
conflicts. It also blocks an existing active binding for the same admission
decision. Confirm may persist only a `binding_reserved` admission-trial binding
and must not create trials/campaigns, install runtime constraints, switch
carriers, place orders, enable live execution, or mutate runtime state.

Phase 5 introduces a separate operation,
`operation_type=create_campaign_from_admission_binding`, rather than overloading
`create_gated_trial_from_admission`. This keeps binding reservation and campaign
carrier creation distinct in audit and idempotency semantics. Preflight requires
an existing `binding_reserved`, an admissible non-expired decision, an
`installable` constraint snapshot, valid funded Owner risk acceptance, pinned
playbook, no existing campaign on the binding, acceptable live funded account
facts when applicable, audit writability, and no active conflicting BRC campaign
when checkable. Confirm may create only a BRC campaign shell and advance the
binding to `campaign_created`; it must not install runtime constraints, switch a
runtime carrier, start strategy execution, place orders, enable live, withdraw,
or transfer.

Phase 6 introduces a separate operation,
`operation_type=install_runtime_constraints_from_admission_campaign`. Preflight
requires an existing `campaign_created` binding, linked campaign metadata whose
admission refs match the binding, an `installable` constraint snapshot, valid
Owner risk acceptance when funded validation is requested, matching
`strategy_family_version_id`, a pinned playbook, acceptable account facts,
writable audit, no non-idempotent prior constraint installation, and no active
conflicting runtime carrier when checkable. Confirm may write constraints
metadata and advance the binding to `runtime_constraints_installed`; it must not
start runtime, activate strategy, create orders, enable live, install an
executable strategy runner, change execution state to active, cancel, close,
flatten, withdraw, or transfer.

Phase 7 introduces a separate operation,
`operation_type=prepare_runtime_carrier_from_admission_campaign`. Preflight
requires an existing `runtime_constraints_installed` binding, linked campaign
metadata with `constraints_installed=true`,
`runtime_status=constraints_installed_not_started`, false runtime/strategy/trial
and order flags, installed constraint snapshot id, strategy-family version,
pinned playbook, allowed execution mode, fresh account facts, writable audit,
inactive runtime, and no conflicting active runtime carrier when checkable.
Confirm may write carrier readiness metadata and audit refs; it must not start
runtime, activate strategy, install a strategy runner, create orders, enable
live, change runtime state to active, mark trial started, cancel, close, flatten,
withdraw, or transfer.

Phase 8 introduces a separate operation,
`operation_type=prepare_runtime_start_from_admission_carrier`. Preflight
requires an existing `runtime_constraints_installed` binding, linked campaign
metadata with `carrier_ready=true`,
`runtime_status=carrier_ready_not_started`, false runtime/strategy/trial/order
flags, installed constraints, installed constraint snapshot id, allowed
execution mode, fresh account facts, writable audit, and no conflicting active
runtime/trial/strategy when checkable. Confirm may write runtime start
readiness metadata and audit refs; it must not start runtime, activate strategy,
install a strategy runner, create orders, enable live, change runtime state to
active, mark trial started, cancel, close, flatten, withdraw, or transfer.

Phase 9 introduces a separate operation,
`operation_type=evaluate_trial_trade_intent`. Preflight requires a
runtime-start-ready admission campaign, false runtime/strategy/order flags, a
modeled `execution_mode`, installed constraint snapshot, and writable audit.
Confirm may record `observe_only` / `no_entry` trial trade intent evidence or
return an `auto_within_budget` constraints-completeness check. It must not start
runtime, activate strategy, enable auto execution, create orders, create
execution intents, create live paths, mark trial started, cancel, close,
flatten, withdraw, or transfer.

Phase 10 introduces a separate operation,
`operation_type=prepare_runtime_handoff_from_admission_campaign`. Preflight
requires a runtime-start-ready admission campaign, false runtime/strategy/trial
and order flags, installed constraints, a modeled `execution_mode`, available
execution-mode enforcement contract, writable audit, fresh account facts, and no
conflicting active runtime/trial when checkable. Confirm may write runtime
handoff readiness metadata and audit refs; it must not start runtime, set
`runtime_started=true`, activate strategy, set `strategy_active=true`, enable
auto execution, create orders, create execution intents, enable live, mark trial
started, cancel, close, flatten, withdraw, or transfer.

Phase 11 introduces a separate preflight-only operation,
`operation_type=start_runtime_from_admission_handoff`. Preflight requires a
handoff-ready admission campaign, `runtime_status=runtime_handoff_ready_not_started`,
false runtime/strategy/trial/order flags, installed constraints, carrier and
runtime-start readiness metadata, a valid `execution_mode`, available
execution-mode enforcement contract, writable audit, acceptable account facts
freshness, safe runtime profile/environment mapping, no conflicting active
runtime/trial, and no emergency stop or hard lock when checkable. Confirm is
disabled/not implemented and must return blocked/unavailable semantics. Phase 11
must not start runtime, set `runtime_started=true`, activate strategy, set
`strategy_active=true`, enable auto execution, create orders, create execution
intents, mark trial started, enable live, cancel, close, flatten, withdraw, or
transfer. `runtime_handoff_ready_not_started` remains the latest actual state.

Phase 12 upgrades `operation_type=start_runtime_from_admission_handoff` from
preflight-only to a runtime-state-only transition. Confirm may set
`runtime_started=true`, `runtime_status=runtime_started_strategy_inactive`,
`runtime_started_at`, `runtime_started_by_operation_id`, and
`runtime_started_by_preflight_id`, with explicit false strategy/trial/order/auto
flags. It must not activate a strategy runner, set `strategy_active=true`, mark
`trial_started=true`, enable auto execution, create orders, create execution
intents, enable live trading, cancel, close, flatten, withdraw, or transfer.
`runtime_started_strategy_inactive` is not strategy active, not trial started,
and not order-capable.

Phase 12.5 records the alignment boundary: admission binding status remains an
admission/constraints milestone and is not promoted to runtime-started. Runtime
state is represented by campaign metadata. After Phase 12, the binding can remain
`runtime_constraints_installed` while campaign metadata records
`runtime_started=true` and `runtime_status=runtime_started_strategy_inactive`.
This split is intentional and prevents runtime state from being mistaken for
strategy activation, trial start, auto execution, live enablement, order
capability, or an execution-intent source.

Phase 13 introduces
`operation_type=prepare_strategy_activation_from_admission_runtime` as a
metadata-only readiness operation. Preflight requires
`runtime_started=true`, `runtime_status=runtime_started_strategy_inactive`,
false strategy/trial/order/auto flags, valid `execution_mode`, pinned
`playbook_id`, present `strategy_family_version_id`,
`installed_constraint_snapshot_id`, acceptable account facts freshness, writable
audit, no active strategy conflict when checkable, and no unresolved safety
blockers. Confirm may set `strategy_activation_ready=true`,
`runtime_status=strategy_activation_ready_not_active`,
`strategy_activation_ready_at`, `strategy_activation_ready_by_operation_id`, and
`strategy_activation_ready_by_preflight_id`, while preserving
`strategy_active=false`, `trial_started=false`, `orders_placed=false`,
`auto_execution_enabled=false`, and `auto_within_budget_enabled=false`. It must
not activate a strategy runner, start a signal loop, create trade intents,
create execution intents, create orders, enable auto execution, enable live,
cancel, close, flatten, withdraw, or transfer.

`strategy_activation_ready_not_active` is not strategy active, not trial started,
not signal-loop active, not auto-execution-enabled, and not order-capable.

Phase 14 introduces `operation_type=activate_strategy_from_admission_runtime` as
a metadata-only non-execution strategy state transition. Preflight requires
`runtime_started=true`, `runtime_status=strategy_activation_ready_not_active`,
`strategy_activation_ready=true`, false trial/order/auto flags, valid
`execution_mode`, pinned `playbook_id`, present `strategy_family_version_id`,
`installed_constraint_snapshot_id`, acceptable account facts freshness, writable
audit, no active strategy conflict when checkable, and no already order-capable
state flags. Confirm may set `strategy_state=strategy_active_no_execution`,
`strategy_activation_state=active_no_execution`,
`runtime_status=strategy_active_no_execution`, and `strategy_active=true` only
with `strategy_execution_enabled=false`, `signal_loop_enabled=false`,
`signal_loop_started=false`, `trial_started=false`,
`auto_execution_enabled=false`, `auto_within_budget_enabled=false`,
`trade_intent_created=false`, `execution_intent_created=false`,
`order_created=false`, and `orders_placed=false`.

`strategy_active_no_execution` is not order-capable strategy, not signal-loop
active, not trial started, not auto-execution-enabled, and not live enabled.

Phase 15 introduces
`operation_type=prepare_signal_loop_from_admission_strategy` as a metadata-only
signal loop / observe gate readiness operation. Preflight requires
`runtime_status=strategy_active_no_execution`,
`strategy_activation_state=active_no_execution`, `strategy_active=true`, false
strategy-execution/signal-loop/trial/order/intent/auto flags, valid
`execution_mode`, pinned `playbook_id`, present `strategy_family_version_id`,
`installed_constraint_snapshot_id`, acceptable account facts freshness, writable
audit, and no active signal loop conflict when checkable. Confirm may set
`signal_loop_ready=true`, `runtime_status=signal_loop_ready_not_started`,
`signal_loop_ready_at`, `signal_loop_ready_by_operation_id`, and
`signal_loop_ready_by_preflight_id`, while preserving
`signal_loop_enabled=false`, `signal_loop_started=false`,
`signal_generated=false`, `strategy_execution_enabled=false`,
`trial_started=false`, `trade_intent_created=false`,
`execution_intent_created=false`, `order_created=false`, `orders_placed=false`,
`auto_execution_enabled=false`, and `auto_within_budget_enabled=false`.

`signal_loop_ready_not_started` is not signal-loop started, not signal
generation, not observe-only/no-entry intent behavior, not auto execution, and
not order-capable. Signal loop start is handled by the separate Phase 16
metadata-only transition; observe-gate runtime integration, order-capable
strategy execution, and `auto_within_budget` actual execution remain later
explicitly authorized runtime phases.

Phase 16 introduces
`operation_type=start_signal_loop_from_admission_strategy` as a metadata-only
signal loop start state operation. Preflight requires
`runtime_status=signal_loop_ready_not_started`, `signal_loop_ready=true`,
`strategy_state=strategy_active_no_execution`,
`strategy_activation_state=active_no_execution`, `strategy_active=true`, false
strategy-execution/signal-generated/trial/order/intent/auto flags, valid
`execution_mode`, pinned `playbook_id`, present `strategy_family_version_id`,
`installed_constraint_snapshot_id`, acceptable account facts freshness, writable
audit, and no active signal loop conflict when checkable. Confirm may set
`signal_loop_started=true`, `signal_loop_enabled=true`,
`signal_loop_enabled_scope=non_trading_loop_state`,
`runtime_status=signal_loop_started_no_signal`, `signal_loop_started_at`,
`signal_loop_started_by_operation_id`, and
`signal_loop_started_by_preflight_id`, while preserving
`signal_generated=false`, `trade_intent_created=false`,
`execution_intent_created=false`, `order_created=false`,
`orders_placed=false`, `strategy_execution_enabled=false`,
`trial_started=false`, `auto_execution_enabled=false`, and
`auto_within_budget_enabled=false`.

`signal_loop_started_no_signal` is not signal generation, not trade-intent
creation, not execution-intent creation, not trial started, not auto execution,
and not order-capable. Observe-only/no-entry actual intent behavior and
`auto_within_budget` actual execution remain later explicitly authorized runtime
phases.

Phase 17 introduces
`operation_type=evaluate_signal_from_admission_strategy` as a metadata-only
signal evaluation operation. Preflight requires
`runtime_status=signal_loop_started_no_signal`, `signal_loop_started=true`,
`signal_loop_enabled_scope=non_trading_loop_state`, `signal_generated=false`
unless already idempotently `signal_evaluated_no_intent`, false
trade-intent/execution-intent/order/trial/auto flags, valid `execution_mode`,
pinned `playbook_id`, present `strategy_family_version_id`,
`installed_constraint_snapshot_id`, acceptable account facts freshness, and
writable audit. Confirm may set `signal_evaluated=true`,
`signal_generated=true`, and `runtime_status=signal_evaluated_no_intent`, plus
`signal_evaluated_at`, operation/preflight refs, `signal_snapshot_json`,
`signal_evaluation_input_json`, and `signal_evaluation_summary_json`, while
preserving `trade_intent_created=false`, `execution_intent_created=false`,
`order_created=false`, `orders_placed=false`, `trial_started=false`,
`auto_execution_enabled=false`, and `auto_within_budget_enabled=false`.

`signal_evaluated_no_intent` is not a trade intent, not an execution intent, not
an order-capable state, not trial started, and not auto execution.
Observe-only/no-entry trade-intent conversion and `auto_within_budget` actual
execution remain later explicitly authorized runtime phases.

### D9 Observe-only And No-entry Enforcement

Phase 9 stores observe-only/no-entry trade intent evidence in
`brc_trial_trade_intents`. This table is a non-executable ledger only. Runtime
integration, order planning, and actual no-entry enforcement in live runtime
gates remain future phases.

### D10 Account Facts Hard Boundary

For `trial_env=live` plus `trial_stage=funded_validation`, unavailable account
facts must reject/block admission. Reconciliation mismatch or unknown unmanaged
exposure is also treated as a hard blocker for live funded validation.

For testnet, incomplete account/evidence facts should degrade to constraints,
observe-only/no-entry intent, warnings, or pending risk-capital resolution
instead of automatic rejection.

### D11 Owner Risk Acceptance

Funded validation requires Owner risk acceptance before future trial creation.
The Owner accepts the risk disclosure and computed/installable constraints. The
Owner does not manually declare total account size; account size must come from
account facts / exchange read models.

`create_gated_trial_from_admission` must check risk acceptance. Phase 1 persists
owner risk acceptance only when the referenced constraint snapshot is
`installable`.

## Consequences

Phase 1 adds PG facts, repository methods, read/create API endpoints, a
RiskCapitalAdapter interface, and an evaluation skeleton. It intentionally does
not enable runtime execution, live activation, trading endpoints, auto execution,
or campaign/trial creation.

The initial behavior can produce useful admission decisions before the final
Risk/Capital module exists, while preserving an explicit pending state so later
Operation Layer code cannot confuse unresolved risk with installable
constraints.
