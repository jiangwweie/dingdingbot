from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.brc_admission_service import (
    BrcAdmissionService,
    OwnerRiskAcceptanceInput,
    PendingRiskCapitalAdapter,
)
from src.application.bounded_risk_campaign_service import BoundedRiskCampaignService
from src.application.brc_operation_layer import (
    AdmissionRuntimeAdapterPayload,
    BrcOperationService,
    BudgetRevokeAdapterPayload,
    ConfirmationRequirement,
    FixedTestnetRehearsalAdapterPayload,
    InMemoryOperationRepository,
    OperationAdapterPayloadMetadata,
    OperationLayerError,
    OperationRecord,
    OperationLayerReaders,
    PreflightSnapshot,
    RuntimeStopAdapterPayload,
    SignalTradeIntentRecorderAdapterPayload,
    _admission_runtime_adapter_payload,
    _budget_revoke_adapter_payload,
    _fixed_testnet_rehearsal_adapter_payload,
    _operation_adapter_payload,
    _runtime_stop_adapter_payload,
    _signal_trade_intent_recorder_adapter_payload,
)
from src.application.execution_permission import ExecutionPermission, ExecutionPermissionResolver
from src.domain.brc_admission import (
    AdmissionDecisionValue,
    AdmissionExecutionMode,
    AdmissionTrialBinding,
    AdmissionTrialBindingStatus,
    TrialConstraintSnapshotStatus,
    TrialEnv,
    TrialStage,
)
from src.domain.bounded_risk_campaign import BrcCampaignStatus
from src.infrastructure.pg_models import PGBrcTrialConstraintSnapshotORM
from src.infrastructure.pg_brc_admission_repository import PgBrcAdmissionRepository
from tests.unit.test_brc_admission_phase1 import ADMISSION_TABLES, _seed_request
from tests.unit.test_brc_campaign_service import InMemoryBrcRepo


def _default_runtime_summary() -> dict:
    return {
        "runtime_bound": True,
        "profile": "brc_btc_eth_testnet_runtime",
        "testnet": True,
        "current_runtime_state": "observe",
        "gks_active": True,
        "startup_guard_armed": False,
        "runtime_control_api_enabled": True,
        "runtime_test_signal_injection_enabled": True,
        "live_ready": False,
    }


async def _async_dict(value: dict) -> dict:
    return dict(value)


async def _async_bool(value: bool) -> bool:
    return value


async def _campaign_service(*, create_campaign: bool = True):
    repo = InMemoryBrcRepo()
    service = BoundedRiskCampaignService(repo)
    await service.initialize()
    if create_campaign:
        await service.create_campaign(
            bucket_id="bucket",
            authorized_amount=Decimal("500"),
            max_campaign_loss=Decimal("120"),
            profit_protect_trigger=Decimal("100"),
            reason="test",
        )
    return service, repo


def test_operation_adapter_payload_centralizes_operation_metadata():
    operation = OperationRecord(
        operation_id="op-authority",
        operation_type="prepare_runtime_handoff_from_admission_campaign",
        requested_by="owner",
        requested_at_ms=1,
        input_params={
            "operation_id": "caller-stale-op",
            "authorization_source": "caller",
            "strategy_group_id": "MPG-001",
        },
        risk_level="medium",
        status="awaiting_confirmation",
        confirmed_by="owner-1",
    )
    preflight = PreflightSnapshot(
        preflight_id="pre-authority",
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        created_at_ms=1,
        expires_at_ms=2,
        decision="allow",
        confirmation_requirement=ConfirmationRequirement(required=False, expires_at_ms=2),
        snapshot_hash="snapshot-hash",
        idempotency_key="idempotency-key",
        summary="ready",
    )

    payload = _operation_adapter_payload(
        operation,
        preflight,
        {"execution_permission_resolution": {"permission": "intent_recording"}},
    )

    assert payload["strategy_group_id"] == "MPG-001"
    assert payload["operation_id"] == "op-authority"
    assert payload["preflight_id"] == "pre-authority"
    assert payload["confirmed_by"] == "owner-1"
    assert payload["authorization_source"] == "brc_operation_layer"
    assert payload["execution_permission_resolution"] == {"permission": "intent_recording"}
    assert operation.input_params["operation_id"] == "caller-stale-op"
    assert operation.input_params["authorization_source"] == "caller"


def test_operation_adapter_payload_metadata_is_typed_authority_boundary():
    metadata = OperationAdapterPayloadMetadata(
        operation_id="op-1",
        preflight_id="pre-1",
        confirmed_by="owner",
    )

    assert metadata.model_dump(mode="json") == {
        "operation_id": "op-1",
        "preflight_id": "pre-1",
        "confirmed_by": "owner",
        "authorization_source": "brc_operation_layer",
    }


def test_admission_runtime_adapter_payload_is_typed_non_live_boundary():
    operation = OperationRecord(
        operation_id="op-admission-runtime",
        operation_type="prepare_runtime_handoff_from_admission_campaign",
        requested_by="owner-typed",
        requested_at_ms=1,
        input_params={
            "admission_binding_id": "binding-1",
            "operation_id": "caller-stale-op",
            "authorization_source": "caller",
            "live_ready": True,
            "orders_placed": True,
            "execution_intent_created": True,
            "withdrawal_executed": True,
            "transfer_executed": True,
            "auto_execution_enabled": True,
        },
        risk_level="medium",
        status="awaiting_confirmation",
        confirmed_by="owner-confirmed",
    )
    preflight = PreflightSnapshot(
        preflight_id="pre-admission-runtime",
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        created_at_ms=1,
        expires_at_ms=2,
        decision="allow",
        confirmation_requirement=ConfirmationRequirement(required=False, expires_at_ms=2),
        snapshot_hash="snapshot-hash",
        idempotency_key="idempotency-key",
        summary="ready",
    )

    payload = _admission_runtime_adapter_payload(operation, preflight)

    assert AdmissionRuntimeAdapterPayload.model_validate(payload).model_dump(
        mode="json",
        exclude_none=True,
    ) == payload
    assert payload["admission_binding_id"] == "binding-1"
    assert payload["operation_id"] == "op-admission-runtime"
    assert payload["preflight_id"] == "pre-admission-runtime"
    assert payload["confirmed_by"] == "owner-confirmed"
    assert payload["authorization_source"] == "brc_operation_layer"
    assert payload["live_ready"] is False
    assert payload["orders_placed"] is False
    assert payload["execution_intent_created"] is False
    assert payload["withdrawal_executed"] is False
    assert payload["transfer_executed"] is False
    assert payload["auto_execution_enabled"] is False
    assert operation.input_params["authorization_source"] == "caller"


def test_admission_runtime_adapter_payload_does_not_expand_absent_safety_fields():
    operation = OperationRecord(
        operation_id="op-admission-runtime-minimal",
        operation_type="prepare_runtime_handoff_from_admission_campaign",
        requested_by="owner-typed",
        requested_at_ms=1,
        input_params={"admission_binding_id": "binding-2"},
        risk_level="medium",
        status="awaiting_confirmation",
        confirmed_by="owner-confirmed",
    )
    preflight = PreflightSnapshot(
        preflight_id="pre-admission-runtime-minimal",
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        created_at_ms=1,
        expires_at_ms=2,
        decision="allow",
        confirmation_requirement=ConfirmationRequirement(required=False, expires_at_ms=2),
        snapshot_hash="snapshot-hash",
        idempotency_key="idempotency-key",
        summary="ready",
    )

    payload = _admission_runtime_adapter_payload(operation, preflight)

    assert payload == {
        "admission_binding_id": "binding-2",
        "operation_id": "op-admission-runtime-minimal",
        "preflight_id": "pre-admission-runtime-minimal",
        "confirmed_by": "owner-confirmed",
        "authorization_source": "brc_operation_layer",
    }


def test_signal_trade_intent_recorder_payload_is_typed_permission_boundary():
    operation = OperationRecord(
        operation_id="op-signal-intent",
        operation_type="record_trial_trade_intent_from_signal_evaluation",
        requested_by="owner-typed",
        requested_at_ms=1,
        input_params={
            "admission_binding_id": "binding-3",
            "execution_permission_resolution": {"permission": "caller-stale"},
            "live_ready": True,
            "order_created": True,
        },
        risk_level="medium",
        status="awaiting_confirmation",
        confirmed_by="owner-confirmed",
    )
    preflight = PreflightSnapshot(
        preflight_id="pre-signal-intent",
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        created_at_ms=1,
        expires_at_ms=2,
        decision="allow",
        confirmation_requirement=ConfirmationRequirement(required=False, expires_at_ms=2),
        snapshot_hash="snapshot-hash",
        idempotency_key="idempotency-key",
        summary="ready",
        after={"execution_permission_resolution": {"permission": "intent_recording"}},
    )

    payload = _signal_trade_intent_recorder_adapter_payload(operation, preflight)

    assert SignalTradeIntentRecorderAdapterPayload.model_validate(payload).model_dump(
        mode="json",
        exclude_none=True,
    ) == payload
    assert payload["operation_id"] == "op-signal-intent"
    assert payload["preflight_id"] == "pre-signal-intent"
    assert payload["authorization_source"] == "brc_operation_layer"
    assert payload["execution_permission_resolution"] == {"permission": "intent_recording"}
    assert payload["live_ready"] is False
    assert payload["order_created"] is False


def test_budget_revoke_adapter_payload_is_typed_safe_executor_boundary():
    operation = OperationRecord(
        operation_id="op-budget",
        operation_type="revoke_budget",
        requested_by="owner-2",
        requested_at_ms=1,
        input_params={
            "reason": "owner revoke budget",
            "operation_id": "caller-stale-op",
            "authorization_source": "caller",
            "places_orders": True,
            "withdrawal_executed": True,
            "live_ready": True,
        },
        risk_level="medium",
        status="awaiting_confirmation",
        confirmed_by="owner-2",
    )
    preflight = PreflightSnapshot(
        preflight_id="pre-budget",
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        created_at_ms=1,
        expires_at_ms=2,
        decision="warn",
        confirmation_requirement=ConfirmationRequirement(required=False, expires_at_ms=2),
        snapshot_hash="snapshot-hash",
        idempotency_key="idempotency-key",
        summary="ready",
    )

    payload = _budget_revoke_adapter_payload(operation, preflight)

    assert BudgetRevokeAdapterPayload.model_validate(payload).model_dump(mode="json") == payload
    assert payload["reason"] == "owner revoke budget"
    assert payload["operation_id"] == "op-budget"
    assert payload["preflight_id"] == "pre-budget"
    assert payload["confirmed_by"] == "owner-2"
    assert payload["authorization_source"] == "brc_operation_layer"
    assert payload["revoked_by"] == "owner-2"
    assert payload["places_orders"] is False
    assert payload["closes_positions"] is False
    assert payload["cancels_orders"] is False
    assert payload["withdrawal_executed"] is False
    assert payload["transfer_executed"] is False
    assert payload["live_ready"] is False


def test_fixed_testnet_rehearsal_adapter_payload_is_typed_safe_executor_boundary():
    operation = OperationRecord(
        operation_id="op-fixed-rehearsal",
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner-3",
        requested_at_ms=1,
        input_params={
            "source": "fixed_rehearsal_page",
            "operation_id": "caller-stale-op",
            "authorization_source": "caller",
            "workflow_carrier_role": "external_carrier",
            "allowed_symbols": ["DOGE/USDT:USDT"],
            "live_ready": True,
        },
        risk_level="medium",
        status="awaiting_confirmation",
        confirmed_by="owner-3",
    )
    preflight = PreflightSnapshot(
        preflight_id="pre-fixed-rehearsal",
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        created_at_ms=1,
        expires_at_ms=2,
        decision="allow",
        confirmation_requirement=ConfirmationRequirement(required=False, expires_at_ms=2),
        snapshot_hash="snapshot-hash",
        idempotency_key="idempotency-key",
        summary="ready",
    )

    payload = _fixed_testnet_rehearsal_adapter_payload(operation, preflight)

    assert FixedTestnetRehearsalAdapterPayload.model_validate(payload).model_dump(mode="json") == payload
    assert payload["source"] == "fixed_rehearsal_page"
    assert payload["operation_id"] == "op-fixed-rehearsal"
    assert payload["preflight_id"] == "pre-fixed-rehearsal"
    assert payload["confirmed_by"] == "owner-3"
    assert payload["authorization_source"] == "brc_operation_layer"
    assert payload["idempotency_key"] == "idempotency-key"
    assert payload["workflow_carrier_role"] == "internal_ref_only"
    assert payload["allowed_symbols"] == ["ETH/USDT:USDT", "BTC/USDT:USDT"]
    assert payload["live_ready"] is False


def test_runtime_stop_adapter_payload_is_typed_safe_executor_boundary():
    operation = OperationRecord(
        operation_id="op-runtime-stop",
        operation_type="emergency_stop_runtime",
        requested_by="owner-4",
        requested_at_ms=1,
        input_params={
            "reason": "owner emergency stop",
            "operation_id": "caller-stale-op",
            "authorization_source": "caller",
            "updated_by": "caller",
            "does_not_flatten": False,
            "does_not_cancel_orders": False,
            "does_not_place_orders": False,
            "does_not_withdraw_or_transfer": False,
            "live_ready": True,
        },
        risk_level="medium",
        status="awaiting_confirmation",
        confirmed_by="owner-4",
    )
    preflight = PreflightSnapshot(
        preflight_id="pre-runtime-stop",
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        created_at_ms=1,
        expires_at_ms=2,
        decision="allow",
        confirmation_requirement=ConfirmationRequirement(required=False, expires_at_ms=2),
        snapshot_hash="snapshot-hash",
        idempotency_key="idempotency-key",
        summary="ready",
    )

    payload = _runtime_stop_adapter_payload(operation, preflight)

    assert RuntimeStopAdapterPayload.model_validate(payload).model_dump(mode="json") == payload
    assert payload["reason"] == "owner emergency stop"
    assert payload["operation_id"] == "op-runtime-stop"
    assert payload["preflight_id"] == "pre-runtime-stop"
    assert payload["confirmed_by"] == "owner-4"
    assert payload["authorization_source"] == "brc_operation_layer"
    assert payload["idempotency_key"] == "idempotency-key"
    assert payload["updated_by"] == "owner-4"
    assert payload["does_not_flatten"] is True
    assert payload["does_not_cancel_orders"] is True
    assert payload["does_not_place_orders"] is True
    assert payload["does_not_withdraw_or_transfer"] is True
    assert payload["live_ready"] is False


async def _operation_service(
    *,
    market_state: dict | None = None,
    audit_writable: bool = True,
    ttl_ms: int = 300_000,
    runtime_adapter: bool = True,
    runtime_stop_adapter: bool = False,
    runtime_stop_failure: Exception | None = None,
    fixed_rehearsal_adapter: bool = False,
    fixed_rehearsal_failure: Exception | None = None,
    budget_adapter: bool = True,
    budget_revoke_adapter: bool = True,
    budget_authorization_status: str | None = "active_metadata_only",
    create_campaign: bool = True,
    runtime_state: dict | None = None,
    admission_readiness=None,
    admission_binding_reserver=None,
    admission_campaign_readiness=None,
    admission_campaign_creator_factory=None,
    admission_runtime_constraint_readiness=None,
    admission_runtime_constraint_installer_factory=None,
    admission_runtime_carrier_readiness=None,
    admission_runtime_carrier_preparer_factory=None,
    admission_runtime_start_readiness=None,
    admission_runtime_start_preparer_factory=None,
    trial_trade_intent_readiness=None,
    trial_trade_intent_evaluator_factory=None,
    admission_runtime_handoff_readiness=None,
    admission_runtime_handoff_preparer_factory=None,
    admission_runtime_start_from_handoff_readiness=None,
    admission_runtime_start_from_handoff_starter_factory=None,
    admission_strategy_activation_readiness=None,
    admission_strategy_activation_preparer_factory=None,
    admission_strategy_state_activation_readiness=None,
    admission_strategy_state_activator_factory=None,
    admission_signal_loop_readiness=None,
    admission_signal_loop_preparer_factory=None,
    admission_signal_loop_start_readiness=None,
    admission_signal_loop_starter_factory=None,
    admission_signal_evaluation_readiness=None,
    admission_signal_evaluator_factory=None,
    signal_trade_intent_readiness=None,
    signal_trade_intent_recorder_factory=None,
    runtime_safety_readiness=None,
    execution_permission_max: ExecutionPermission | None = None,
    brc_service: BoundedRiskCampaignService | None = None,
    brc_repo_existing=None,
):
    if brc_service is None:
        brc, brc_repo = await _campaign_service(create_campaign=create_campaign)
    else:
        brc = brc_service
        brc_repo = brc_repo_existing
    op_repo = InMemoryOperationRepository()
    market = market_state if market_state is not None else {
        "active_position_count": 0,
        "open_order_count": 0,
        "all_local_flat": True,
        "data_source": "unit",
        "source": "local_pg",
        "truth_level": "summary",
        "reconciliation_status": {"status": "not_available"},
    }
    runtime = _default_runtime_summary()
    runtime.update(runtime_state or {})
    fixed_rehearsal_calls = []
    runtime_stop_calls = []
    budget_revoke_calls = []
    budget_state = {
        "latest_budget_authorization": (
            {
                "budget_authorization_id": "budget-1",
                "status": budget_authorization_status,
                "updated_at_ms": 1780496600000,
                "live_ready": False,
                "auto_execution_enabled": False,
                "order_permission_granted": False,
                "execution_permission_granted": False,
                "execution_intent_created": False,
                "order_created": False,
                "metadata_only": True,
            }
            if budget_authorization_status is not None
            else None
        ),
        "eligible_carrier_ids": ["MI-001-BNB-LONG"],
        "disabled_execution_state": {
            "live_ready": False,
            "auto_execution_enabled": False,
            "order_permission_granted": False,
            "execution_permission_granted": False,
        },
        "budget_scope_source": "pg_metadata",
    }

    async def _runtime_summary():
        return dict(runtime)

    async def _market_summary():
        return dict(market)

    async def _audit_writable():
        return audit_writable

    async def _review_artifact(_input):
        return {"packet": "review", "mutation_executed": False, "live_ready": False}

    async def _runtime_transition(target_state, input_params):
        runtime["current_runtime_state"] = target_state
        return {
            "status": target_state,
            "operation_id": input_params["operation_id"],
            "preflight_id": input_params["preflight_id"],
            "places_orders": False,
            "live_ready": False,
        }

    async def _budget_summary():
        latest = budget_state.get("latest_budget_authorization")
        return {
            **budget_state,
            "latest_budget_authorization": dict(latest) if isinstance(latest, dict) else None,
            "available": latest is not None,
            "ready": latest is not None,
            "source": "pg_metadata",
        }

    async def _budget_revoke(input_params):
        budget_revoke_calls.append(dict(input_params))
        latest = budget_state.get("latest_budget_authorization")
        if latest is None:
            raise RuntimeError("No current budget authorization metadata exists to revoke.")
        already_revoked = latest.get("status") == "revoked"
        if not already_revoked:
            latest.update(
                {
                    "status": "revoked",
                    "revoked_at_ms": 1780496700000,
                    "revoked_by": input_params.get("revoked_by"),
                    "revoke_reason": input_params.get("reason"),
                    "last_control_operation_id": input_params.get("operation_id"),
                    "updated_at_ms": 1780496700000,
                }
            )
        return {
            **latest,
            "already_revoked": already_revoked,
            "budget_effective_state": "revoked",
            "future_budgeted_actions_allowed": False,
            "places_orders": False,
            "closes_positions": False,
            "cancels_orders": False,
            "withdrawal_executed": False,
            "transfer_executed": False,
            "live_ready": False,
        }

    async def _runtime_stop(input_params):
        runtime_stop_calls.append(dict(input_params))
        if runtime_stop_failure is not None:
            raise runtime_stop_failure
        runtime["current_runtime_state"] = "hard_locked"
        return {
            "status": "hard_locked",
            "runtime_state": "hard_locked",
            "stopped_by_owner": True,
            "emergency_stop": True,
            "operation_id": input_params["operation_id"],
            "preflight_id": input_params["preflight_id"],
            "authorization_source": input_params["authorization_source"],
            "flatten_executed": False,
            "orders_cancelled": False,
            "places_orders": False,
            "closes_positions": False,
            "cancels_orders": False,
            "live_ready": False,
        }

    async def _fixed_rehearsal(input_params):
        fixed_rehearsal_calls.append(dict(input_params))
        if fixed_rehearsal_failure is not None:
            raise fixed_rehearsal_failure
        return {
            "workflow_run_id": f"op-wf-{input_params['operation_id']}",
            "campaign_id": "brc-rehearsal",
            "mutation_executed": True,
            "withdrawal_executed": False,
            "live_ready": False,
            "final_inventory": {"all_flat": True},
            "review_artifact": {"campaign_id": "brc-rehearsal", "ready": True},
            "evidence": {"packet": "fixed-testnet-rehearsal"},
            "readiness": {"mode": "testnet_ready", "live_ready": False},
            "steps": [
                {"name": "campaign_created", "payload": {"campaign_id": "brc-rehearsal"}},
                {"name": "review_recorded", "payload": {"review_id": "review-rehearsal"}},
                {"name": "finalized", "payload": {"campaign_id": "brc-rehearsal"}},
            ],
        }
    admission_campaign_creator = (
        admission_campaign_creator_factory(brc)
        if admission_campaign_creator_factory is not None
        else None
    )
    admission_runtime_constraint_installer = (
        admission_runtime_constraint_installer_factory(brc)
        if admission_runtime_constraint_installer_factory is not None
        else None
    )
    admission_runtime_carrier_preparer = (
        admission_runtime_carrier_preparer_factory(brc)
        if admission_runtime_carrier_preparer_factory is not None
        else None
    )
    admission_runtime_start_preparer = (
        admission_runtime_start_preparer_factory(brc)
        if admission_runtime_start_preparer_factory is not None
        else None
    )
    trial_trade_intent_evaluator = (
        trial_trade_intent_evaluator_factory(brc)
        if trial_trade_intent_evaluator_factory is not None
        else None
    )
    admission_runtime_handoff_preparer = (
        admission_runtime_handoff_preparer_factory(brc)
        if admission_runtime_handoff_preparer_factory is not None
        else None
    )
    admission_runtime_start_from_handoff_starter = (
        admission_runtime_start_from_handoff_starter_factory(brc)
        if admission_runtime_start_from_handoff_starter_factory is not None
        else None
    )
    admission_strategy_activation_preparer = (
        admission_strategy_activation_preparer_factory(brc)
        if admission_strategy_activation_preparer_factory is not None
        else None
    )
    admission_strategy_state_activator = (
        admission_strategy_state_activator_factory(brc)
        if admission_strategy_state_activator_factory is not None
        else None
    )
    admission_signal_loop_preparer = (
        admission_signal_loop_preparer_factory(brc)
        if admission_signal_loop_preparer_factory is not None
        else None
    )
    admission_signal_loop_starter = (
        admission_signal_loop_starter_factory(brc)
        if admission_signal_loop_starter_factory is not None
        else None
    )
    admission_signal_evaluator = (
        admission_signal_evaluator_factory(brc)
        if admission_signal_evaluator_factory is not None
        else None
    )
    signal_trade_intent_recorder = (
        signal_trade_intent_recorder_factory(brc)
        if signal_trade_intent_recorder_factory is not None
        else None
    )

    service = BrcOperationService(
        repository=op_repo,
        brc_campaign_service=brc,
        readers=OperationLayerReaders(
            runtime_summary=_runtime_summary,
            markets_orders_summary=_market_summary,
            audit_writable=_audit_writable,
            runtime_safety_readiness=runtime_safety_readiness,
            review_artifact_reader=_review_artifact,
            runtime_transition=_runtime_transition if runtime_adapter else None,
            budget_authorization_summary=_budget_summary if budget_adapter else None,
            budget_revoke_executor=_budget_revoke if budget_revoke_adapter else None,
            runtime_stop_executor=_runtime_stop if runtime_stop_adapter else None,
            fixed_rehearsal_executor=_fixed_rehearsal if fixed_rehearsal_adapter else None,
            admission_readiness=admission_readiness,
            admission_binding_reserver=admission_binding_reserver,
            admission_campaign_readiness=admission_campaign_readiness,
            admission_campaign_creator=admission_campaign_creator,
            admission_runtime_constraint_readiness=admission_runtime_constraint_readiness,
            admission_runtime_constraint_installer=admission_runtime_constraint_installer,
            admission_runtime_carrier_readiness=admission_runtime_carrier_readiness,
            admission_runtime_carrier_preparer=admission_runtime_carrier_preparer,
            admission_runtime_start_readiness=admission_runtime_start_readiness,
            admission_runtime_start_preparer=admission_runtime_start_preparer,
            trial_trade_intent_readiness=trial_trade_intent_readiness,
            trial_trade_intent_evaluator=trial_trade_intent_evaluator,
            admission_runtime_handoff_readiness=admission_runtime_handoff_readiness,
            admission_runtime_handoff_preparer=admission_runtime_handoff_preparer,
            admission_runtime_start_from_handoff_readiness=admission_runtime_start_from_handoff_readiness,
            admission_runtime_start_from_handoff_starter=admission_runtime_start_from_handoff_starter,
            admission_strategy_activation_readiness=admission_strategy_activation_readiness,
            admission_strategy_activation_preparer=admission_strategy_activation_preparer,
            admission_strategy_state_activation_readiness=admission_strategy_state_activation_readiness,
            admission_strategy_state_activator=admission_strategy_state_activator,
            admission_signal_loop_readiness=admission_signal_loop_readiness,
            admission_signal_loop_preparer=admission_signal_loop_preparer,
            admission_signal_loop_start_readiness=admission_signal_loop_start_readiness,
            admission_signal_loop_starter=admission_signal_loop_starter,
            admission_signal_evaluation_readiness=admission_signal_evaluation_readiness,
            admission_signal_evaluator=admission_signal_evaluator,
            signal_trade_intent_readiness=signal_trade_intent_readiness,
            signal_trade_intent_recorder=signal_trade_intent_recorder,
        ),
        execution_permission_resolver=ExecutionPermissionResolver(
            configured_max_permission=execution_permission_max
        ),
        ttl_ms=ttl_ms,
    )
    await service.initialize()
    market["fixed_rehearsal_calls"] = fixed_rehearsal_calls
    market["runtime_stop_calls"] = runtime_stop_calls
    market["budget_revoke_calls"] = budget_revoke_calls
    market["budget_state"] = budget_state
    market["runtime_state"] = runtime
    return service, op_repo, brc_repo, market


async def _admission_service(*, adapter=None):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in ADMISSION_TABLES:
            await conn.run_sync(table.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    service = BrcAdmissionService(
        repository=PgBrcAdmissionRepository(session_maker=session_maker),
        risk_capital_adapter=adapter,
    )
    return service, engine


async def _installable_admission(
    *,
    execution_mode: AdmissionExecutionMode | None = None,
):
    admission, engine = await _admission_service()
    _, _, _, _, request = await _seed_request(
        admission,
        trial_env=TrialEnv.TESTNET,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        mandatory_complete=True,
        requested_execution_mode=execution_mode,
    )
    decision = await admission.evaluate(request.admission_request_id)
    acceptance = await admission.create_owner_risk_acceptance(
        OwnerRiskAcceptanceInput(
            admission_request_id=request.admission_request_id,
            admission_decision_id=decision.admission_decision_id,
            constraint_snapshot_id=decision.trial_constraint_snapshot_id,
            owner_rationale="I accept the installable gated trial constraints.",
            confirmation_phrase="I ACCEPT BOUNDED FUNDED VALIDATION RISK",
        )
    )
    return admission, engine, decision, acceptance


def _binding_reserver(admission: BrcAdmissionService):
    async def _reserve(input_params: dict):
        return (
            await admission.reserve_gated_trial_binding(
                input_params,
                operation_id=input_params["operation_id"],
                preflight_id=input_params["preflight_id"],
                confirmed_by=input_params.get("confirmed_by") or "owner",
            )
        ).model_dump(mode="json")

    return _reserve


def _campaign_creator(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _create(input_params: dict):
            readiness = await admission.build_campaign_carrier_preflight_readiness(input_params)
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(input_params.get("admission_binding_id") or input_params.get("binding_id"))
            binding = await admission.get_admission_trial_binding(binding_id)
            decision = await admission.get_admission_decision(binding.admission_decision_id)
            constraint = await admission.get_trial_constraint_snapshot(
                binding.trial_constraint_snapshot_id
            )
            campaign = await brc.create_admission_campaign_shell(
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                trial_env=binding.trial_env.value,
                trial_stage=binding.trial_stage.value,
                execution_mode=binding.execution_mode.value,
                constraints_json=dict(constraint.constraints_json),
                reason="unit admission campaign shell",
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                created_by=str(input_params.get("confirmed_by") or "owner"),
            )
            updated_binding = await admission.mark_admission_trial_binding_campaign_created(
                binding_id=binding.binding_id,
                campaign_id=campaign.campaign_id,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            return {
                "campaign": campaign.model_dump(mode="json"),
                "binding": updated_binding.model_dump(mode="json"),
                "admission_decision_id": decision.admission_decision_id,
                "campaign_created": True,
                "runtime_installed": False,
                "runtime_started": False,
                "strategy_active": False,
                "constraints_installed": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _create

    return _factory


def _runtime_constraint_readiness(admission: BrcAdmissionService, brc: BoundedRiskCampaignService):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        return await admission.build_runtime_constraint_install_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary={"current_runtime_state": "observe", "strategy_active": False},
        )

    return _readiness


def _runtime_constraint_installer(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _install(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_runtime_constraint_install_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={"current_runtime_state": "observe", "strategy_active": False},
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            constraint = await admission.get_trial_constraint_snapshot(
                binding.trial_constraint_snapshot_id
            )
            installed = await brc.install_runtime_constraints_from_admission_campaign(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                constraints_json=dict(constraint.constraints_json),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                installed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            updated_binding = await admission.mark_admission_trial_binding_runtime_constraints_installed(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            campaign_payload = installed["campaign"].model_dump(mode="json")
            return {
                "campaign": campaign_payload,
                "binding": updated_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "installed_constraint_snapshot_id": binding.trial_constraint_snapshot_id,
                "installed_constraints_summary": dict(installed.get("installed_constraints_summary") or {}),
                "idempotent": bool(installed.get("idempotent", False)),
                "constraints_installed": True,
                "runtime_status": "constraints_installed_not_started",
                "runtime_started": False,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _install

    return _factory


def _runtime_carrier_readiness(admission: BrcAdmissionService, brc: BoundedRiskCampaignService):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        return await admission.build_runtime_carrier_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary={"current_runtime_state": "observe", "strategy_active": False},
        )

    return _readiness


def _runtime_carrier_preparer(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _prepare(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_runtime_carrier_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={"current_runtime_state": "observe", "strategy_active": False},
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            prepared = await brc.prepare_runtime_carrier_from_admission_campaign(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                execution_mode=binding.execution_mode.value,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                prepared_by=str(input_params.get("confirmed_by") or "owner"),
            )
            audited_binding = await admission.record_admission_runtime_carrier_ready(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            campaign_payload = prepared["campaign"].model_dump(mode="json")
            return {
                "campaign": campaign_payload,
                "binding": audited_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "carrier_ready": True,
                "carrier_readiness_summary": dict(prepared.get("carrier_readiness_summary") or {}),
                "idempotent": bool(prepared.get("idempotent", False)),
                "runtime_status": "carrier_ready_not_started",
                "runtime_started": False,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _prepare

    return _factory


def _runtime_start_readiness(admission: BrcAdmissionService, brc: BoundedRiskCampaignService):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        return await admission.build_runtime_start_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary={"current_runtime_state": "observe", "strategy_active": False},
        )

    return _readiness


def _runtime_start_preparer(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _prepare(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_runtime_start_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={"current_runtime_state": "observe", "strategy_active": False},
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            prepared = await brc.prepare_runtime_start_from_admission_carrier(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                execution_mode=binding.execution_mode.value,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                prepared_by=str(input_params.get("confirmed_by") or "owner"),
            )
            audited_binding = await admission.record_admission_runtime_start_ready(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            campaign_payload = prepared["campaign"].model_dump(mode="json")
            return {
                "campaign": campaign_payload,
                "binding": audited_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "runtime_start_ready": True,
                "runtime_start_readiness_summary": dict(
                    prepared.get("runtime_start_readiness_summary") or {}
                ),
                "idempotent": bool(prepared.get("idempotent", False)),
                "runtime_status": "runtime_start_ready_not_started",
                "runtime_started": False,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _prepare

    return _factory


def _trial_trade_intent_readiness(admission: BrcAdmissionService, brc: BoundedRiskCampaignService):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        return await admission.build_trial_trade_intent_preflight_readiness(
            input_params,
            campaign=campaign,
        )

    return _readiness


def _trial_trade_intent_evaluator(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _evaluate(input_params: dict):
            campaign = await brc.get_current_campaign()
            evaluated = await admission.evaluate_trial_trade_intent(
                input_params,
                campaign=campaign,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            return {
                **evaluated,
                "campaign_id": getattr(campaign, "campaign_id", None),
                "trial_trade_intent_is_order": False,
                "order_created": False,
                "execution_intent_created": False,
                "runtime_started": False,
                "strategy_active": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _evaluate

    return _factory


def _runtime_handoff_readiness(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    *,
    trade_intent_ledger_available: bool = True,
):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        return await admission.build_runtime_handoff_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary={"current_runtime_state": "observe", "strategy_active": False},
            trade_intent_ledger_available=trade_intent_ledger_available,
        )

    return _readiness


def _runtime_handoff_preparer(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _prepare(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_runtime_handoff_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={"current_runtime_state": "observe", "strategy_active": False},
                trade_intent_ledger_available=True,
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            prepared = await brc.prepare_runtime_handoff_from_admission_campaign(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                execution_mode=binding.execution_mode.value,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                prepared_by=str(input_params.get("confirmed_by") or "owner"),
            )
            audited_binding = await admission.record_admission_runtime_handoff_ready(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            campaign_payload = prepared["campaign"].model_dump(mode="json")
            return {
                "campaign": campaign_payload,
                "binding": audited_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "runtime_handoff_ready": True,
                "runtime_handoff_readiness_summary": dict(
                    prepared.get("runtime_handoff_readiness_summary") or {}
                ),
                "idempotent": bool(prepared.get("idempotent", False)),
                "runtime_status": "runtime_handoff_ready_not_started",
                "runtime_started": False,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "order_created": False,
                "execution_intent_created": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _prepare

    return _factory


def _runtime_start_from_handoff_readiness(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    *,
    trade_intent_ledger_available: bool = True,
):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        return await admission.build_start_runtime_from_handoff_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary={
                "current_runtime_state": "observe",
                "profile": "brc_btc_eth_testnet_runtime",
                "testnet": True,
                "strategy_active": False,
                "live_ready": False,
            },
            trade_intent_ledger_available=trade_intent_ledger_available,
        )

    return _readiness


def _runtime_start_from_handoff_starter(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _start(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_start_runtime_from_handoff_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={
                    "current_runtime_state": "observe",
                    "profile": "brc_btc_eth_testnet_runtime",
                    "testnet": True,
                    "strategy_active": False,
                    "live_ready": False,
                },
                trade_intent_ledger_available=True,
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            started = await brc.start_runtime_from_admission_handoff(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                execution_mode=binding.execution_mode.value,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                started_by=str(input_params.get("confirmed_by") or "owner"),
            )
            audited_binding = await admission.record_admission_runtime_started(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            return {
                "campaign": started["campaign"].model_dump(mode="json"),
                "binding": audited_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "runtime_started": True,
                "runtime_start_summary": dict(started.get("runtime_start_summary") or {}),
                "idempotent": bool(started.get("idempotent", False)),
                "runtime_status": "runtime_started_strategy_inactive",
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "order_created": False,
                "execution_intent_created": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _start

    return _factory


def _strategy_activation_readiness(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    *,
    runtime_state: dict | None = None,
):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        summary = {
            "current_runtime_state": "observe",
            "profile": "brc_btc_eth_testnet_runtime",
            "testnet": True,
            "strategy_active": False,
            "active_strategy_id": None,
            "active_trial_id": None,
            "emergency_stop_active": False,
            "hard_lock_active": False,
            "live_ready": False,
        }
        summary.update(runtime_state or {})
        return await admission.build_strategy_activation_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary=summary,
        )

    return _readiness


def _strategy_activation_preparer(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _prepare(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_strategy_activation_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={
                    "current_runtime_state": "observe",
                    "profile": "brc_btc_eth_testnet_runtime",
                    "testnet": True,
                    "strategy_active": False,
                    "active_strategy_id": None,
                    "active_trial_id": None,
                    "emergency_stop_active": False,
                    "hard_lock_active": False,
                    "live_ready": False,
                },
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            prepared = await brc.prepare_strategy_activation_from_admission_runtime(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                execution_mode=binding.execution_mode.value,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                prepared_by=str(input_params.get("confirmed_by") or "owner"),
            )
            audited_binding = await admission.record_admission_strategy_activation_ready(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            return {
                "campaign": prepared["campaign"].model_dump(mode="json"),
                "binding": audited_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "strategy_activation_ready": True,
                "strategy_activation_readiness_summary": dict(
                    prepared.get("strategy_activation_readiness_summary") or {}
                ),
                "idempotent": bool(prepared.get("idempotent", False)),
                "event": dict(prepared.get("event") or {}),
                "runtime_status": "strategy_activation_ready_not_active",
                "runtime_started": True,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "signal_loop_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _prepare

    return _factory


def _strategy_state_activation_readiness(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    *,
    runtime_state: dict | None = None,
):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        summary = {
            "current_runtime_state": "observe",
            "profile": "brc_btc_eth_testnet_runtime",
            "testnet": True,
            "active_strategy_id": None,
            "strategy_execution_enabled": False,
            "signal_loop_enabled": False,
            "signal_loop_started": False,
            "active_trial_id": None,
            "emergency_stop_active": False,
            "hard_lock_active": False,
            "live_ready": False,
        }
        summary.update(runtime_state or {})
        return await admission.build_strategy_state_activation_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary=summary,
        )

    return _readiness


def _strategy_state_activator(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _activate(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_strategy_state_activation_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={
                    "current_runtime_state": "observe",
                    "profile": "brc_btc_eth_testnet_runtime",
                    "testnet": True,
                    "active_strategy_id": None,
                    "strategy_execution_enabled": False,
                    "signal_loop_enabled": False,
                    "signal_loop_started": False,
                    "active_trial_id": None,
                    "emergency_stop_active": False,
                    "hard_lock_active": False,
                    "live_ready": False,
                },
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            activated = await brc.activate_strategy_from_admission_runtime(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                execution_mode=binding.execution_mode.value,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                activated_by=str(input_params.get("confirmed_by") or "owner"),
            )
            audited_binding = await admission.record_admission_strategy_activated_no_execution(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            return {
                "campaign": activated["campaign"].model_dump(mode="json"),
                "binding": audited_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "strategy_state": "strategy_active_no_execution",
                "strategy_activation_state": "active_no_execution",
                "strategy_state_activation_summary": dict(
                    activated.get("strategy_state_activation_summary") or {}
                ),
                "idempotent": bool(activated.get("idempotent", False)),
                "event": dict(activated.get("event") or {}),
                "runtime_status": "strategy_active_no_execution",
                "runtime_started": True,
                "runtime_active": False,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "trial_started": False,
                "signal_loop_enabled": False,
                "signal_loop_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _activate

    return _factory


def _signal_loop_readiness(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    *,
    runtime_state: dict | None = None,
):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        summary = {
            "current_runtime_state": "observe",
            "profile": "brc_btc_eth_testnet_runtime",
            "testnet": True,
            "strategy_execution_enabled": False,
            "signal_loop_enabled": False,
            "signal_loop_started": False,
            "active_trial_id": None,
            "emergency_stop_active": False,
            "hard_lock_active": False,
            "live_ready": False,
        }
        summary.update(runtime_state or {})
        return await admission.build_signal_loop_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary=summary,
        )

    return _readiness


def _signal_loop_preparer(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _prepare(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_signal_loop_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={
                    "current_runtime_state": "observe",
                    "profile": "brc_btc_eth_testnet_runtime",
                    "testnet": True,
                    "strategy_execution_enabled": False,
                    "signal_loop_enabled": False,
                    "signal_loop_started": False,
                    "active_trial_id": None,
                    "emergency_stop_active": False,
                    "hard_lock_active": False,
                    "live_ready": False,
                },
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            prepared = await brc.prepare_signal_loop_from_admission_strategy(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                execution_mode=binding.execution_mode.value,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                prepared_by=str(input_params.get("confirmed_by") or "owner"),
            )
            audited_binding = await admission.record_admission_signal_loop_ready(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            return {
                "campaign": prepared["campaign"].model_dump(mode="json"),
                "binding": audited_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "signal_loop_ready": True,
                "signal_loop_readiness_summary": dict(
                    prepared.get("signal_loop_readiness_summary") or {}
                ),
                "idempotent": bool(prepared.get("idempotent", False)),
                "event": dict(prepared.get("event") or {}),
                "runtime_status": "signal_loop_ready_not_started",
                "runtime_started": True,
                "runtime_active": False,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "trial_started": False,
                "signal_loop_enabled": False,
                "signal_loop_started": False,
                "signal_generated": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _prepare

    return _factory


def _signal_loop_start_readiness(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    *,
    runtime_state: dict | None = None,
):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        summary = {
            "current_runtime_state": "observe",
            "profile": "brc_btc_eth_testnet_runtime",
            "testnet": True,
            "strategy_execution_enabled": False,
            "signal_loop_enabled": False,
            "signal_loop_started": False,
            "active_trial_id": None,
            "emergency_stop_active": False,
            "hard_lock_active": False,
            "live_ready": False,
        }
        summary.update(runtime_state or {})
        return await admission.build_signal_loop_start_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary=summary,
        )

    return _readiness


def _signal_loop_starter(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _start(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_signal_loop_start_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={
                    "current_runtime_state": "observe",
                    "profile": "brc_btc_eth_testnet_runtime",
                    "testnet": True,
                    "strategy_execution_enabled": False,
                    "signal_loop_enabled": False,
                    "signal_loop_started": False,
                    "active_trial_id": None,
                    "emergency_stop_active": False,
                    "hard_lock_active": False,
                    "live_ready": False,
                },
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            started = await brc.start_signal_loop_from_admission_strategy(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                execution_mode=binding.execution_mode.value,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                started_by=str(input_params.get("confirmed_by") or "owner"),
            )
            audited_binding = await admission.record_admission_signal_loop_started_no_signal(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            return {
                "campaign": started["campaign"].model_dump(mode="json"),
                "binding": audited_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "signal_loop_start_summary": dict(
                    started.get("signal_loop_start_summary") or {}
                ),
                "idempotent": bool(started.get("idempotent", False)),
                "event": dict(started.get("event") or {}),
                "runtime_status": "signal_loop_started_no_signal",
                "runtime_started": True,
                "runtime_active": False,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "signal_loop_ready": True,
                "signal_loop_enabled": True,
                "signal_loop_enabled_scope": "non_trading_loop_state",
                "signal_loop_started": True,
                "signal_generated": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _start

    return _factory


def _signal_evaluation_readiness(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    *,
    runtime_state: dict | None = None,
):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        summary = {
            "current_runtime_state": "observe",
            "profile": "brc_btc_eth_testnet_runtime",
            "testnet": True,
            "strategy_execution_enabled": False,
            "signal_loop_enabled": True,
            "signal_loop_started": True,
            "active_trial_id": None,
            "emergency_stop_active": False,
            "hard_lock_active": False,
            "live_ready": False,
        }
        summary.update(runtime_state or {})
        return await admission.build_signal_evaluation_preflight_readiness(
            input_params,
            campaign=campaign,
            runtime_summary=summary,
        )

    return _readiness


def _signal_evaluator(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _evaluate(input_params: dict):
            campaign = await brc.get_current_campaign()
            readiness = await admission.build_signal_evaluation_preflight_readiness(
                input_params,
                campaign=campaign,
                runtime_summary={
                    "current_runtime_state": "observe",
                    "profile": "brc_btc_eth_testnet_runtime",
                    "testnet": True,
                    "strategy_execution_enabled": False,
                    "signal_loop_enabled": True,
                    "signal_loop_started": True,
                    "active_trial_id": None,
                    "emergency_stop_active": False,
                    "hard_lock_active": False,
                    "live_ready": False,
                },
            )
            blockers = [str(item) for item in readiness.get("blockers") or []]
            if blockers:
                raise ValueError("; ".join(blockers))
            binding_id = str(
                input_params.get("admission_binding_id")
                or input_params.get("binding_id")
                or readiness.get("binding_summary", {}).get("binding_id")
            )
            binding = await admission.get_admission_trial_binding(binding_id)
            evaluated = await brc.evaluate_signal_from_admission_strategy(
                campaign_id=str(binding.campaign_id),
                admission_binding_id=binding.binding_id,
                admission_decision_id=binding.admission_decision_id,
                strategy_family_version_id=binding.strategy_family_version_id,
                playbook_id=binding.playbook_id,
                installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
                execution_mode=binding.execution_mode.value,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                signal_snapshot=dict(input_params.get("signal_snapshot") or {}),
                signal_evaluation_input=dict(input_params.get("signal_evaluation_input") or {}),
                evaluated_by=str(input_params.get("confirmed_by") or "owner"),
            )
            audited_binding = await admission.record_admission_signal_evaluated_no_intent(
                binding_id=binding.binding_id,
                campaign_id=str(binding.campaign_id),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            return {
                "campaign": evaluated["campaign"].model_dump(mode="json"),
                "binding": audited_binding.model_dump(mode="json"),
                "campaign_id": binding.campaign_id,
                "binding_id": binding.binding_id,
                "signal_evaluation_summary": dict(
                    evaluated.get("signal_evaluation_summary") or {}
                ),
                "idempotent": bool(evaluated.get("idempotent", False)),
                "event": dict(evaluated.get("event") or {}),
                "runtime_status": "signal_evaluated_no_intent",
                "runtime_started": True,
                "runtime_active": False,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "signal_loop_started": True,
                "signal_loop_enabled": True,
                "signal_loop_enabled_scope": "non_trading_loop_state",
                "signal_evaluated": True,
                "signal_generated": True,
                "signal_is_trade_intent": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "live_ready": False,
            }

        return _evaluate

    return _factory


def _signal_trade_intent_readiness(admission: BrcAdmissionService, brc: BoundedRiskCampaignService):
    async def _readiness(input_params: dict):
        campaign = await brc.get_current_campaign()
        return await admission.build_signal_trial_trade_intent_preflight_readiness(
            input_params,
            campaign=campaign,
        )

    return _readiness


def _signal_trade_intent_recorder(admission: BrcAdmissionService):
    def _factory(brc: BoundedRiskCampaignService):
        async def _record(input_params: dict):
            campaign = await brc.get_current_campaign()
            recorded = await admission.record_trial_trade_intent_from_signal_evaluation(
                input_params,
                campaign=campaign,
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
                execution_permission_resolution=dict(input_params.get("execution_permission_resolution") or {}),
                confirmed_by=str(input_params.get("confirmed_by") or "owner"),
            )
            intent = dict(recorded.get("intent") or {})
            metadata_result = await brc.record_trial_trade_intent_recorded_no_execution(
                campaign_id=str(recorded.get("campaign_id") or intent.get("campaign_id")),
                admission_binding_id=str(recorded.get("binding_id") or intent.get("binding_id")),
                admission_decision_id=str(intent.get("admission_decision_id")),
                strategy_family_version_id=str(intent.get("strategy_family_version_id")),
                playbook_id=str(intent.get("playbook_id")),
                installed_constraint_snapshot_id=str(campaign.metadata_json["installed_constraint_snapshot_id"]),
                execution_mode=str(recorded.get("execution_mode") or intent.get("execution_mode")),
                trial_trade_intent_id=recorded.get("intent_id") or intent.get("intent_id"),
                trial_trade_intent_result=str(recorded["trial_trade_intent_result"]),
                not_executed_reason=str(recorded.get("not_executed_reason") or intent.get("not_executed_reason")),
                execution_permission_resolution=dict(recorded.get("execution_permission_resolution") or {}),
                operation_id=str(input_params["operation_id"]),
                preflight_id=str(input_params["preflight_id"]),
            )
            return {
                **recorded,
                "campaign": metadata_result["campaign"].model_dump(mode="json"),
                "campaign_id": metadata_result["campaign"].campaign_id,
                "trial_trade_intent_summary": dict(metadata_result.get("trial_trade_intent_summary") or {}),
                "metadata_idempotent": bool(metadata_result.get("idempotent", False)),
                "trial_trade_intent_is_order": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "trial_started": False,
                "auto_execution_enabled": False,
                "auto_within_budget_enabled": False,
                "live_ready": False,
            }

        return _record

    return _factory


async def _switch_preflight(service: BrcOperationService):
    return await service.preflight(
        operation_type="switch_playbook",
        requested_by="owner",
        input_params={
            "target_playbook_id": "PB-004-BRC-CONTROLLED-TESTNET",
            "reason_text": "owner authorized controlled rehearsal",
            "evidence_refs": ["docs/adr/0012-bounded-risk-campaign-system.md"],
        },
        source={"kind": "ui"},
    )


@pytest.mark.asyncio
async def test_operation_capabilities_model_supported_and_forbidden_operations():
    service, _, _, _ = await _operation_service()
    capabilities = {item.operation_type: item for item in service.capabilities()}

    assert capabilities["switch_playbook"].status == "enabled"
    assert capabilities["switch_playbook"].executable_through_operation is True
    for operation_type in [
        "write_review_outcome",
        "start_review",
        "enter_observe",
        "enter_pause",
        "enter_strategy_or_monitor",
    ]:
        assert capabilities[operation_type].status == "enabled"
        assert capabilities[operation_type].executable_through_operation is True
    assert capabilities["run_fixed_testnet_rehearsal"].status == "unavailable"
    assert capabilities["run_fixed_testnet_rehearsal"].executable_through_operation is False
    assert capabilities["withdrawal"].status == "forbidden"
    assert capabilities["llm_direct_execution"].status == "forbidden"
    assert capabilities["emergency_flatten"].status == "preflight_dry_run_available"
    assert capabilities["emergency_flatten"].executable_through_operation is False
    assert capabilities["emergency_flatten"].dry_run_only is True
    assert capabilities["emergency_flatten"].confirmation_required is True
    assert capabilities["emergency_stop_runtime"].status == "preflight_planning_available"
    assert capabilities["emergency_stop_runtime"].executable_through_operation is False
    assert capabilities["create_gated_trial_from_admission"].status == "binding_reservation_available"
    assert capabilities["create_gated_trial_from_admission"].executable_through_operation is True
    assert capabilities["create_gated_trial_from_admission"].confirmation_required is True
    assert "does not create a campaign or runtime carrier" in capabilities[
        "create_gated_trial_from_admission"
    ].current_reason
    assert capabilities["install_runtime_constraints_from_admission_campaign"].status == "operation_preflight_available"
    assert capabilities["install_runtime_constraints_from_admission_campaign"].executable_through_operation is True
    assert capabilities["install_runtime_constraints_from_admission_campaign"].confirmation_required is True
    assert "does not start runtime or strategy" in capabilities[
        "install_runtime_constraints_from_admission_campaign"
    ].current_reason
    assert capabilities["prepare_runtime_carrier_from_admission_campaign"].status == "operation_preflight_available"
    assert capabilities["prepare_runtime_carrier_from_admission_campaign"].executable_through_operation is True
    assert capabilities["prepare_runtime_carrier_from_admission_campaign"].confirmation_required is True
    assert "does not start runtime, strategy, or trading" in capabilities[
        "prepare_runtime_carrier_from_admission_campaign"
    ].current_reason
    assert capabilities["prepare_runtime_start_from_admission_carrier"].status == "operation_preflight_available"
    assert capabilities["prepare_runtime_start_from_admission_carrier"].executable_through_operation is True
    assert capabilities["prepare_runtime_start_from_admission_carrier"].confirmation_required is True
    assert "does not start runtime, strategy, or trading" in capabilities[
        "prepare_runtime_start_from_admission_carrier"
    ].current_reason
    assert capabilities["evaluate_trial_trade_intent"].status == "operation_preflight_available"
    assert capabilities["evaluate_trial_trade_intent"].executable_through_operation is True
    assert capabilities["evaluate_trial_trade_intent"].confirmation_required is True
    assert "does not start runtime, strategy, or trading" in capabilities[
        "evaluate_trial_trade_intent"
    ].current_reason
    assert capabilities["prepare_runtime_handoff_from_admission_campaign"].status == "operation_preflight_available"
    assert capabilities["prepare_runtime_handoff_from_admission_campaign"].executable_through_operation is True
    assert capabilities["prepare_runtime_handoff_from_admission_campaign"].confirmation_required is True
    assert "does not start runtime, strategy, or trading" in capabilities[
        "prepare_runtime_handoff_from_admission_campaign"
    ].current_reason
    assert capabilities["start_runtime_from_admission_handoff"].status == "operation_preflight_available"
    assert capabilities["start_runtime_from_admission_handoff"].executable_through_operation is True
    assert capabilities["start_runtime_from_admission_handoff"].confirmation_required is True
    assert "runtime state only" in capabilities[
        "start_runtime_from_admission_handoff"
    ].current_reason
    assert "does not activate strategy" in capabilities[
        "start_runtime_from_admission_handoff"
    ].current_reason
    assert "enable auto execution" in capabilities[
        "start_runtime_from_admission_handoff"
    ].current_reason
    assert "place orders" in capabilities[
        "start_runtime_from_admission_handoff"
    ].current_reason
    assert capabilities["prepare_strategy_activation_from_admission_runtime"].status == "operation_preflight_available"
    assert capabilities["prepare_strategy_activation_from_admission_runtime"].executable_through_operation is True
    assert capabilities["prepare_strategy_activation_from_admission_runtime"].confirmation_required is True
    assert "does not activate strategy" in capabilities[
        "prepare_strategy_activation_from_admission_runtime"
    ].current_reason
    assert "start signal loop" in capabilities[
        "prepare_strategy_activation_from_admission_runtime"
    ].current_reason
    assert "enable auto execution" in capabilities[
        "prepare_strategy_activation_from_admission_runtime"
    ].current_reason
    assert "create execution intents" in capabilities[
        "prepare_strategy_activation_from_admission_runtime"
    ].current_reason
    assert "place orders" in capabilities[
        "prepare_strategy_activation_from_admission_runtime"
    ].current_reason
    assert capabilities["activate_strategy_from_admission_runtime"].status == "operation_preflight_available"
    assert capabilities["activate_strategy_from_admission_runtime"].executable_through_operation is True
    assert capabilities["activate_strategy_from_admission_runtime"].confirmation_required is True
    assert "strategy state metadata only" in capabilities[
        "activate_strategy_from_admission_runtime"
    ].current_reason
    assert "does not enable signal loop" in capabilities[
        "activate_strategy_from_admission_runtime"
    ].current_reason
    assert "auto execution" in capabilities[
        "activate_strategy_from_admission_runtime"
    ].current_reason
    assert "execution intents" in capabilities[
        "activate_strategy_from_admission_runtime"
    ].current_reason
    assert "orders" in capabilities[
        "activate_strategy_from_admission_runtime"
    ].current_reason
    assert capabilities["prepare_signal_loop_from_admission_strategy"].status == "operation_preflight_available"
    assert capabilities["prepare_signal_loop_from_admission_strategy"].executable_through_operation is True
    assert capabilities["prepare_signal_loop_from_admission_strategy"].confirmation_required is True
    assert "signal loop readiness metadata only" in capabilities[
        "prepare_signal_loop_from_admission_strategy"
    ].current_reason
    assert "does not start signal loop" in capabilities[
        "prepare_signal_loop_from_admission_strategy"
    ].current_reason
    assert "generate signals" in capabilities[
        "prepare_signal_loop_from_admission_strategy"
    ].current_reason
    assert "trade intents" in capabilities[
        "prepare_signal_loop_from_admission_strategy"
    ].current_reason
    assert "execution intents" in capabilities[
        "prepare_signal_loop_from_admission_strategy"
    ].current_reason
    assert "orders" in capabilities[
        "prepare_signal_loop_from_admission_strategy"
    ].current_reason
    assert capabilities["start_signal_loop_from_admission_strategy"].status == "operation_preflight_available"
    assert capabilities["start_signal_loop_from_admission_strategy"].executable_through_operation is True
    assert capabilities["start_signal_loop_from_admission_strategy"].confirmation_required is True
    assert "signal loop state metadata only" in capabilities[
        "start_signal_loop_from_admission_strategy"
    ].current_reason
    assert "does not generate signals" in capabilities[
        "start_signal_loop_from_admission_strategy"
    ].current_reason
    assert "trade intents" in capabilities[
        "start_signal_loop_from_admission_strategy"
    ].current_reason
    assert "execution intents" in capabilities[
        "start_signal_loop_from_admission_strategy"
    ].current_reason
    assert "orders" in capabilities[
        "start_signal_loop_from_admission_strategy"
    ].current_reason
    assert capabilities["evaluate_signal_from_admission_strategy"].status == "operation_preflight_available"
    assert capabilities["evaluate_signal_from_admission_strategy"].executable_through_operation is True
    assert capabilities["evaluate_signal_from_admission_strategy"].confirmation_required is True
    assert "signal snapshot metadata only" in capabilities[
        "evaluate_signal_from_admission_strategy"
    ].current_reason
    assert "does not create trade intents" in capabilities[
        "evaluate_signal_from_admission_strategy"
    ].current_reason
    assert "execution intents" in capabilities[
        "evaluate_signal_from_admission_strategy"
    ].current_reason
    assert "orders" in capabilities[
        "evaluate_signal_from_admission_strategy"
    ].current_reason


@pytest.mark.asyncio
async def test_create_gated_trial_preflight_allows_valid_installable_admission_readiness():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            admission_readiness=admission.build_gated_trial_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={
                "admission_decision_id": decision.admission_decision_id,
                "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "allow"
    assert preflight.confirmation_requirement.required is True
    assert preflight.constraints_summary["status"] == "installable"
    assert preflight.owner_risk_acceptance_summary["valid"] is True
    _assert_admission_summary_result(preflight.admission_summary)
    assert preflight.after["binding_reservation_only"] is True
    assert preflight.after["confirm_disabled"] is False
    assert preflight.binding_summary["binding_status_on_confirm"] == "binding_reserved"
    assert brc_repo.campaign is None


@pytest.mark.asyncio
async def test_create_gated_trial_preflight_blocks_pending_constraints():
    admission, engine = await _admission_service(adapter=PendingRiskCapitalAdapter())
    try:
        _, _, _, _, request = await _seed_request(
            admission,
            trial_env=TrialEnv.TESTNET,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            mandatory_complete=True,
        )
        decision = await admission.evaluate(request.admission_request_id)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_readiness=admission.build_gated_trial_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={
                "admission_decision_id": decision.admission_decision_id,
                "owner_risk_acceptance_id": "risk-acceptance-missing",
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert any("not installable" in item for item in preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_create_gated_trial_preflight_blocks_missing_risk_acceptance_for_funded_validation():
    admission, engine, decision, _ = await _installable_admission()
    try:
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_readiness=admission.build_gated_trial_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={"admission_decision_id": decision.admission_decision_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "owner_risk_acceptance_id required for funded_validation" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_create_gated_trial_preflight_blocks_mismatched_risk_acceptance():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        mismatched = decision.model_copy(
            update={"admission_decision_id": "admission-decision-mismatch"}
        )
        await admission._repo.create_admission_decision(mismatched)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_readiness=admission.build_gated_trial_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={
                "admission_decision_id": mismatched.admission_decision_id,
                "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "owner risk acceptance decision mismatch" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_create_gated_trial_preflight_blocks_expired_decision():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        expired = decision.model_copy(
            update={
                "admission_decision_id": "admission-decision-expired",
                "expires_at_ms": 1,
            }
        )
        await admission._repo.create_admission_decision(expired)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_readiness=admission.build_gated_trial_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={
                "admission_decision_id": expired.admission_decision_id,
                "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "admission decision expired" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_create_gated_trial_preflight_blocks_reject_or_park_decision():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        rejected = decision.model_copy(
            update={
                "admission_decision_id": "admission-decision-rejected",
                "decision": AdmissionDecisionValue.REJECT,
            }
        )
        parked = decision.model_copy(
            update={
                "admission_decision_id": "admission-decision-parked",
                "decision": AdmissionDecisionValue.PARK,
            }
        )
        await admission._repo.create_admission_decision(rejected)
        await admission._repo.create_admission_decision(parked)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_readiness=admission.build_gated_trial_preflight_readiness,
        )
        rejected_preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={
                "admission_decision_id": rejected.admission_decision_id,
                "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
            },
        )
        parked_preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={
                "admission_decision_id": parked.admission_decision_id,
                "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
            },
        )
    finally:
        await engine.dispose()

    assert rejected_preflight.preflight_result == "block"
    assert parked_preflight.preflight_result == "block"
    assert any("not admissible" in item for item in rejected_preflight.risk_summary["blockers"])
    assert any("not admissible" in item for item in parked_preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_create_gated_trial_preflight_blocks_live_funded_unacceptable_account_facts():
    admission, engine = await _admission_service()
    try:
        _, _, _, _, request = await _seed_request(
            admission,
            trial_env=TrialEnv.LIVE,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            mandatory_complete=True,
            account_facts_snapshot_ref=None,
            account_facts_snapshot_json={"source": "unavailable", "truth_level": "unavailable"},
        )
        decision = await admission.evaluate(request.admission_request_id)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_readiness=admission.build_gated_trial_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={"admission_decision_id": decision.admission_decision_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "account facts unavailable" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_create_gated_trial_confirm_creates_binding_reserved_only():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            admission_readiness=admission.build_gated_trial_preflight_readiness,
            admission_binding_reserver=_binding_reserver(admission),
        )
        preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={
                "admission_decision_id": decision.admission_decision_id,
                "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
            },
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_RESERVE_ADMISSION_BINDING",
            idempotency_key=preflight.idempotency_key,
        )
        bindings = await admission._repo.list_admission_trial_bindings_by_operation(
            preflight.operation_id
        )
        second = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_RESERVE_ADMISSION_BINDING",
            idempotency_key=preflight.idempotency_key,
        )
        bindings_after_second_confirm = await admission._repo.list_admission_trial_bindings_by_operation(
            preflight.operation_id
        )
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert second.status == "executed"
    assert result.result_summary["planned_result_status"] == "binding_reserved"
    assert result.result_summary["binding_persisted"] is True
    assert result.result_summary["campaign_creation_executed"] is False
    assert result.result_summary["runtime_constraints_installed"] is False
    assert result.result_summary["orders_placed"] is False
    assert len(bindings) == 1
    assert len(bindings_after_second_confirm) == 1
    assert bindings[0].binding_status.value == "binding_reserved"
    assert bindings[0].campaign_id is None
    assert bindings[0].runtime_carrier_id is None
    assert brc_repo.campaign is None


@pytest.mark.asyncio
async def test_create_gated_trial_duplicate_active_binding_blocks_preflight():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        await admission.reserve_gated_trial_binding(
            {
                "admission_decision_id": decision.admission_decision_id,
                "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
            },
            operation_id="op-existing",
            preflight_id="pre-existing",
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_readiness=admission.build_gated_trial_preflight_readiness,
            admission_binding_reserver=_binding_reserver(admission),
        )
        preflight = await service.preflight(
            operation_type="create_gated_trial_from_admission",
            requested_by="owner",
            input_params={
                "admission_decision_id": decision.admission_decision_id,
                "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert any("active admission trial binding already exists" in item for item in preflight.risk_summary["blockers"])


async def _reserve_valid_binding(admission, decision, acceptance):
    return await admission.reserve_gated_trial_binding(
        {
            "admission_decision_id": decision.admission_decision_id,
            "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
        },
        operation_id="op-binding-reserve",
        preflight_id="pre-binding-reserve",
    )


async def _create_campaign_shell_for_binding(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    binding: AdmissionTrialBinding,
):
    constraint = await admission.get_trial_constraint_snapshot(binding.trial_constraint_snapshot_id)
    campaign = await brc.create_admission_campaign_shell(
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        trial_env=binding.trial_env.value,
        trial_stage=binding.trial_stage.value,
        execution_mode=binding.execution_mode.value,
        constraints_json=dict(constraint.constraints_json),
        reason="unit admission campaign shell",
        operation_id="op-campaign-shell",
        preflight_id="pre-campaign-shell",
        created_by="owner",
    )
    updated_binding = await admission.mark_admission_trial_binding_campaign_created(
        binding_id=binding.binding_id,
        campaign_id=campaign.campaign_id,
        operation_id="op-campaign-shell",
        preflight_id="pre-campaign-shell",
    )
    return campaign, updated_binding


async def _install_constraints_for_binding(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    binding: AdmissionTrialBinding,
):
    constraint = await admission.get_trial_constraint_snapshot(binding.trial_constraint_snapshot_id)
    installed = await brc.install_runtime_constraints_from_admission_campaign(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        constraints_json=dict(constraint.constraints_json),
        operation_id="op-install-constraints",
        preflight_id="pre-install-constraints",
        installed_by="owner",
    )
    updated_binding = await admission.mark_admission_trial_binding_runtime_constraints_installed(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id="op-install-constraints",
        preflight_id="pre-install-constraints",
    )
    return installed["campaign"], updated_binding


async def _prepare_carrier_for_binding(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    binding: AdmissionTrialBinding,
):
    prepared = await brc.prepare_runtime_carrier_from_admission_campaign(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id="op-prepare-carrier",
        preflight_id="pre-prepare-carrier",
        prepared_by="owner",
    )
    audited_binding = await admission.record_admission_runtime_carrier_ready(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id="op-prepare-carrier",
        preflight_id="pre-prepare-carrier",
    )
    return prepared["campaign"], audited_binding


async def _prepare_runtime_start_for_binding(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    binding: AdmissionTrialBinding,
):
    prepared = await brc.prepare_runtime_start_from_admission_carrier(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id="op-prepare-runtime-start",
        preflight_id="pre-prepare-runtime-start",
        prepared_by="owner",
    )
    audited_binding = await admission.record_admission_runtime_start_ready(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id="op-prepare-runtime-start",
        preflight_id="pre-prepare-runtime-start",
    )
    return prepared["campaign"], audited_binding


async def _prepare_runtime_handoff_for_binding(
    admission: BrcAdmissionService,
    brc: BoundedRiskCampaignService,
    binding: AdmissionTrialBinding,
):
    prepared = await brc.prepare_runtime_handoff_from_admission_campaign(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id="op-prepare-runtime-handoff",
        preflight_id="pre-prepare-runtime-handoff",
        prepared_by="owner",
    )
    audited_binding = await admission.record_admission_runtime_handoff_ready(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id="op-prepare-runtime-handoff",
        preflight_id="pre-prepare-runtime-handoff",
    )
    return prepared["campaign"], audited_binding


async def _phase9_runtime_start_ready_context(execution_mode: AdmissionExecutionMode):
    admission, engine, decision, acceptance = await _installable_admission(
        execution_mode=execution_mode,
    )
    binding = await _reserve_valid_binding(admission, decision, acceptance)
    service, _, brc_repo, market = await _operation_service(create_campaign=False)
    _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
    _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
    _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
    _, binding = await _prepare_runtime_start_for_binding(admission, service._brc, binding)
    service, _, brc_repo, market = await _operation_service(
        create_campaign=False,
        brc_service=service._brc,
        brc_repo_existing=brc_repo,
        trial_trade_intent_readiness=_trial_trade_intent_readiness(admission, service._brc),
        trial_trade_intent_evaluator_factory=_trial_trade_intent_evaluator(admission),
    )
    return admission, engine, binding, service, brc_repo, market


async def _phase10_runtime_start_ready_context(
    execution_mode: AdmissionExecutionMode = AdmissionExecutionMode.OBSERVE_ONLY,
    *,
    trade_intent_ledger_available: bool = True,
):
    admission, engine, decision, acceptance = await _installable_admission(
        execution_mode=execution_mode,
    )
    binding = await _reserve_valid_binding(admission, decision, acceptance)
    service, _, brc_repo, market = await _operation_service(create_campaign=False)
    _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
    _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
    _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
    _, binding = await _prepare_runtime_start_for_binding(admission, service._brc, binding)
    service, _, brc_repo, market = await _operation_service(
        create_campaign=False,
        brc_service=service._brc,
        brc_repo_existing=brc_repo,
        admission_runtime_handoff_readiness=_runtime_handoff_readiness(
            admission,
            service._brc,
            trade_intent_ledger_available=trade_intent_ledger_available,
        ),
        admission_runtime_handoff_preparer_factory=_runtime_handoff_preparer(admission),
    )
    return admission, engine, binding, service, brc_repo, market


async def _phase11_runtime_handoff_ready_context(
    execution_mode: AdmissionExecutionMode = AdmissionExecutionMode.OBSERVE_ONLY,
    *,
    trade_intent_ledger_available: bool = True,
    runtime_state: dict | None = None,
):
    admission, engine, decision, acceptance = await _installable_admission(
        execution_mode=execution_mode,
    )
    binding = await _reserve_valid_binding(admission, decision, acceptance)
    service, _, brc_repo, market = await _operation_service(create_campaign=False)
    _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
    _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
    _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
    _, binding = await _prepare_runtime_start_for_binding(admission, service._brc, binding)
    _, binding = await _prepare_runtime_handoff_for_binding(admission, service._brc, binding)
    service, _, brc_repo, market = await _operation_service(
        create_campaign=False,
        brc_service=service._brc,
        brc_repo_existing=brc_repo,
        runtime_state=runtime_state,
        admission_runtime_start_from_handoff_readiness=_runtime_start_from_handoff_readiness(
            admission,
            service._brc,
            trade_intent_ledger_available=trade_intent_ledger_available,
        ),
        admission_runtime_start_from_handoff_starter_factory=_runtime_start_from_handoff_starter(admission),
    )
    return admission, engine, binding, service, brc_repo, market


async def _phase13_runtime_started_context(
    execution_mode: AdmissionExecutionMode = AdmissionExecutionMode.OBSERVE_ONLY,
    *,
    runtime_state: dict | None = None,
):
    admission, engine, binding, service, brc_repo, market = await _phase11_runtime_handoff_ready_context(
        execution_mode=execution_mode,
    )
    start_preflight = await service.preflight(
        operation_type="start_runtime_from_admission_handoff",
        requested_by="owner",
        input_params={"binding_id": binding.binding_id, "campaign_id": str(binding.campaign_id)},
        source={"kind": "ui"},
    )
    await service.confirm(
        operation_id=start_preflight.operation_id,
        preflight_id=start_preflight.preflight_id,
        confirmed_by="owner",
        confirmation_phrase="CONFIRM_START_ADMISSION_RUNTIME",
        idempotency_key=start_preflight.idempotency_key,
    )
    service, _, brc_repo, market = await _operation_service(
        create_campaign=False,
        brc_service=service._brc,
        brc_repo_existing=brc_repo,
        runtime_state=runtime_state,
        admission_strategy_activation_readiness=_strategy_activation_readiness(
            admission,
            service._brc,
            runtime_state=runtime_state,
        ),
        admission_strategy_activation_preparer_factory=_strategy_activation_preparer(admission),
    )
    return admission, engine, binding, service, brc_repo, market


async def _phase14_strategy_activation_ready_context(
    execution_mode: AdmissionExecutionMode = AdmissionExecutionMode.OBSERVE_ONLY,
    *,
    runtime_state: dict | None = None,
):
    admission, engine, binding, service, brc_repo, market = await _phase13_runtime_started_context(
        execution_mode=execution_mode,
    )
    readiness_preflight = await service.preflight(
        operation_type="prepare_strategy_activation_from_admission_runtime",
        requested_by="owner",
        input_params={"binding_id": binding.binding_id, "campaign_id": str(binding.campaign_id)},
        source={"kind": "ui"},
    )
    await service.confirm(
        operation_id=readiness_preflight.operation_id,
        preflight_id=readiness_preflight.preflight_id,
        confirmed_by="owner",
        confirmation_phrase="CONFIRM_PREPARE_STRATEGY_ACTIVATION",
        idempotency_key=readiness_preflight.idempotency_key,
    )
    service, _, brc_repo, market = await _operation_service(
        create_campaign=False,
        brc_service=service._brc,
        brc_repo_existing=brc_repo,
        runtime_state=runtime_state,
        admission_strategy_state_activation_readiness=_strategy_state_activation_readiness(
            admission,
            service._brc,
            runtime_state=runtime_state,
        ),
        admission_strategy_state_activator_factory=_strategy_state_activator(admission),
    )
    return admission, engine, binding, service, brc_repo, market


async def _phase15_strategy_active_no_execution_context(
    execution_mode: AdmissionExecutionMode = AdmissionExecutionMode.OBSERVE_ONLY,
    *,
    runtime_state: dict | None = None,
):
    admission, engine, binding, service, brc_repo, market = await _phase14_strategy_activation_ready_context(
        execution_mode=execution_mode,
    )
    activation_preflight = await service.preflight(
        operation_type="activate_strategy_from_admission_runtime",
        requested_by="owner",
        input_params={"binding_id": binding.binding_id, "campaign_id": str(binding.campaign_id)},
        source={"kind": "ui"},
    )
    await service.confirm(
        operation_id=activation_preflight.operation_id,
        preflight_id=activation_preflight.preflight_id,
        confirmed_by="owner",
        confirmation_phrase="CONFIRM_ACTIVATE_STRATEGY_NO_EXECUTION",
        idempotency_key=activation_preflight.idempotency_key,
    )
    service, _, brc_repo, market = await _operation_service(
        create_campaign=False,
        brc_service=service._brc,
        brc_repo_existing=brc_repo,
        runtime_state=runtime_state,
        admission_signal_loop_readiness=_signal_loop_readiness(
            admission,
            service._brc,
            runtime_state=runtime_state,
        ),
        admission_signal_loop_preparer_factory=_signal_loop_preparer(admission),
    )
    return admission, engine, binding, service, brc_repo, market


async def _phase16_signal_loop_ready_context(
    execution_mode: AdmissionExecutionMode = AdmissionExecutionMode.OBSERVE_ONLY,
    *,
    runtime_state: dict | None = None,
):
    admission, engine, binding, service, brc_repo, market = await _phase15_strategy_active_no_execution_context(
        execution_mode=execution_mode,
        runtime_state=runtime_state,
    )
    readiness_preflight = await service.preflight(
        operation_type="prepare_signal_loop_from_admission_strategy",
        requested_by="owner",
        input_params={"binding_id": binding.binding_id, "campaign_id": str(binding.campaign_id)},
        source={"kind": "ui"},
    )
    await service.confirm(
        operation_id=readiness_preflight.operation_id,
        preflight_id=readiness_preflight.preflight_id,
        confirmed_by="owner",
        confirmation_phrase="CONFIRM_PREPARE_SIGNAL_LOOP",
        idempotency_key=readiness_preflight.idempotency_key,
    )
    service, _, brc_repo, market = await _operation_service(
        create_campaign=False,
        brc_service=service._brc,
        brc_repo_existing=brc_repo,
        runtime_state=runtime_state,
        admission_signal_loop_start_readiness=_signal_loop_start_readiness(
            admission,
            service._brc,
            runtime_state=runtime_state,
        ),
        admission_signal_loop_starter_factory=_signal_loop_starter(admission),
    )
    return admission, engine, binding, service, brc_repo, market


async def _phase17_signal_loop_started_context(
    execution_mode: AdmissionExecutionMode = AdmissionExecutionMode.OBSERVE_ONLY,
    *,
    runtime_state: dict | None = None,
):
    admission, engine, binding, service, brc_repo, market = await _phase16_signal_loop_ready_context(
        execution_mode=execution_mode,
        runtime_state=runtime_state,
    )
    start_preflight = await service.preflight(
        operation_type="start_signal_loop_from_admission_strategy",
        requested_by="owner",
        input_params={"binding_id": binding.binding_id, "campaign_id": str(binding.campaign_id)},
        source={"kind": "ui"},
    )
    await service.confirm(
        operation_id=start_preflight.operation_id,
        preflight_id=start_preflight.preflight_id,
        confirmed_by="owner",
        confirmation_phrase="CONFIRM_START_SIGNAL_LOOP_NO_SIGNAL",
        idempotency_key=start_preflight.idempotency_key,
    )
    service, _, brc_repo, market = await _operation_service(
        create_campaign=False,
        brc_service=service._brc,
        brc_repo_existing=brc_repo,
        runtime_state=runtime_state,
        admission_signal_evaluation_readiness=_signal_evaluation_readiness(
            admission,
            service._brc,
            runtime_state=runtime_state,
        ),
        admission_signal_evaluator_factory=_signal_evaluator(admission),
    )
    return admission, engine, binding, service, brc_repo, market


async def _phase18_signal_evaluated_context(
    execution_mode: AdmissionExecutionMode = AdmissionExecutionMode.OBSERVE_ONLY,
    *,
    runtime_state: dict | None = None,
    runtime_safety_readiness=None,
    execution_permission_max: ExecutionPermission | None = ExecutionPermission.INTENT_RECORDING,
):
    admission, engine, binding, service, brc_repo, market = await _phase17_signal_loop_started_context(
        execution_mode=execution_mode,
        runtime_state=runtime_state,
    )
    evaluation_preflight = await service.preflight(
        operation_type="evaluate_signal_from_admission_strategy",
        requested_by="owner",
        input_params={
            "binding_id": binding.binding_id,
            "campaign_id": str(binding.campaign_id),
            "signal_snapshot": {"symbol": "ETH/USDT:USDT", "bias": "observe"},
        },
        source={"kind": "ui"},
    )
    await service.confirm(
        operation_id=evaluation_preflight.operation_id,
        preflight_id=evaluation_preflight.preflight_id,
        confirmed_by="owner",
        confirmation_phrase="CONFIRM_EVALUATE_SIGNAL_NO_INTENT",
        idempotency_key=evaluation_preflight.idempotency_key,
    )
    service, _, brc_repo, market = await _operation_service(
        create_campaign=False,
        brc_service=service._brc,
        brc_repo_existing=brc_repo,
        runtime_state=runtime_state,
        signal_trade_intent_readiness=_signal_trade_intent_readiness(admission, service._brc),
        signal_trade_intent_recorder_factory=_signal_trade_intent_recorder(admission),
        runtime_safety_readiness=runtime_safety_readiness,
        execution_permission_max=execution_permission_max,
    )
    return admission, engine, binding, service, brc_repo, market


async def _evaluate_trade_intent(
    service: BrcOperationService,
    *,
    campaign_id: str,
    intended_action: str,
    symbol: str = "ETH/USDT:USDT",
    side: str = "long",
):
    preflight = await service.preflight(
        operation_type="evaluate_trial_trade_intent",
        requested_by="owner",
        input_params={
            "campaign_id": campaign_id,
            "intended_action": intended_action,
            "symbol": symbol,
            "side": side,
            "signal_snapshot": {"signal_id": "sig-1", "confidence": "medium"},
            "market_snapshot": {"mark_price": "3000"},
        },
    )
    if preflight.confirmation_requirement.required:
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_EVALUATE_TRIAL_TRADE_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
    else:
        result = None
    return preflight, result


def _assert_admission_summary_result(
    summary: dict,
    *,
    expected: str = "admit_with_constraints",
) -> None:
    assert summary["admission_result"] == expected
    assert "decision" not in summary


def _assert_trial_trade_intent_projection(
    projection: dict,
    *,
    expected: str,
) -> None:
    assert projection["trial_trade_intent_result"] == expected
    assert "decision" not in projection


@pytest.mark.asyncio
async def test_create_campaign_from_admission_binding_capability_is_campaign_shell_only():
    service, _, _, _ = await _operation_service()
    capabilities = {item.operation_type: item for item in service.capabilities()}

    capability = capabilities["create_campaign_from_admission_binding"]
    assert capability.status == "campaign_shell_creation_available"
    assert capability.executable_through_operation is True
    assert capability.confirmation_required is True
    assert capability.backend_executor == "admission_campaign_shell_creation"
    assert "does not install runtime constraints" in capability.current_reason


@pytest.mark.asyncio
async def test_create_campaign_from_admission_binding_preflight_blocks_missing_binding():
    service, _, _, _ = await _operation_service(
        create_campaign=False,
        admission_campaign_readiness=lambda payload: _async_dict(
            {
                "available": False,
                "ready": False,
                "blockers": ["admission trial binding not found: missing-binding"],
                "warnings": [],
            }
        ),
    )

    preflight = await service.preflight(
        operation_type="create_campaign_from_admission_binding",
        requested_by="owner",
        input_params={"admission_binding_id": "missing-binding"},
    )

    assert preflight.preflight_result == "block"
    assert "admission trial binding not found" in "; ".join(preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_create_campaign_from_admission_binding_preflight_blocks_non_reserved_status():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        await admission._repo.update_admission_trial_binding(
            binding.model_copy(update={"binding_status": AdmissionTrialBindingStatus.PLANNED})
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_campaign_readiness=admission.build_campaign_carrier_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_campaign_from_admission_binding",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert any("not binding_reserved" in item for item in preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_create_campaign_from_admission_binding_preflight_blocks_pending_constraints():
    admission, engine = await _admission_service(adapter=PendingRiskCapitalAdapter())
    try:
        _, _, _, _, request = await _seed_request(
            admission,
            trial_env=TrialEnv.TESTNET,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            mandatory_complete=True,
        )
        decision = await admission.evaluate(request.admission_request_id)
        binding = AdmissionTrialBinding(
            binding_id="binding-pending",
            admission_decision_id=decision.admission_decision_id,
            owner_risk_acceptance_id=None,
            trial_constraint_snapshot_id=decision.trial_constraint_snapshot_id,
            strategy_family_version_id=decision.strategy_family_version_id,
            playbook_id=decision.playbook_id or "PB-004-BRC-CONTROLLED-TESTNET",
            playbook_catalog_snapshot_json=dict(decision.playbook_catalog_snapshot_json),
            trial_env=decision.trial_env,
            trial_stage=decision.trial_stage,
            execution_mode=AdmissionExecutionMode.OBSERVE_ONLY,
            binding_status=AdmissionTrialBindingStatus.BINDING_RESERVED,
            created_by_operation_id="op-pending",
            created_by_preflight_id="pre-pending",
            created_at_ms=1,
            updated_at_ms=1,
        )
        await admission._repo.create_admission_trial_binding(binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_campaign_readiness=admission.build_campaign_carrier_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_campaign_from_admission_binding",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert any("not installable" in item for item in preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_create_campaign_from_admission_binding_preflight_blocks_missing_risk_acceptance():
    admission, engine, decision, _ = await _installable_admission()
    try:
        binding = AdmissionTrialBinding(
            binding_id="binding-missing-acceptance",
            admission_decision_id=decision.admission_decision_id,
            owner_risk_acceptance_id=None,
            trial_constraint_snapshot_id=decision.trial_constraint_snapshot_id,
            strategy_family_version_id=decision.strategy_family_version_id,
            playbook_id=decision.playbook_id or "PB-004-BRC-CONTROLLED-TESTNET",
            playbook_catalog_snapshot_json=dict(decision.playbook_catalog_snapshot_json),
            trial_env=decision.trial_env,
            trial_stage=decision.trial_stage,
            execution_mode=decision.execution_mode,
            binding_status=AdmissionTrialBindingStatus.BINDING_RESERVED,
            created_by_operation_id="op-missing-acceptance",
            created_by_preflight_id="pre-missing-acceptance",
            created_at_ms=1,
            updated_at_ms=1,
        )
        await admission._repo.create_admission_trial_binding(binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_campaign_readiness=admission.build_campaign_carrier_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_campaign_from_admission_binding",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "owner risk acceptance required for funded_validation binding" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_create_campaign_from_admission_binding_preflight_blocks_mismatched_risk_acceptance():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        mismatched = decision.model_copy(
            update={"admission_decision_id": "admission-decision-mismatch-for-campaign"}
        )
        await admission._repo.create_admission_decision(mismatched)
        binding = AdmissionTrialBinding(
            binding_id="binding-mismatch-acceptance",
            admission_decision_id=mismatched.admission_decision_id,
            owner_risk_acceptance_id=acceptance.owner_risk_acceptance_id,
            trial_constraint_snapshot_id=mismatched.trial_constraint_snapshot_id,
            strategy_family_version_id=mismatched.strategy_family_version_id,
            playbook_id=mismatched.playbook_id or "PB-004-BRC-CONTROLLED-TESTNET",
            playbook_catalog_snapshot_json=dict(mismatched.playbook_catalog_snapshot_json),
            trial_env=mismatched.trial_env,
            trial_stage=mismatched.trial_stage,
            execution_mode=mismatched.execution_mode,
            binding_status=AdmissionTrialBindingStatus.BINDING_RESERVED,
            created_by_operation_id="op-mismatch-acceptance",
            created_by_preflight_id="pre-mismatch-acceptance",
            created_at_ms=1,
            updated_at_ms=1,
        )
        await admission._repo.create_admission_trial_binding(binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_campaign_readiness=admission.build_campaign_carrier_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_campaign_from_admission_binding",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "owner risk acceptance decision mismatch" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_create_campaign_from_admission_binding_preflight_blocks_live_bad_account_facts():
    admission, engine = await _admission_service()
    try:
        _, _, _, _, request = await _seed_request(
            admission,
            trial_env=TrialEnv.LIVE,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            mandatory_complete=True,
            account_facts_snapshot_ref=None,
            account_facts_snapshot_json={"source": "unavailable", "truth_level": "unavailable"},
        )
        decision = await admission.evaluate(request.admission_request_id)
        binding = AdmissionTrialBinding(
            binding_id="binding-live-bad-account-facts",
            admission_decision_id=decision.admission_decision_id,
            owner_risk_acceptance_id=None,
            trial_constraint_snapshot_id=decision.trial_constraint_snapshot_id,
            strategy_family_version_id=decision.strategy_family_version_id,
            playbook_id=decision.playbook_id or "PB-004-BRC-CONTROLLED-TESTNET",
            playbook_catalog_snapshot_json=dict(decision.playbook_catalog_snapshot_json),
            trial_env=decision.trial_env,
            trial_stage=decision.trial_stage,
            execution_mode=decision.execution_mode,
            binding_status=AdmissionTrialBindingStatus.BINDING_RESERVED,
            created_by_operation_id="op-live-bad-facts",
            created_by_preflight_id="pre-live-bad-facts",
            created_at_ms=1,
            updated_at_ms=1,
        )
        await admission._repo.create_admission_trial_binding(binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_campaign_readiness=admission.build_campaign_carrier_preflight_readiness,
        )
        preflight = await service.preflight(
            operation_type="create_campaign_from_admission_binding",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "account facts unavailable" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_create_campaign_from_admission_binding_confirm_creates_campaign_shell_only():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            admission_campaign_readiness=admission.build_campaign_carrier_preflight_readiness,
            admission_campaign_creator_factory=_campaign_creator(admission),
        )
        preflight = await service.preflight(
            operation_type="create_campaign_from_admission_binding",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_CREATE_ADMISSION_CAMPAIGN_SHELL",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
        second = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_CREATE_ADMISSION_CAMPAIGN_SHELL",
            idempotency_key=preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "allow"
    _assert_admission_summary_result(preflight.admission_summary)
    assert preflight.after["campaign_shell_creation_only"] is True
    assert preflight.campaign_shell_summary["would_create_campaign_shell"] is True
    assert result.status == "executed"
    assert second.status == "executed"
    assert result.result_summary["planned_result_status"] == "campaign_created"
    assert result.result_summary["campaign_created"] is True
    assert result.result_summary["runtime_installed"] is False
    assert result.result_summary["runtime_started"] is False
    assert result.result_summary["strategy_active"] is False
    assert result.result_summary["constraints_installed"] is False
    assert result.result_summary["orders_placed"] is False
    assert brc_repo.campaign is not None
    assert brc_repo.campaign.status == BrcCampaignStatus.OBSERVE
    assert brc_repo.campaign.metadata_json["created_from_admission"] is True
    assert brc_repo.campaign.metadata_json["runtime_status"] == "not_installed"
    assert brc_repo.campaign.metadata_json["strategy_status"] == "not_active"
    assert brc_repo.campaign.metadata_json["constraints_installed"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.CAMPAIGN_CREATED
    assert updated_binding.campaign_id == brc_repo.campaign.campaign_id
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_campaign_shell_created"]) == 1


@pytest.mark.asyncio
async def test_create_campaign_from_admission_binding_blocks_rejected_admission():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        rejected = decision.model_copy(
            update={
                "admission_decision_id": "admission-decision-rejected-for-campaign",
                "decision": AdmissionDecisionValue.REJECT,
            }
        )
        await admission._repo.create_admission_decision(rejected)
        binding = AdmissionTrialBinding(
            binding_id="binding-rejected-decision",
            admission_decision_id=rejected.admission_decision_id,
            owner_risk_acceptance_id=acceptance.owner_risk_acceptance_id,
            trial_constraint_snapshot_id=rejected.trial_constraint_snapshot_id,
            strategy_family_version_id=rejected.strategy_family_version_id,
            playbook_id=rejected.playbook_id or "PB-004-BRC-CONTROLLED-TESTNET",
            playbook_catalog_snapshot_json=dict(rejected.playbook_catalog_snapshot_json),
            trial_env=rejected.trial_env,
            trial_stage=rejected.trial_stage,
            execution_mode=rejected.execution_mode,
            binding_status=AdmissionTrialBindingStatus.BINDING_RESERVED,
            created_by_operation_id="op-rejected-binding",
            created_by_preflight_id="pre-rejected-binding",
            created_at_ms=1,
            updated_at_ms=1,
        )
        await admission._repo.create_admission_trial_binding(binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_campaign_readiness=admission.build_campaign_carrier_preflight_readiness,
            admission_campaign_creator_factory=_campaign_creator(admission),
        )
        preflight = await service.preflight(
            operation_type="create_campaign_from_admission_binding",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert any("not admissible" in item for item in preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_install_runtime_constraints_preflight_blocks_non_campaign_created_binding():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_runtime_constraint_readiness=lambda payload: _async_dict(
                {
                    "available": True,
                    "ready": False,
                    "blockers": [
                        f"admission trial binding is {binding.binding_status.value}, not campaign_created"
                    ],
                    "warnings": [],
                }
            ),
        )
        preflight = await service.preflight(
            operation_type="install_runtime_constraints_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert any("not campaign_created" in item for item in preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_install_runtime_constraints_preflight_blocks_missing_campaign_id():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        await admission._repo.update_admission_trial_binding(
            binding.model_copy(update={"binding_status": AdmissionTrialBindingStatus.CAMPAIGN_CREATED})
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_runtime_constraint_readiness=lambda payload: _async_dict(
                {
                    "available": True,
                    "ready": False,
                    "blockers": ["admission trial binding missing campaign_id"],
                    "warnings": [],
                }
            ),
        )
        preflight = await service.preflight(
            operation_type="install_runtime_constraints_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "admission trial binding missing campaign_id" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_install_runtime_constraints_preflight_blocks_pending_constraints():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        async with engine.begin() as conn:
            await conn.execute(
                PGBrcTrialConstraintSnapshotORM.__table__.update()
                .where(
                    PGBrcTrialConstraintSnapshotORM.trial_constraint_snapshot_id
                    == decision.trial_constraint_snapshot_id
                )
                .values(status=TrialConstraintSnapshotStatus.PENDING_RISK_CAPITAL_RESOLUTION.value)
            )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_constraint_readiness=_runtime_constraint_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="install_runtime_constraints_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert brc_repo.campaign is not None
    assert preflight.preflight_result == "block"
    assert any("not installable" in item for item in preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_install_runtime_constraints_preflight_blocks_mismatched_campaign_metadata():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={
                "metadata_json": {
                    **brc_repo.campaign.metadata_json,
                    "admission_decision_id": "wrong-decision",
                }
            }
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_constraint_readiness=_runtime_constraint_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="install_runtime_constraints_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata admission_decision_id mismatch" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_install_runtime_constraints_preflight_allows_valid_campaign_created_installable_constraints():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, _, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=None,
            admission_runtime_constraint_readiness=_runtime_constraint_readiness(admission, service._brc),
            admission_runtime_constraint_installer_factory=_runtime_constraint_installer(admission),
        )
        preflight = await service.preflight(
            operation_type="install_runtime_constraints_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "allow"
    assert preflight.after["runtime_constraint_installation_only"] is True
    assert preflight.constraints_summary["status"] == "installable"
    assert preflight.campaign_shell_summary["constraints_would_be_installed"] is True
    assert preflight.campaign_shell_summary["runtime_will_start"] is False
    assert preflight.campaign_shell_summary["strategy_will_activate"] is False
    assert preflight.campaign_shell_summary["orders_will_be_placed"] is False
    assert preflight.campaign_shell_summary["trial_remains_inactive_after_install"] is True


@pytest.mark.asyncio
async def test_install_runtime_constraints_confirm_installs_metadata_without_runtime_or_orders():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, market = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        service, _, brc_repo, market = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_constraint_readiness=_runtime_constraint_readiness(admission, service._brc),
            admission_runtime_constraint_installer_factory=_runtime_constraint_installer(admission),
        )
        preflight = await service.preflight(
            operation_type="install_runtime_constraints_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_INSTALL_ADMISSION_CAMPAIGN_CONSTRAINTS",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
        second_same_operation = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_INSTALL_ADMISSION_CAMPAIGN_CONSTRAINTS",
            idempotency_key=preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert second_same_operation.status == "executed"
    _assert_admission_summary_result(preflight.admission_summary)
    assert result.result_summary["constraints_installed"] is True
    assert result.result_summary["runtime_status"] == "constraints_installed_not_started"
    assert result.result_summary["runtime_started"] is False
    assert result.result_summary["runtime_active"] is False
    assert result.result_summary["strategy_active"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["owner_confirm_each_entry_enabled"] is False
    assert result.result_summary["orders_placed"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.status == BrcCampaignStatus.OBSERVE
    assert brc_repo.campaign.attempt_count == 0
    assert brc_repo.campaign.metadata_json["constraints_installed"] is True
    assert brc_repo.campaign.metadata_json["installed_constraint_snapshot_id"] == decision.trial_constraint_snapshot_id
    assert brc_repo.campaign.metadata_json["runtime_status"] == "constraints_installed_not_started"
    assert brc_repo.campaign.metadata_json["strategy_status"] == "not_active"
    assert brc_repo.campaign.metadata_json["runtime_started"] is False
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_constraints_installed"]) == 1


@pytest.mark.asyncio
async def test_install_runtime_constraints_double_confirm_is_idempotent():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_constraint_readiness=_runtime_constraint_readiness(admission, service._brc),
            admission_runtime_constraint_installer_factory=_runtime_constraint_installer(admission),
        )
        first_preflight = await service.preflight(
            operation_type="install_runtime_constraints_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=first_preflight.operation_id,
            preflight_id=first_preflight.preflight_id,
            confirmation_phrase="CONFIRM_INSTALL_ADMISSION_CAMPAIGN_CONSTRAINTS",
            idempotency_key=first_preflight.idempotency_key,
        )
        second_preflight = await service.preflight(
            operation_type="install_runtime_constraints_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        second = await service.confirm(
            operation_id=second_preflight.operation_id,
            preflight_id=second_preflight.preflight_id,
            confirmation_phrase="CONFIRM_INSTALL_ADMISSION_CAMPAIGN_CONSTRAINTS",
            idempotency_key=second_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second_preflight.preflight_result in {"allow", "warn"}
    assert second_preflight.after["idempotent_install"] is True
    assert second.status == "noop"
    assert second.result_summary["idempotent"] is True
    assert second.result_summary["runtime_started"] is False
    assert second.result_summary["strategy_active"] is False
    assert second.result_summary["orders_placed"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_constraints_installed"]) == 1


@pytest.mark.asyncio
async def test_prepare_runtime_carrier_preflight_blocks_non_runtime_constraints_installed_binding():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_carrier_readiness=_runtime_carrier_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert any("not runtime_constraints_installed" in item for item in preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_prepare_runtime_carrier_preflight_blocks_missing_campaign_id():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        await admission._repo.update_admission_trial_binding(
            binding.model_copy(
                update={"binding_status": AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED}
            )
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            admission_runtime_carrier_readiness=lambda payload: _async_dict(
                {
                    "available": True,
                    "ready": False,
                    "blockers": ["admission trial binding missing campaign_id"],
                    "warnings": [],
                }
            ),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "admission trial binding missing campaign_id" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_carrier_preflight_blocks_constraints_installed_false():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        binding = await admission.mark_admission_trial_binding_runtime_constraints_installed(
            binding_id=binding.binding_id,
            campaign_id=str(binding.campaign_id),
            operation_id="op-fake-installed-binding",
            preflight_id="pre-fake-installed-binding",
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_carrier_readiness=_runtime_carrier_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata constraints_installed is not true" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_carrier_preflight_blocks_runtime_started_true():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "runtime_started": True}}
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_carrier_readiness=_runtime_carrier_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_started is not false" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_carrier_preflight_blocks_strategy_active_true():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "strategy_active": True}}
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_carrier_readiness=_runtime_carrier_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata strategy_active is not false" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_carrier_preflight_blocks_orders_placed_true():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "orders_placed": True}}
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_carrier_readiness=_runtime_carrier_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata orders_placed is not false" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_carrier_preflight_allows_valid_constraints_installed_campaign():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_carrier_readiness=_runtime_carrier_readiness(admission, service._brc),
            admission_runtime_carrier_preparer_factory=_runtime_carrier_preparer(admission),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "allow"
    assert preflight.after["runtime_carrier_readiness_only"] is True
    assert preflight.runtime_carrier_summary["carrier_readiness_would_be_prepared"] is True
    assert preflight.runtime_carrier_summary["runtime_will_start"] is False
    assert preflight.runtime_carrier_summary["strategy_will_activate"] is False
    assert preflight.runtime_carrier_summary["auto_execution_will_be_enabled"] is False
    assert preflight.runtime_carrier_summary["orders_will_be_placed"] is False
    assert preflight.runtime_carrier_summary["trial_remains_inactive_after_readiness_preparation"] is True


@pytest.mark.asyncio
async def test_prepare_runtime_carrier_confirm_writes_metadata_without_runtime_strategy_or_orders():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, market = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        service, _, brc_repo, market = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_carrier_readiness=_runtime_carrier_readiness(admission, service._brc),
            admission_runtime_carrier_preparer_factory=_runtime_carrier_preparer(admission),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_CARRIER",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["carrier_ready"] is True
    assert result.result_summary["runtime_status"] == "carrier_ready_not_started"
    assert result.result_summary["runtime_started"] is False
    assert result.result_summary["runtime_active"] is False
    assert result.result_summary["strategy_active"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["orders_placed"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.status == BrcCampaignStatus.OBSERVE
    assert brc_repo.campaign.attempt_count == 0
    assert brc_repo.campaign.metadata_json["carrier_ready"] is True
    assert brc_repo.campaign.metadata_json["runtime_status"] == "carrier_ready_not_started"
    assert brc_repo.campaign.metadata_json["prepared_by_operation_id"] == preflight.operation_id
    assert brc_repo.campaign.metadata_json["prepared_by_preflight_id"] == preflight.preflight_id
    assert brc_repo.campaign.metadata_json["runtime_started"] is False
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_carrier_ready"]) == 1


@pytest.mark.asyncio
async def test_prepare_runtime_carrier_double_confirm_is_idempotent():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_carrier_readiness=_runtime_carrier_readiness(admission, service._brc),
            admission_runtime_carrier_preparer_factory=_runtime_carrier_preparer(admission),
        )
        first_preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=first_preflight.operation_id,
            preflight_id=first_preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_CARRIER",
            idempotency_key=first_preflight.idempotency_key,
        )
        second_preflight = await service.preflight(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        second = await service.confirm(
            operation_id=second_preflight.operation_id,
            preflight_id=second_preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_CARRIER",
            idempotency_key=second_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second_preflight.preflight_result in {"allow", "warn"}
    assert second_preflight.after["idempotent_prepare"] is True
    assert second.status == "noop"
    assert second.result_summary["idempotent"] is True
    assert second.result_summary["runtime_started"] is False
    assert second.result_summary["strategy_active"] is False
    assert second.result_summary["orders_placed"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_carrier_ready"]) == 1


@pytest.mark.asyncio
async def test_prepare_runtime_start_preflight_blocks_non_carrier_ready_campaign():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_start_readiness=_runtime_start_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_start_from_admission_carrier",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata carrier_ready is not true" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_start_preflight_blocks_runtime_started_true():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "runtime_started": True}}
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_start_readiness=_runtime_start_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_start_from_admission_carrier",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_started is not false" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_start_preflight_blocks_strategy_active_true():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "strategy_active": True}}
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_start_readiness=_runtime_start_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_start_from_admission_carrier",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata strategy_active is not false" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_start_preflight_blocks_trial_started_true():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "trial_started": True}}
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_start_readiness=_runtime_start_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_start_from_admission_carrier",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata trial_started is not false" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_start_preflight_blocks_orders_placed_true():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "orders_placed": True}}
        )
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_start_readiness=_runtime_start_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_start_from_admission_carrier",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata orders_placed is not false" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_prepare_runtime_start_preflight_allows_valid_carrier_ready_campaign():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
        service, _, _, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_start_readiness=_runtime_start_readiness(admission, service._brc),
            admission_runtime_start_preparer_factory=_runtime_start_preparer(admission),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_start_from_admission_carrier",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result in {"allow", "warn"}
    assert preflight.after["runtime_start_readiness_only"] is True
    assert preflight.runtime_start_summary["runtime_start_readiness_would_be_prepared"] is True
    assert preflight.runtime_start_summary["runtime_will_start"] is False
    assert preflight.runtime_start_summary["strategy_will_activate"] is False
    assert preflight.runtime_start_summary["auto_execution_will_be_enabled"] is False
    assert preflight.runtime_start_summary["orders_will_be_placed"] is False
    assert preflight.runtime_start_summary["next_phase_must_handle_execution_mode_enforcement"] is True


@pytest.mark.asyncio
async def test_prepare_runtime_start_confirm_writes_metadata_without_runtime_strategy_or_orders():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, market = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
        service, _, brc_repo, market = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_start_readiness=_runtime_start_readiness(admission, service._brc),
            admission_runtime_start_preparer_factory=_runtime_start_preparer(admission),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_start_from_admission_carrier",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_START",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["runtime_start_ready"] is True
    assert result.result_summary["runtime_status"] == "runtime_start_ready_not_started"
    assert result.result_summary["runtime_started"] is False
    assert result.result_summary["runtime_active"] is False
    assert result.result_summary["strategy_active"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["orders_placed"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.status == BrcCampaignStatus.OBSERVE
    assert brc_repo.campaign.attempt_count == 0
    assert brc_repo.campaign.metadata_json["runtime_start_ready"] is True
    assert brc_repo.campaign.metadata_json["runtime_status"] == "runtime_start_ready_not_started"
    assert brc_repo.campaign.metadata_json["start_ready_by_operation_id"] == preflight.operation_id
    assert brc_repo.campaign.metadata_json["start_ready_by_preflight_id"] == preflight.preflight_id
    assert brc_repo.campaign.metadata_json["runtime_started"] is False
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_start_ready"]) == 1


@pytest.mark.asyncio
async def test_prepare_runtime_start_double_confirm_is_idempotent():
    admission, engine, decision, acceptance = await _installable_admission()
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_start_readiness=_runtime_start_readiness(admission, service._brc),
            admission_runtime_start_preparer_factory=_runtime_start_preparer(admission),
        )
        first_preflight = await service.preflight(
            operation_type="prepare_runtime_start_from_admission_carrier",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=first_preflight.operation_id,
            preflight_id=first_preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_START",
            idempotency_key=first_preflight.idempotency_key,
        )
        second_preflight = await service.preflight(
            operation_type="prepare_runtime_start_from_admission_carrier",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        second = await service.confirm(
            operation_id=second_preflight.operation_id,
            preflight_id=second_preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_START",
            idempotency_key=second_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second_preflight.preflight_result in {"allow", "warn"}
    assert second_preflight.after["idempotent_prepare"] is True
    assert second.status == "noop"
    assert second.result_summary["idempotent"] is True
    assert second.result_summary["runtime_started"] is False
    assert second.result_summary["strategy_active"] is False
    assert second.result_summary["orders_placed"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_start_ready"]) == 1


@pytest.mark.asyncio
async def test_observe_only_records_would_enter_intent_with_no_order():
    admission, engine, _, service, brc_repo, market = await _phase9_runtime_start_ready_context(
        AdmissionExecutionMode.OBSERVE_ONLY
    )
    try:
        preflight, result = await _evaluate_trade_intent(
            service,
            campaign_id=brc_repo.campaign.campaign_id,
            intended_action="entry",
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "allow"
    _assert_trial_trade_intent_projection(preflight.after["enforcement"], expected="recorded")
    _assert_trial_trade_intent_projection(preflight.trade_intent_summary, expected="recorded")
    assert result.status == "executed"
    assert result.result_summary["trial_trade_intent_result"] == "recorded"
    assert "decision" not in result.result_summary
    assert result.result_summary["intent_persisted"] is True
    assert result.result_summary["trial_trade_intent_is_order"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["runtime_started"] is False
    assert result.result_summary["strategy_active"] is False
    assert result.result_summary["orders_placed"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.attempt_count == 0
    assert len(intents) == 1
    assert intents[0].decision.value == "recorded"
    assert intents[0].intended_action == "entry"


@pytest.mark.asyncio
async def test_no_entry_blocks_entry_intent_without_execution():
    admission, engine, _, service, brc_repo, _ = await _phase9_runtime_start_ready_context(
        AdmissionExecutionMode.NO_ENTRY
    )
    try:
        preflight, result = await _evaluate_trade_intent(
            service,
            campaign_id=brc_repo.campaign.campaign_id,
            intended_action="entry",
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "warn"
    _assert_trial_trade_intent_projection(preflight.after["enforcement"], expected="blocked")
    _assert_trial_trade_intent_projection(preflight.trade_intent_summary, expected="blocked")
    assert result.status == "executed"
    assert result.result_summary["trial_trade_intent_result"] == "blocked"
    assert "decision" not in result.result_summary
    assert "no_entry blocks entry" in result.result_summary["not_executed_reason"]
    assert result.result_summary["order_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert len(intents) == 1
    assert intents[0].decision.value == "blocked"
    assert intents[0].not_executed_reason == "no_entry blocks entry and increase intents"


@pytest.mark.asyncio
async def test_no_entry_records_exit_reduce_intent_without_execution():
    admission, engine, _, service, brc_repo, _ = await _phase9_runtime_start_ready_context(
        AdmissionExecutionMode.NO_ENTRY
    )
    try:
        preflight, result = await _evaluate_trade_intent(
            service,
            campaign_id=brc_repo.campaign.campaign_id,
            intended_action="reduce",
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "allow"
    assert result.status == "executed"
    assert result.result_summary["trial_trade_intent_result"] == "recorded"
    assert "decision" not in result.result_summary
    assert result.result_summary["order_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert len(intents) == 1
    assert intents[0].decision.value == "recorded"
    assert intents[0].intended_action == "reduce"


@pytest.mark.asyncio
async def test_auto_within_budget_checks_constraints_but_does_not_execute_or_persist_order():
    admission, engine, _, service, brc_repo, _ = await _phase9_runtime_start_ready_context(
        AdmissionExecutionMode.AUTO_WITHIN_BUDGET
    )
    try:
        preflight, result = await _evaluate_trade_intent(
            service,
            campaign_id=brc_repo.campaign.campaign_id,
            intended_action="entry",
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "warn"
    assert preflight.after["constraints_check"]["complete"] is True
    _assert_trial_trade_intent_projection(preflight.after["enforcement"], expected="unavailable")
    _assert_trial_trade_intent_projection(preflight.trade_intent_summary, expected="unavailable")
    assert preflight.after["enforcement"]["would_require_runtime_execution"] is True
    assert result.status == "executed"
    assert result.result_summary["trial_trade_intent_result"] == "unavailable"
    assert "decision" not in result.result_summary
    assert result.result_summary["would_require_runtime_execution"] is True
    assert result.result_summary["intent_persisted"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert intents == []


@pytest.mark.asyncio
async def test_owner_confirm_each_entry_returns_not_implemented_unavailable():
    admission, engine, _, service, brc_repo, _ = await _phase9_runtime_start_ready_context(
        AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY
    )
    try:
        preflight, result = await _evaluate_trade_intent(
            service,
            campaign_id=brc_repo.campaign.campaign_id,
            intended_action="entry",
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "unavailable"
    assert preflight.confirmation_requirement.required is False
    assert result is None
    assert "owner_confirm_each_entry execution is reserved and not implemented" in preflight.risk_summary["blockers"]
    assert intents == []


@pytest.mark.asyncio
async def test_trial_trade_intent_ledger_is_not_treated_as_order():
    admission, engine, _, service, brc_repo, market = await _phase9_runtime_start_ready_context(
        AdmissionExecutionMode.OBSERVE_ONLY
    )
    try:
        _, result = await _evaluate_trade_intent(
            service,
            campaign_id=brc_repo.campaign.campaign_id,
            intended_action="entry",
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert len(intents) == 1
    assert result.result_summary["intent_id"] == intents[0].intent_id
    assert result.result_summary["trial_trade_intent_is_order"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert market["open_order_count"] == 0
    assert brc_repo.campaign.metadata_json["orders_placed"] is False


@pytest.mark.asyncio
async def test_trial_trade_intent_preflight_blocks_missing_runtime_start_ready():
    admission, engine, decision, acceptance = await _installable_admission(
        execution_mode=AdmissionExecutionMode.OBSERVE_ONLY
    )
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            trial_trade_intent_readiness=_trial_trade_intent_readiness(admission, service._brc),
            trial_trade_intent_evaluator_factory=_trial_trade_intent_evaluator(admission),
        )
        preflight = await service.preflight(
            operation_type="evaluate_trial_trade_intent",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "signal_snapshot": {},
                "market_snapshot": {},
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_start_ready is not true" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_trial_trade_intent_preflight_blocks_runtime_started_true():
    admission, engine, _, service, brc_repo, _ = await _phase9_runtime_start_ready_context(
        AdmissionExecutionMode.OBSERVE_ONLY
    )
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "runtime_started": True}}
        )
        preflight = await service.preflight(
            operation_type="evaluate_trial_trade_intent",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "signal_snapshot": {},
                "market_snapshot": {},
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_started is not false" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_runtime_handoff_preflight_blocks_missing_runtime_start_ready():
    admission, engine, decision, acceptance = await _installable_admission(
        execution_mode=AdmissionExecutionMode.OBSERVE_ONLY
    )
    try:
        binding = await _reserve_valid_binding(admission, decision, acceptance)
        service, _, brc_repo, _ = await _operation_service(create_campaign=False)
        _, binding = await _create_campaign_shell_for_binding(admission, service._brc, binding)
        _, binding = await _install_constraints_for_binding(admission, service._brc, binding)
        _, binding = await _prepare_carrier_for_binding(admission, service._brc, binding)
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_handoff_readiness=_runtime_handoff_readiness(admission, service._brc),
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_handoff_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_start_ready is not true" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("runtime_started", "campaign metadata runtime_started is not false"),
        ("strategy_active", "campaign metadata strategy_active is not false"),
        ("trial_started", "campaign metadata trial_started is not false"),
        ("orders_placed", "campaign metadata orders_placed is not false"),
    ],
)
async def test_runtime_handoff_preflight_blocks_active_or_order_flags(flag, message):
    admission, engine, binding, service, brc_repo, _ = await _phase10_runtime_start_ready_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, flag: True}}
        )
        preflight = await service.preflight(
            operation_type="prepare_runtime_handoff_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert message in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_runtime_handoff_preflight_blocks_missing_execution_mode():
    admission, engine, binding, service, brc_repo, _ = await _phase10_runtime_start_ready_context()
    try:
        metadata = dict(brc_repo.campaign.metadata_json)
        metadata.pop("execution_mode", None)
        brc_repo.campaign = brc_repo.campaign.model_copy(update={"metadata_json": metadata})
        preflight = await service.preflight(
            operation_type="prepare_runtime_handoff_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata execution_mode is missing or invalid" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_runtime_handoff_preflight_blocks_missing_trade_intent_ledger_for_observe_only():
    admission, engine, binding, service, brc_repo, _ = await _phase10_runtime_start_ready_context(
        AdmissionExecutionMode.OBSERVE_ONLY,
        trade_intent_ledger_available=False,
    )
    try:
        preflight = await service.preflight(
            operation_type="prepare_runtime_handoff_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "observe_only trade intent ledger support unavailable" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_runtime_handoff_preflight_allows_valid_runtime_start_ready_campaign():
    admission, engine, binding, service, brc_repo, _ = await _phase10_runtime_start_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="prepare_runtime_handoff_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result in {"allow", "warn"}
    assert preflight.after["runtime_handoff_readiness_only"] is True
    assert preflight.runtime_handoff_summary["runtime_handoff_readiness_would_be_prepared"] is True
    assert preflight.runtime_handoff_summary["runtime_will_start"] is False
    assert preflight.runtime_handoff_summary["strategy_will_activate"] is False
    assert preflight.runtime_handoff_summary["auto_execution_will_be_enabled"] is False
    assert preflight.runtime_handoff_summary["orders_will_be_placed"] is False
    assert preflight.runtime_handoff_summary["next_phase_must_explicitly_start_runtime"] is True
    assert brc_repo.campaign.metadata_json["runtime_started"] is False


@pytest.mark.asyncio
async def test_runtime_handoff_confirm_writes_metadata_without_runtime_strategy_or_orders():
    admission, engine, binding, service, brc_repo, market = await _phase10_runtime_start_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="prepare_runtime_handoff_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_HANDOFF",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["runtime_handoff_ready"] is True
    assert result.result_summary["runtime_status"] == "runtime_handoff_ready_not_started"
    assert result.result_summary["runtime_started"] is False
    assert result.result_summary["strategy_active"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["orders_placed"] is False
    assert result.result_summary["live_ready"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.status == BrcCampaignStatus.OBSERVE
    assert brc_repo.campaign.attempt_count == 0
    assert brc_repo.campaign.metadata_json["runtime_handoff_ready"] is True
    assert brc_repo.campaign.metadata_json["runtime_status"] == "runtime_handoff_ready_not_started"
    assert brc_repo.campaign.metadata_json["handoff_ready_by_operation_id"] == preflight.operation_id
    assert brc_repo.campaign.metadata_json["handoff_ready_by_preflight_id"] == preflight.preflight_id
    assert brc_repo.campaign.metadata_json["runtime_started"] is False
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_handoff_ready"]) == 1


@pytest.mark.asyncio
async def test_runtime_handoff_double_confirm_is_idempotent():
    admission, engine, binding, service, brc_repo, _ = await _phase10_runtime_start_ready_context()
    try:
        first_preflight = await service.preflight(
            operation_type="prepare_runtime_handoff_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=first_preflight.operation_id,
            preflight_id=first_preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_HANDOFF",
            idempotency_key=first_preflight.idempotency_key,
        )
        second_preflight = await service.preflight(
            operation_type="prepare_runtime_handoff_from_admission_campaign",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        second = await service.confirm(
            operation_id=second_preflight.operation_id,
            preflight_id=second_preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_HANDOFF",
            idempotency_key=second_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second_preflight.preflight_result in {"allow", "warn"}
    assert second_preflight.after["idempotent_prepare"] is True
    assert second.status == "noop"
    assert second.result_summary["idempotent"] is True
    assert second.result_summary["runtime_started"] is False
    assert second.result_summary["strategy_active"] is False
    assert second.result_summary["orders_placed"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_handoff_ready"]) == 1


@pytest.mark.asyncio
async def test_start_runtime_from_handoff_preflight_blocks_missing_runtime_handoff_ready():
    admission, engine, binding, service, brc_repo, _ = await _phase10_runtime_start_ready_context()
    try:
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_runtime_start_from_handoff_readiness=_runtime_start_from_handoff_readiness(
                admission,
                service._brc,
            ),
        )
        preflight = await service.preflight(
            operation_type="start_runtime_from_admission_handoff",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_handoff_ready is not true" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("runtime_started", "campaign metadata runtime_started is true outside runtime_started_strategy_inactive noop path"),
        ("strategy_active", "campaign metadata strategy_active is not false"),
        ("trial_started", "campaign metadata trial_started is not false"),
        ("orders_placed", "campaign metadata orders_placed is not false"),
    ],
)
async def test_start_runtime_from_handoff_preflight_blocks_active_or_order_flags(flag, message):
    admission, engine, binding, service, brc_repo, _ = await _phase11_runtime_handoff_ready_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, flag: True}}
        )
        preflight = await service.preflight(
            operation_type="start_runtime_from_admission_handoff",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert message in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_start_runtime_from_handoff_preflight_checks_execution_mode_contract():
    admission, engine, binding, service, brc_repo, _ = await _phase11_runtime_handoff_ready_context(
        AdmissionExecutionMode.OBSERVE_ONLY,
        trade_intent_ledger_available=False,
    )
    try:
        preflight = await service.preflight(
            operation_type="start_runtime_from_admission_handoff",
            requested_by="owner",
            input_params={"campaign_id": brc_repo.campaign.campaign_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "observe_only trade intent ledger support unavailable" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_start_runtime_from_handoff_preflight_allows_valid_handoff_ready_campaign():
    admission, engine, binding, service, brc_repo, _ = await _phase11_runtime_handoff_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="start_runtime_from_admission_handoff",
            requested_by="owner",
            input_params={"campaign_id": brc_repo.campaign.campaign_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result in {"allow", "warn"}
    assert preflight.after["runtime_start_preflight_only"] is False
    assert preflight.after["runtime_state_start_only"] is True
    assert preflight.after["confirm_disabled"] is False
    assert preflight.confirmation_requirement.required is True
    assert preflight.runtime_start_summary["start_would_be_possible"] is True
    assert preflight.runtime_start_summary["runtime_state_can_be_started"] is True
    assert preflight.runtime_start_summary["runtime_started_after_confirm"] is True
    assert preflight.runtime_start_summary["strategy_will_activate"] is False
    assert preflight.runtime_start_summary["auto_execution_will_be_enabled"] is False
    assert preflight.runtime_start_summary["orders_will_be_placed"] is False
    assert (
        preflight.runtime_start_summary["next_required_implementation"]
        == "strategy activation / execution mode runtime enforcement Operation"
    )
    assert brc_repo.campaign.metadata_json["runtime_handoff_ready"] is True
    assert brc_repo.campaign.metadata_json["runtime_started"] is False
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False


@pytest.mark.asyncio
async def test_start_runtime_from_handoff_confirm_sets_runtime_started_without_strategy_trial_or_orders():
    admission, engine, binding, service, brc_repo, market = await _phase11_runtime_handoff_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="start_runtime_from_admission_handoff",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_START_ADMISSION_RUNTIME",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["runtime_status"] == "runtime_started_strategy_inactive"
    assert result.result_summary["runtime_started"] is True
    assert result.result_summary["strategy_active"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["auto_execution_enabled"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["orders_placed"] is False
    assert result.result_summary["live_ready"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.status == BrcCampaignStatus.OBSERVE
    assert brc_repo.campaign.attempt_count == 0
    assert brc_repo.campaign.metadata_json["constraints_installed"] is True
    assert brc_repo.campaign.metadata_json["carrier_ready"] is True
    assert brc_repo.campaign.metadata_json["runtime_start_ready"] is True
    assert brc_repo.campaign.metadata_json["runtime_handoff_ready"] is True
    assert brc_repo.campaign.metadata_json["runtime_status"] == "runtime_started_strategy_inactive"
    assert brc_repo.campaign.metadata_json["runtime_started"] is True
    assert brc_repo.campaign.metadata_json["runtime_started_by_operation_id"] == preflight.operation_id
    assert brc_repo.campaign.metadata_json["runtime_started_by_preflight_id"] == preflight.preflight_id
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert brc_repo.campaign.metadata_json["auto_execution_enabled"] is False
    assert brc_repo.campaign.metadata_json["auto_within_budget_enabled"] is False
    assert brc_repo.campaign.metadata_json["live_ready"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_started"]) == 1


@pytest.mark.asyncio
async def test_start_runtime_from_handoff_double_confirm_is_idempotent_on_same_operation():
    admission, engine, binding, service, brc_repo, _ = await _phase11_runtime_handoff_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="start_runtime_from_admission_handoff",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_START_ADMISSION_RUNTIME",
            idempotency_key=preflight.idempotency_key,
        )
        second = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_START_ADMISSION_RUNTIME",
            idempotency_key=preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second.status == "executed"
    assert second.result_summary == first.result_summary
    assert brc_repo.campaign.metadata_json["runtime_started"] is True
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert brc_repo.campaign.metadata_json["auto_execution_enabled"] is False
    assert brc_repo.campaign.metadata_json["auto_within_budget_enabled"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_started"]) == 1


@pytest.mark.asyncio
async def test_start_runtime_from_handoff_new_operation_noops_when_already_started_strategy_inactive():
    admission, engine, binding, service, brc_repo, _ = await _phase11_runtime_handoff_ready_context()
    try:
        first_preflight = await service.preflight(
            operation_type="start_runtime_from_admission_handoff",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=first_preflight.operation_id,
            preflight_id=first_preflight.preflight_id,
            confirmation_phrase="CONFIRM_START_ADMISSION_RUNTIME",
            idempotency_key=first_preflight.idempotency_key,
        )
        second_preflight = await service.preflight(
            operation_type="start_runtime_from_admission_handoff",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        second = await service.confirm(
            operation_id=second_preflight.operation_id,
            preflight_id=second_preflight.preflight_id,
            confirmation_phrase="CONFIRM_START_ADMISSION_RUNTIME",
            idempotency_key=second_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second_preflight.preflight_result in {"allow", "warn"}
    assert second_preflight.after["idempotent_start"] is True
    assert second.status == "noop"
    assert second.result_summary["idempotent"] is True
    assert second.result_summary["runtime_started"] is True
    assert second.result_summary["strategy_active"] is False
    assert second.result_summary["trial_started"] is False
    assert second.result_summary["orders_placed"] is False
    assert second.result_summary["auto_within_budget_enabled"] is False
    assert second.result_summary["auto_execution_enabled"] is False
    assert second.result_summary["order_created"] is False
    assert second.result_summary["execution_intent_created"] is False
    assert second.result_summary["live_ready"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_runtime_started"]) == 1


@pytest.mark.asyncio
async def test_strategy_activation_readiness_preflight_blocks_runtime_started_false():
    admission, engine, binding, service, brc_repo, _ = await _phase11_runtime_handoff_ready_context()
    try:
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_strategy_activation_readiness=_strategy_activation_readiness(admission, service._brc),
            admission_strategy_activation_preparer_factory=_strategy_activation_preparer(admission),
        )
        preflight = await service.preflight(
            operation_type="prepare_strategy_activation_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_started is not true" in preflight.risk_summary["blockers"]
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False


@pytest.mark.asyncio
async def test_strategy_activation_readiness_preflight_blocks_wrong_runtime_status():
    admission, engine, binding, service, brc_repo, _ = await _phase13_runtime_started_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "runtime_status": "runtime_handoff_ready_not_started"}}
        )
        preflight = await service.preflight(
            operation_type="prepare_strategy_activation_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_status is not runtime_started_strategy_inactive" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("strategy_active", "campaign metadata strategy_active is not false"),
        ("trial_started", "campaign metadata trial_started is not false"),
        ("orders_placed", "campaign metadata orders_placed is not false"),
        ("auto_execution_enabled", "campaign metadata auto_execution_enabled is not false"),
        ("auto_within_budget_enabled", "campaign metadata auto_within_budget_enabled is not false"),
    ],
)
async def test_strategy_activation_readiness_preflight_blocks_active_auto_or_order_flags(flag, message):
    admission, engine, binding, service, brc_repo, _ = await _phase13_runtime_started_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, flag: True}}
        )
        preflight = await service.preflight(
            operation_type="prepare_strategy_activation_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert message in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_strategy_activation_readiness_preflight_allows_valid_runtime_started_campaign():
    admission, engine, binding, service, brc_repo, _ = await _phase13_runtime_started_context()
    try:
        preflight = await service.preflight(
            operation_type="prepare_strategy_activation_from_admission_runtime",
            requested_by="owner",
            input_params={"campaign_id": brc_repo.campaign.campaign_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result in {"allow", "warn"}
    assert preflight.after["strategy_activation_readiness_only"] is True
    assert preflight.after["actual_strategy_activation_available"] is False
    assert preflight.strategy_activation_summary["strategy_activation_readiness_would_be_prepared"] is True
    assert preflight.strategy_activation_summary["strategy_will_activate"] is False
    assert preflight.strategy_activation_summary["signal_loop_will_start"] is False
    assert preflight.strategy_activation_summary["auto_execution_will_be_enabled"] is False
    assert preflight.strategy_activation_summary["execution_intent_will_be_created"] is False
    assert preflight.strategy_activation_summary["orders_will_be_placed"] is False
    assert (
        preflight.strategy_activation_summary["next_phase_must_explicitly_activate_strategy"]
        is True
    )
    assert brc_repo.campaign.metadata_json["runtime_started"] is True
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False


@pytest.mark.asyncio
async def test_strategy_activation_readiness_confirm_writes_metadata_without_strategy_trial_or_orders():
    admission, engine, binding, service, brc_repo, market = await _phase13_runtime_started_context()
    try:
        preflight = await service.preflight(
            operation_type="prepare_strategy_activation_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_STRATEGY_ACTIVATION",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["strategy_activation_ready"] is True
    assert result.result_summary["runtime_status"] == "strategy_activation_ready_not_active"
    assert result.result_summary["runtime_started"] is True
    assert result.result_summary["strategy_active"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["signal_loop_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["auto_execution_enabled"] is False
    assert result.result_summary["trade_intent_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["orders_placed"] is False
    assert result.result_summary["live_ready"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.status == BrcCampaignStatus.OBSERVE
    assert brc_repo.campaign.attempt_count == 0
    assert brc_repo.campaign.metadata_json["strategy_activation_ready"] is True
    assert brc_repo.campaign.metadata_json["runtime_status"] == "strategy_activation_ready_not_active"
    assert brc_repo.campaign.metadata_json["strategy_activation_ready_by_operation_id"] == preflight.operation_id
    assert brc_repo.campaign.metadata_json["strategy_activation_ready_by_preflight_id"] == preflight.preflight_id
    assert brc_repo.campaign.metadata_json["runtime_started"] is True
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["signal_loop_started"] is False
    assert brc_repo.campaign.metadata_json["auto_execution_enabled"] is False
    assert brc_repo.campaign.metadata_json["auto_within_budget_enabled"] is False
    assert brc_repo.campaign.metadata_json["execution_intent_created"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert brc_repo.campaign.metadata_json["live_ready"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert not [event for event in brc_repo.events if "order" in event["event_type"] or "execution_intent" in event["event_type"]]
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_strategy_activation_ready"]) == 1


@pytest.mark.asyncio
async def test_strategy_activation_readiness_double_confirm_is_idempotent():
    admission, engine, binding, service, brc_repo, _ = await _phase13_runtime_started_context()
    try:
        preflight = await service.preflight(
            operation_type="prepare_strategy_activation_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_STRATEGY_ACTIVATION",
            idempotency_key=preflight.idempotency_key,
        )
        second = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_STRATEGY_ACTIVATION",
            idempotency_key=preflight.idempotency_key,
        )
        noop_preflight = await service.preflight(
            operation_type="prepare_strategy_activation_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        noop_result = await service.confirm(
            operation_id=noop_preflight.operation_id,
            preflight_id=noop_preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_STRATEGY_ACTIVATION",
            idempotency_key=noop_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second.status == "executed"
    assert second.result_summary == first.result_summary
    assert noop_preflight.preflight_result in {"allow", "warn"}
    assert noop_preflight.after["idempotent_prepare"] is True
    assert noop_result.status == "noop"
    assert noop_result.result_summary["idempotent"] is True
    assert noop_result.result_summary["strategy_activation_ready"] is True
    assert noop_result.result_summary["strategy_active"] is False
    assert noop_result.result_summary["trial_started"] is False
    assert noop_result.result_summary["auto_execution_enabled"] is False
    assert noop_result.result_summary["auto_within_budget_enabled"] is False
    assert noop_result.result_summary["execution_intent_created"] is False
    assert noop_result.result_summary["order_created"] is False
    assert noop_result.result_summary["orders_placed"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_strategy_activation_ready"]) == 1


@pytest.mark.asyncio
async def test_strategy_state_activation_preflight_blocks_strategy_activation_ready_false():
    admission, engine, binding, service, brc_repo, _ = await _phase13_runtime_started_context()
    try:
        service, _, brc_repo, _ = await _operation_service(
            create_campaign=False,
            brc_service=service._brc,
            brc_repo_existing=brc_repo,
            admission_strategy_state_activation_readiness=_strategy_state_activation_readiness(admission, service._brc),
            admission_strategy_state_activator_factory=_strategy_state_activator(admission),
        )
        preflight = await service.preflight(
            operation_type="activate_strategy_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata strategy_activation_ready is not true" in preflight.risk_summary["blockers"]
    assert brc_repo.campaign.metadata_json["strategy_active"] is False


@pytest.mark.asyncio
async def test_strategy_state_activation_preflight_blocks_wrong_runtime_status():
    admission, engine, binding, service, brc_repo, _ = await _phase14_strategy_activation_ready_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "runtime_status": "runtime_started_strategy_inactive"}}
        )
        preflight = await service.preflight(
            operation_type="activate_strategy_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_status is not strategy_activation_ready_not_active" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("strategy_execution_enabled", "campaign metadata strategy_execution_enabled is true"),
        ("signal_loop_enabled", "campaign metadata signal_loop_enabled is true"),
        ("signal_loop_started", "campaign metadata signal_loop_started is true"),
        ("trade_intent_created", "campaign metadata trade_intent_created is true"),
        ("execution_intent_created", "campaign metadata execution_intent_created is true"),
        ("order_created", "campaign metadata order_created is true"),
    ],
)
async def test_strategy_state_activation_preflight_blocks_already_order_capable_state(flag, message):
    admission, engine, binding, service, brc_repo, _ = await _phase14_strategy_activation_ready_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, flag: True}}
        )
        preflight = await service.preflight(
            operation_type="activate_strategy_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert message in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_strategy_state_activation_preflight_blocks_auto_execution_enabled_true():
    admission, engine, binding, service, brc_repo, _ = await _phase14_strategy_activation_ready_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "auto_execution_enabled": True}}
        )
        preflight = await service.preflight(
            operation_type="activate_strategy_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata auto_execution_enabled is not false" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_strategy_state_activation_preflight_allows_valid_strategy_activation_ready_campaign():
    admission, engine, binding, service, brc_repo, _ = await _phase14_strategy_activation_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="activate_strategy_from_admission_runtime",
            requested_by="owner",
            input_params={"campaign_id": brc_repo.campaign.campaign_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result in {"allow", "warn"}
    assert preflight.after["strategy_state_activation_only"] is True
    assert preflight.after["order_capable_strategy_available"] is False
    assert preflight.strategy_activation_summary["strategy_metadata_activation_would_occur"] is True
    assert preflight.strategy_activation_summary["strategy_active_after_confirm"] is True
    assert preflight.strategy_activation_summary["strategy_runner_will_start"] is False
    assert preflight.strategy_activation_summary["signal_loop_will_start"] is False
    assert preflight.strategy_activation_summary["auto_execution_will_be_enabled"] is False
    assert preflight.strategy_activation_summary["trade_intent_will_be_created"] is False
    assert preflight.strategy_activation_summary["execution_intent_will_be_created"] is False
    assert preflight.strategy_activation_summary["orders_will_be_placed"] is False
    assert (
        preflight.strategy_activation_summary["next_phase_must_explicitly_enable_signal_loop_or_observe_gate"]
        is True
    )
    assert brc_repo.campaign.metadata_json["strategy_activation_ready"] is True
    assert brc_repo.campaign.metadata_json["strategy_active"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False


@pytest.mark.asyncio
async def test_strategy_state_activation_confirm_writes_no_execution_metadata():
    admission, engine, binding, service, brc_repo, market = await _phase14_strategy_activation_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="activate_strategy_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_ACTIVATE_STRATEGY_NO_EXECUTION",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["strategy_state"] == "strategy_active_no_execution"
    assert result.result_summary["strategy_activation_state"] == "active_no_execution"
    assert result.result_summary["runtime_status"] == "strategy_active_no_execution"
    assert result.result_summary["runtime_started"] is True
    assert result.result_summary["strategy_active"] is True
    assert result.result_summary["strategy_execution_enabled"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["signal_loop_enabled"] is False
    assert result.result_summary["signal_loop_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["auto_execution_enabled"] is False
    assert result.result_summary["trade_intent_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["orders_placed"] is False
    assert result.result_summary["live_ready"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.status == BrcCampaignStatus.OBSERVE
    assert brc_repo.campaign.attempt_count == 0
    assert brc_repo.campaign.metadata_json["strategy_state"] == "strategy_active_no_execution"
    assert brc_repo.campaign.metadata_json["strategy_activation_state"] == "active_no_execution"
    assert brc_repo.campaign.metadata_json["runtime_status"] == "strategy_active_no_execution"
    assert brc_repo.campaign.metadata_json["strategy_active"] is True
    assert brc_repo.campaign.metadata_json["strategy_execution_enabled"] is False
    assert brc_repo.campaign.metadata_json["signal_loop_enabled"] is False
    assert brc_repo.campaign.metadata_json["signal_loop_started"] is False
    assert brc_repo.campaign.metadata_json["trial_started"] is False
    assert brc_repo.campaign.metadata_json["auto_execution_enabled"] is False
    assert brc_repo.campaign.metadata_json["auto_within_budget_enabled"] is False
    assert brc_repo.campaign.metadata_json["trade_intent_created"] is False
    assert brc_repo.campaign.metadata_json["execution_intent_created"] is False
    assert brc_repo.campaign.metadata_json["order_created"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert brc_repo.campaign.metadata_json["live_ready"] is False
    assert brc_repo.campaign.metadata_json["strategy_activated_by_operation_id"] == preflight.operation_id
    assert brc_repo.campaign.metadata_json["strategy_activated_by_preflight_id"] == preflight.preflight_id
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert not [event for event in brc_repo.events if "order" in event["event_type"] or "execution_intent" in event["event_type"]]
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_strategy_activated_no_execution"]) == 1


@pytest.mark.asyncio
async def test_strategy_state_activation_double_confirm_is_idempotent():
    admission, engine, binding, service, brc_repo, _ = await _phase14_strategy_activation_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="activate_strategy_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_ACTIVATE_STRATEGY_NO_EXECUTION",
            idempotency_key=preflight.idempotency_key,
        )
        second = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_ACTIVATE_STRATEGY_NO_EXECUTION",
            idempotency_key=preflight.idempotency_key,
        )
        noop_preflight = await service.preflight(
            operation_type="activate_strategy_from_admission_runtime",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        noop_result = await service.confirm(
            operation_id=noop_preflight.operation_id,
            preflight_id=noop_preflight.preflight_id,
            confirmation_phrase="CONFIRM_ACTIVATE_STRATEGY_NO_EXECUTION",
            idempotency_key=noop_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second.status == "executed"
    assert second.result_summary == first.result_summary
    assert noop_preflight.preflight_result in {"allow", "warn"}
    assert noop_preflight.after["idempotent_activate"] is True
    assert noop_result.status == "noop"
    assert noop_result.result_summary["idempotent"] is True
    assert noop_result.result_summary["strategy_state"] == "strategy_active_no_execution"
    assert noop_result.result_summary["strategy_active"] is True
    assert noop_result.result_summary["strategy_execution_enabled"] is False
    assert noop_result.result_summary["signal_loop_enabled"] is False
    assert noop_result.result_summary["signal_loop_started"] is False
    assert noop_result.result_summary["trial_started"] is False
    assert noop_result.result_summary["auto_execution_enabled"] is False
    assert noop_result.result_summary["auto_within_budget_enabled"] is False
    assert noop_result.result_summary["trade_intent_created"] is False
    assert noop_result.result_summary["execution_intent_created"] is False
    assert noop_result.result_summary["order_created"] is False
    assert noop_result.result_summary["orders_placed"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_strategy_activated_no_execution"]) == 1


@pytest.mark.asyncio
async def test_signal_loop_readiness_preflight_blocks_wrong_runtime_status():
    admission, engine, binding, service, brc_repo, _ = await _phase15_strategy_active_no_execution_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "runtime_status": "strategy_activation_ready_not_active"}}
        )
        preflight = await service.preflight(
            operation_type="prepare_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_status is not strategy_active_no_execution" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("signal_loop_started", "campaign metadata signal_loop_started is not false"),
        ("signal_loop_enabled", "campaign metadata signal_loop_enabled is not false"),
        ("trial_started", "campaign metadata trial_started is not false"),
        ("orders_placed", "campaign metadata orders_placed is not false"),
        ("execution_intent_created", "campaign metadata execution_intent_created is not false"),
    ],
)
async def test_signal_loop_readiness_preflight_blocks_unsafe_flags(flag, message):
    admission, engine, binding, service, brc_repo, _ = await _phase15_strategy_active_no_execution_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, flag: True}}
        )
        preflight = await service.preflight(
            operation_type="prepare_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert message in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_signal_loop_readiness_preflight_allows_valid_strategy_active_no_execution_campaign():
    admission, engine, binding, service, brc_repo, _ = await _phase15_strategy_active_no_execution_context()
    try:
        preflight = await service.preflight(
            operation_type="prepare_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"campaign_id": brc_repo.campaign.campaign_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result in {"allow", "warn"}
    assert preflight.after["signal_loop_readiness_only"] is True
    assert preflight.after["actual_signal_loop_available"] is False
    assert preflight.after["actual_signal_generation_available"] is False
    assert preflight.signal_loop_summary["signal_loop_readiness_would_be_prepared"] is True
    assert preflight.signal_loop_summary["signal_loop_will_start"] is False
    assert preflight.signal_loop_summary["signal_will_be_generated"] is False
    assert preflight.signal_loop_summary["trade_intent_will_be_created"] is False
    assert preflight.signal_loop_summary["execution_intent_will_be_created"] is False
    assert preflight.signal_loop_summary["orders_will_be_placed"] is False
    assert (
        preflight.signal_loop_summary["next_phase_must_explicitly_start_observe_gate_or_signal_loop"]
        is True
    )
    assert brc_repo.campaign.metadata_json["strategy_state"] == "strategy_active_no_execution"
    assert brc_repo.campaign.metadata_json["signal_loop_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False


@pytest.mark.asyncio
async def test_signal_loop_readiness_confirm_writes_metadata_without_signal_or_intents_or_orders():
    admission, engine, binding, service, brc_repo, market = await _phase15_strategy_active_no_execution_context()
    try:
        preflight = await service.preflight(
            operation_type="prepare_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_SIGNAL_LOOP",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["signal_loop_ready"] is True
    assert result.result_summary["runtime_status"] == "signal_loop_ready_not_started"
    assert result.result_summary["runtime_started"] is True
    assert result.result_summary["strategy_active"] is True
    assert result.result_summary["strategy_execution_enabled"] is False
    assert result.result_summary["signal_loop_enabled"] is False
    assert result.result_summary["signal_loop_started"] is False
    assert result.result_summary["signal_generated"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["auto_execution_enabled"] is False
    assert result.result_summary["trade_intent_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["orders_placed"] is False
    assert result.result_summary["live_ready"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.status == BrcCampaignStatus.OBSERVE
    assert brc_repo.campaign.metadata_json["signal_loop_ready"] is True
    assert brc_repo.campaign.metadata_json["runtime_status"] == "signal_loop_ready_not_started"
    assert brc_repo.campaign.metadata_json["signal_loop_ready_by_operation_id"] == preflight.operation_id
    assert brc_repo.campaign.metadata_json["signal_loop_ready_by_preflight_id"] == preflight.preflight_id
    assert brc_repo.campaign.metadata_json["signal_loop_enabled"] is False
    assert brc_repo.campaign.metadata_json["signal_loop_started"] is False
    assert brc_repo.campaign.metadata_json["signal_generated"] is False
    assert brc_repo.campaign.metadata_json["trade_intent_created"] is False
    assert brc_repo.campaign.metadata_json["execution_intent_created"] is False
    assert brc_repo.campaign.metadata_json["order_created"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert not [event for event in brc_repo.events if "order" in event["event_type"] or "execution_intent" in event["event_type"]]
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_signal_loop_ready"]) == 1


@pytest.mark.asyncio
async def test_signal_loop_readiness_double_confirm_is_idempotent():
    admission, engine, binding, service, brc_repo, _ = await _phase15_strategy_active_no_execution_context()
    try:
        preflight = await service.preflight(
            operation_type="prepare_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_SIGNAL_LOOP",
            idempotency_key=preflight.idempotency_key,
        )
        second = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_SIGNAL_LOOP",
            idempotency_key=preflight.idempotency_key,
        )
        noop_preflight = await service.preflight(
            operation_type="prepare_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        noop_result = await service.confirm(
            operation_id=noop_preflight.operation_id,
            preflight_id=noop_preflight.preflight_id,
            confirmation_phrase="CONFIRM_PREPARE_SIGNAL_LOOP",
            idempotency_key=noop_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second.status == "executed"
    assert second.result_summary == first.result_summary
    assert noop_preflight.preflight_result in {"allow", "warn"}
    assert noop_preflight.after["idempotent_prepare"] is True
    assert noop_result.status == "noop"
    assert noop_result.result_summary["idempotent"] is True
    assert noop_result.result_summary["signal_loop_ready"] is True
    assert noop_result.result_summary["signal_loop_enabled"] is False
    assert noop_result.result_summary["signal_loop_started"] is False
    assert noop_result.result_summary["signal_generated"] is False
    assert noop_result.result_summary["trade_intent_created"] is False
    assert noop_result.result_summary["execution_intent_created"] is False
    assert noop_result.result_summary["order_created"] is False
    assert noop_result.result_summary["orders_placed"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_signal_loop_ready"]) == 1


@pytest.mark.asyncio
async def test_signal_loop_start_preflight_blocks_wrong_runtime_status():
    admission, engine, binding, service, brc_repo, _ = await _phase16_signal_loop_ready_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "runtime_status": "strategy_active_no_execution"}}
        )
        preflight = await service.preflight(
            operation_type="start_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_status is not signal_loop_ready_not_started" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_signal_loop_start_preflight_blocks_signal_loop_ready_false():
    admission, engine, binding, service, brc_repo, _ = await _phase16_signal_loop_ready_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "signal_loop_ready": False}}
        )
        preflight = await service.preflight(
            operation_type="start_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata signal_loop_ready is not true" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("signal_loop_started", "campaign metadata signal_loop_started is not false"),
        ("signal_generated", "campaign metadata signal_generated is not false"),
        ("trade_intent_created", "campaign metadata trade_intent_created is not false"),
        ("execution_intent_created", "campaign metadata execution_intent_created is not false"),
        ("orders_placed", "campaign metadata orders_placed is not false"),
        ("auto_execution_enabled", "campaign metadata auto_execution_enabled is not false"),
    ],
)
async def test_signal_loop_start_preflight_blocks_unsafe_flags(flag, message):
    admission, engine, binding, service, brc_repo, _ = await _phase16_signal_loop_ready_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, flag: True}}
        )
        preflight = await service.preflight(
            operation_type="start_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert message in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_signal_loop_start_preflight_allows_valid_signal_loop_ready_campaign():
    admission, engine, binding, service, brc_repo, _ = await _phase16_signal_loop_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="start_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"campaign_id": brc_repo.campaign.campaign_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result in {"allow", "warn"}
    assert preflight.after["signal_loop_start_state_only"] is True
    assert preflight.after["actual_signal_generation_available"] is False
    assert preflight.after["actual_trade_intent_available"] is False
    assert preflight.signal_loop_summary["signal_loop_state_would_start"] is True
    assert preflight.signal_loop_summary["signal_loop_enabled_scope"] == "non_trading_loop_state"
    assert preflight.signal_loop_summary["signal_will_be_generated"] is False
    assert preflight.signal_loop_summary["trade_intent_will_be_created"] is False
    assert preflight.signal_loop_summary["execution_intent_will_be_created"] is False
    assert preflight.signal_loop_summary["orders_will_be_placed"] is False
    assert (
        preflight.signal_loop_summary["next_phase_must_explicitly_generate_or_evaluate_signals"]
        is True
    )
    assert brc_repo.campaign.metadata_json["runtime_status"] == "signal_loop_ready_not_started"
    assert brc_repo.campaign.metadata_json["signal_loop_started"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False


@pytest.mark.asyncio
async def test_signal_loop_start_confirm_writes_started_no_signal_metadata():
    admission, engine, binding, service, brc_repo, market = await _phase16_signal_loop_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="start_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_START_SIGNAL_LOOP_NO_SIGNAL",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["runtime_status"] == "signal_loop_started_no_signal"
    assert result.result_summary["runtime_started"] is True
    assert result.result_summary["strategy_active"] is True
    assert result.result_summary["strategy_execution_enabled"] is False
    assert result.result_summary["signal_loop_ready"] is True
    assert result.result_summary["signal_loop_enabled"] is True
    assert result.result_summary["signal_loop_enabled_scope"] == "non_trading_loop_state"
    assert result.result_summary["signal_loop_started"] is True
    assert result.result_summary["signal_generated"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["auto_execution_enabled"] is False
    assert result.result_summary["trade_intent_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["orders_placed"] is False
    assert result.result_summary["live_ready"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.metadata_json["runtime_status"] == "signal_loop_started_no_signal"
    assert brc_repo.campaign.metadata_json["signal_loop_started_by_operation_id"] == preflight.operation_id
    assert brc_repo.campaign.metadata_json["signal_loop_started_by_preflight_id"] == preflight.preflight_id
    assert brc_repo.campaign.metadata_json["signal_loop_enabled"] is True
    assert brc_repo.campaign.metadata_json["signal_loop_enabled_scope"] == "non_trading_loop_state"
    assert brc_repo.campaign.metadata_json["signal_loop_started"] is True
    assert brc_repo.campaign.metadata_json["signal_generated"] is False
    assert brc_repo.campaign.metadata_json["trade_intent_created"] is False
    assert brc_repo.campaign.metadata_json["execution_intent_created"] is False
    assert brc_repo.campaign.metadata_json["order_created"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert not [event for event in brc_repo.events if "order" in event["event_type"] or "execution_intent" in event["event_type"]]
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_signal_loop_started_no_signal"]) == 1


@pytest.mark.asyncio
async def test_signal_loop_start_double_confirm_is_idempotent():
    admission, engine, binding, service, brc_repo, _ = await _phase16_signal_loop_ready_context()
    try:
        preflight = await service.preflight(
            operation_type="start_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_START_SIGNAL_LOOP_NO_SIGNAL",
            idempotency_key=preflight.idempotency_key,
        )
        second = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_START_SIGNAL_LOOP_NO_SIGNAL",
            idempotency_key=preflight.idempotency_key,
        )
        noop_preflight = await service.preflight(
            operation_type="start_signal_loop_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        noop_result = await service.confirm(
            operation_id=noop_preflight.operation_id,
            preflight_id=noop_preflight.preflight_id,
            confirmation_phrase="CONFIRM_START_SIGNAL_LOOP_NO_SIGNAL",
            idempotency_key=noop_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second.status == "executed"
    assert second.result_summary == first.result_summary
    assert noop_preflight.preflight_result in {"allow", "warn"}
    assert noop_preflight.after["idempotent_start"] is True
    assert noop_result.status == "noop"
    assert noop_result.result_summary["idempotent"] is True
    assert noop_result.result_summary["runtime_status"] == "signal_loop_started_no_signal"
    assert noop_result.result_summary["signal_loop_enabled"] is True
    assert noop_result.result_summary["signal_loop_enabled_scope"] == "non_trading_loop_state"
    assert noop_result.result_summary["signal_loop_started"] is True
    assert noop_result.result_summary["signal_generated"] is False
    assert noop_result.result_summary["trade_intent_created"] is False
    assert noop_result.result_summary["execution_intent_created"] is False
    assert noop_result.result_summary["order_created"] is False
    assert noop_result.result_summary["orders_placed"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_signal_loop_started_no_signal"]) == 1


@pytest.mark.asyncio
async def test_signal_evaluation_preflight_blocks_wrong_runtime_status():
    admission, engine, binding, service, brc_repo, _ = await _phase17_signal_loop_started_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "runtime_status": "signal_loop_ready_not_started"}}
        )
        preflight = await service.preflight(
            operation_type="evaluate_signal_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata runtime_status is not signal_loop_started_no_signal" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_signal_evaluation_preflight_blocks_signal_loop_started_false():
    admission, engine, binding, service, brc_repo, _ = await _phase17_signal_loop_started_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, "signal_loop_started": False}}
        )
        preflight = await service.preflight(
            operation_type="evaluate_signal_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert "campaign metadata signal_loop_started is not true" in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("trade_intent_created", "campaign metadata trade_intent_created is not false"),
        ("execution_intent_created", "campaign metadata execution_intent_created is not false"),
        ("order_created", "campaign metadata order_created is not false"),
        ("orders_placed", "campaign metadata orders_placed is not false"),
        ("auto_execution_enabled", "campaign metadata auto_execution_enabled is not false"),
    ],
)
async def test_signal_evaluation_preflight_blocks_unsafe_flags(flag, message):
    admission, engine, binding, service, brc_repo, _ = await _phase17_signal_loop_started_context()
    try:
        brc_repo.campaign = brc_repo.campaign.model_copy(
            update={"metadata_json": {**brc_repo.campaign.metadata_json, flag: True}}
        )
        preflight = await service.preflight(
            operation_type="evaluate_signal_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert message in preflight.risk_summary["blockers"]


@pytest.mark.asyncio
async def test_signal_evaluation_preflight_allows_valid_signal_loop_started_campaign():
    admission, engine, binding, service, brc_repo, _ = await _phase17_signal_loop_started_context()
    try:
        preflight = await service.preflight(
            operation_type="evaluate_signal_from_admission_strategy",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "signal_snapshot": {"symbol": "ETH/USDT:USDT", "bias": "observe"},
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result in {"allow", "warn"}
    assert preflight.after["signal_evaluation_metadata_only"] is True
    assert preflight.after["actual_trade_intent_available"] is False
    assert preflight.signal_evaluation_summary["signal_evaluation_would_be_recorded"] is True
    assert preflight.signal_evaluation_summary["signal_is_trade_intent"] is False
    assert preflight.signal_evaluation_summary["trade_intent_will_be_created"] is False
    assert preflight.signal_evaluation_summary["execution_intent_will_be_created"] is False
    assert preflight.signal_evaluation_summary["orders_will_be_placed"] is False
    assert (
        preflight.signal_evaluation_summary["next_phase_must_explicitly_convert_signal_to_trial_trade_intent"]
        is True
    )
    assert brc_repo.campaign.metadata_json["runtime_status"] == "signal_loop_started_no_signal"
    assert brc_repo.campaign.metadata_json["trade_intent_created"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False


@pytest.mark.asyncio
async def test_signal_evaluation_confirm_writes_no_intent_metadata():
    admission, engine, binding, service, brc_repo, market = await _phase17_signal_loop_started_context()
    try:
        preflight = await service.preflight(
            operation_type="evaluate_signal_from_admission_strategy",
            requested_by="owner",
            input_params={
                "admission_binding_id": binding.binding_id,
                "signal_snapshot": {"symbol": "ETH/USDT:USDT", "bias": "observe"},
                "signal_evaluation_input": {"source": "unit"},
            },
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_EVALUATE_SIGNAL_NO_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        updated_binding = await admission.get_admission_trial_binding(binding.binding_id)
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["runtime_status"] == "signal_evaluated_no_intent"
    assert result.result_summary["signal_evaluated"] is True
    assert result.result_summary["signal_generated"] is True
    assert result.result_summary["signal_is_trade_intent"] is False
    assert result.result_summary["trade_intent_created"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["orders_placed"] is False
    assert result.result_summary["trial_started"] is False
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["auto_execution_enabled"] is False
    assert result.result_summary["live_ready"] is False
    assert market["runtime_state"]["current_runtime_state"] == "observe"
    assert brc_repo.campaign.metadata_json["runtime_status"] == "signal_evaluated_no_intent"
    assert brc_repo.campaign.metadata_json["signal_evaluated_by_operation_id"] == preflight.operation_id
    assert brc_repo.campaign.metadata_json["signal_evaluated_by_preflight_id"] == preflight.preflight_id
    assert brc_repo.campaign.metadata_json["signal_evaluated"] is True
    assert brc_repo.campaign.metadata_json["signal_generated"] is True
    assert brc_repo.campaign.metadata_json["signal_snapshot_json"]["symbol"] == "ETH/USDT:USDT"
    assert brc_repo.campaign.metadata_json["signal_evaluation_summary_json"]["signal_is_trade_intent"] is False
    assert brc_repo.campaign.metadata_json["trade_intent_created"] is False
    assert brc_repo.campaign.metadata_json["execution_intent_created"] is False
    assert brc_repo.campaign.metadata_json["order_created"] is False
    assert brc_repo.campaign.metadata_json["orders_placed"] is False
    assert updated_binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED
    assert not [event for event in brc_repo.events if "order" in event["event_type"] or "execution_intent" in event["event_type"]]
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_signal_evaluated_no_intent"]) == 1


@pytest.mark.asyncio
async def test_signal_evaluation_double_confirm_is_idempotent():
    admission, engine, binding, service, brc_repo, _ = await _phase17_signal_loop_started_context()
    try:
        preflight = await service.preflight(
            operation_type="evaluate_signal_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        first = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_EVALUATE_SIGNAL_NO_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        second = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_EVALUATE_SIGNAL_NO_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        noop_preflight = await service.preflight(
            operation_type="evaluate_signal_from_admission_strategy",
            requested_by="owner",
            input_params={"admission_binding_id": binding.binding_id},
        )
        noop_result = await service.confirm(
            operation_id=noop_preflight.operation_id,
            preflight_id=noop_preflight.preflight_id,
            confirmation_phrase="CONFIRM_EVALUATE_SIGNAL_NO_INTENT",
            idempotency_key=noop_preflight.idempotency_key,
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second.status == "executed"
    assert second.result_summary == first.result_summary
    assert noop_preflight.preflight_result in {"allow", "warn"}
    assert noop_preflight.after["idempotent_evaluation"] is True
    assert noop_result.status == "noop"
    assert noop_result.result_summary["idempotent"] is True
    assert noop_result.result_summary["runtime_status"] == "signal_evaluated_no_intent"
    assert noop_result.result_summary["signal_evaluated"] is True
    assert noop_result.result_summary["signal_is_trade_intent"] is False
    assert noop_result.result_summary["trade_intent_created"] is False
    assert noop_result.result_summary["execution_intent_created"] is False
    assert noop_result.result_summary["order_created"] is False
    assert noop_result.result_summary["orders_placed"] is False
    assert len([event for event in brc_repo.events if event["event_type"] == "admission_signal_evaluated_no_intent"]) == 1


@pytest.mark.asyncio
async def test_record_trial_trade_intent_capability_is_evidence_only():
    service, _, _, _ = await _operation_service()
    capabilities = {item.operation_type: item for item in service.capabilities()}

    capability = capabilities["record_trial_trade_intent_from_signal_evaluation"]
    assert capability.status == "operation_preflight_available"
    assert capability.executable_through_operation is True
    assert capability.confirmation_required is True
    assert "does not create execution intents" in capability.current_reason


@pytest.mark.asyncio
async def test_record_trial_trade_intent_preflight_blocks_when_permission_below_intent_recording():
    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context(
        execution_permission_max=ExecutionPermission.SIGNAL_ONLY,
    )
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    assert preflight.after["execution_permission_resolution"]["final_permission"] == "signal_only"
    assert "below requested intent_recording" in "; ".join(preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_record_trial_trade_intent_preflight_allows_when_permission_allows():
    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context()
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result in {"allow", "warn"}
    assert preflight.after["trial_trade_intent_recording_only"] is True
    assert preflight.after["execution_permission_resolution"]["final_permission"] == "intent_recording"
    _assert_trial_trade_intent_projection(preflight.after["enforcement"], expected="recorded")
    _assert_trial_trade_intent_projection(preflight.trade_intent_summary, expected="recorded")
    assert preflight.trade_intent_summary["intent_would_be_recorded"] is True
    assert preflight.trade_intent_summary["execution_intent_created"] is False
    assert preflight.trade_intent_summary["order_created"] is False


@pytest.mark.asyncio
async def test_record_trial_trade_intent_runtime_safety_reader_requires_explicit_runtime_id():
    calls: list[dict[str, Any]] = []

    async def _runtime_safety_readiness(input_params):
        calls.append(dict(input_params))
        return {
            "runtime_instance_id": "rt-unused",
            "status": "blocked",
            "blockers": ["should_not_be_read_without_runtime_id"],
            "missing_boundary_facts": ["should_not_be_read_without_runtime_id"],
            "not_execution_authority": True,
            "execution_intent_created": False,
            "runtime_state_mutated": False,
            "order_created": False,
            "exchange_called": False,
        }

    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context(
        runtime_safety_readiness=_runtime_safety_readiness,
    )
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
    finally:
        await engine.dispose()

    assert calls == []
    assert preflight.preflight_result in {"allow", "warn"}
    assert "runtime_safety_readiness" not in preflight.runtime_summary
    assert preflight.after["execution_permission_resolution"]["final_permission"] == "intent_recording"


@pytest.mark.asyncio
async def test_record_trial_trade_intent_preflight_blocks_explicit_runtime_id_without_reader():
    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context()
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "runtime_instance_id": "rt-missing-reader",
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "block"
    readiness = preflight.runtime_summary["runtime_safety_readiness"]
    assert readiness["runtime_instance_id"] == "rt-missing-reader"
    assert readiness["status"] == "blocked"
    assert readiness["blockers"] == ["runtime_safety_readiness_reader_unavailable"]
    assert preflight.after["execution_permission_resolution"]["runtime_safety_permission"] == "signal_only"
    assert "runtime_safety_readiness_reader_unavailable" in "; ".join(preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_record_trial_trade_intent_preflight_blocks_on_runtime_safety_reader_blocker():
    calls: list[dict[str, Any]] = []

    async def _runtime_safety_readiness(input_params):
        calls.append(dict(input_params))
        return {
            "runtime_instance_id": "rt-blocked",
            "status": "blocked",
            "blockers": ["max_loss_budget_present"],
            "missing_boundary_facts": ["max_loss_budget_present"],
            "not_execution_authority": True,
            "execution_intent_created": False,
            "runtime_state_mutated": False,
            "order_created": False,
            "exchange_called": False,
        }

    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context(
        runtime_safety_readiness=_runtime_safety_readiness,
    )
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "runtime_instance_id": "rt-blocked",
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
    finally:
        await engine.dispose()

    assert [call["runtime_instance_id"] for call in calls] == ["rt-blocked"]
    assert preflight.preflight_result == "block"
    assert preflight.runtime_summary["runtime_safety_readiness"]["blockers"] == ["max_loss_budget_present"]
    assert preflight.after["execution_permission_resolution"]["runtime_safety_permission"] == "signal_only"
    assert "runtime safety readiness blocks intent recording" in "; ".join(preflight.risk_summary["blockers"])
    assert "max_loss_budget_present" in "; ".join(preflight.risk_summary["blockers"])


@pytest.mark.asyncio
async def test_record_trial_trade_intent_confirm_rechecks_runtime_safety_reader_for_runtime_id():
    calls: list[dict[str, Any]] = []

    async def _runtime_safety_readiness(input_params):
        calls.append(dict(input_params))
        if len(calls) == 1:
            return {
                "runtime_instance_id": "rt-recheck",
                "status": "ready_for_owner_codex_confirmation",
                "blockers": [],
                "warnings": [],
                "missing_boundary_facts": [],
                "not_execution_authority": True,
                "execution_intent_created": False,
                "runtime_state_mutated": False,
                "order_created": False,
                "exchange_called": False,
            }
        return {
            "runtime_instance_id": "rt-recheck",
            "status": "blocked",
            "blockers": ["max_active_positions_boundary_present"],
            "missing_boundary_facts": ["max_active_positions_boundary_present"],
            "not_execution_authority": True,
            "execution_intent_created": False,
            "runtime_state_mutated": False,
            "order_created": False,
            "exchange_called": False,
        }

    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context(
        runtime_safety_readiness=_runtime_safety_readiness,
    )
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "runtime_instance_id": "rt-recheck",
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
        assert preflight.preflight_result in {"allow", "warn"}
        assert preflight.after["execution_permission_resolution"]["final_permission"] == "intent_recording"

        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert [call["runtime_instance_id"] for call in calls] == ["rt-recheck", "rt-recheck"]
    assert result.status == "blocked"
    blocked_reason = str(result.result_summary.get("blocked_reason") or "")
    assert "runtime safety readiness blocks intent recording" in blocked_reason
    assert "max_active_positions_boundary_present" in blocked_reason
    assert len(intents) == 0
    assert brc_repo.campaign.metadata_json["trade_intent_created"] is False
    assert brc_repo.campaign.metadata_json["execution_intent_created"] is False
    assert brc_repo.campaign.metadata_json["order_created"] is False


@pytest.mark.asyncio
async def test_record_trial_trade_intent_confirm_rechecks_runtime_safety_readiness():
    admission, engine, binding, service, brc_repo, market = await _phase18_signal_evaluated_context()
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
        assert preflight.preflight_result in {"allow", "warn"}
        assert preflight.after["execution_permission_resolution"]["final_permission"] == "intent_recording"

        market["runtime_state"]["runtime_safety_readiness"] = {
            "status": "blocked",
            "blockers": ["max_loss_budget_present"],
            "missing_boundary_facts": ["max_loss_budget_present"],
            "not_execution_authority": True,
            "execution_intent_created": False,
            "runtime_state_mutated": False,
            "order_created": False,
            "exchange_called": False,
        }
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert result.status == "blocked"
    blocked_reason = str(result.result_summary.get("blocked_reason") or "")
    assert "runtime safety readiness blocks intent recording" in blocked_reason
    assert "max_loss_budget_present" in blocked_reason
    assert result.result_summary["status"] == "blocked"
    assert len(intents) == 0
    assert brc_repo.campaign.metadata_json["trade_intent_created"] is False
    assert brc_repo.campaign.metadata_json["execution_intent_created"] is False
    assert brc_repo.campaign.metadata_json["order_created"] is False
    assert not [
        event
        for event in brc_repo.events
        if event["event_type"] == "admission_trial_trade_intent_recorded_no_execution"
    ]


@pytest.mark.asyncio
async def test_record_trial_trade_intent_observe_only_records_would_enter_intent():
    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context(
        execution_mode=AdmissionExecutionMode.OBSERVE_ONLY,
    )
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
                "signal_snapshot": {"signal_id": "sig-observe"},
                "market_snapshot": {"mark_price": "3000"},
            },
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["trial_trade_intent_result"] == "recorded"
    assert "decision" not in result.result_summary
    assert result.result_summary["not_executed_reason"] == "observe_only"
    assert result.result_summary["trial_trade_intent_created"] is True
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["order_created"] is False
    assert result.result_summary["orders_placed"] is False
    assert len(intents) == 1
    assert intents[0].decision.value == "recorded"
    assert intents[0].not_executed_reason == "observe_only"
    assert brc_repo.campaign.metadata_json["runtime_status"] == "trial_trade_intent_recorded_no_execution"
    assert brc_repo.campaign.metadata_json["trial_trade_intent_result"] == "recorded"
    assert "trial_trade_intent_decision" not in brc_repo.campaign.metadata_json
    assert brc_repo.campaign.metadata_json["execution_permission"] == "intent_recording"
    assert brc_repo.campaign.metadata_json["execution_intent_created"] is False
    assert brc_repo.campaign.metadata_json["order_created"] is False
    assert not [event for event in brc_repo.events if "order" in event["event_type"] or "execution_intent" in event["event_type"]]


@pytest.mark.asyncio
async def test_record_trial_trade_intent_no_entry_blocks_entry_intent_without_execution():
    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context(
        execution_mode=AdmissionExecutionMode.NO_ENTRY,
    )
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["trial_trade_intent_result"] == "blocked"
    assert "decision" not in result.result_summary
    assert result.result_summary["not_executed_reason"] == "no_entry"
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["order_created"] is False
    assert intents[0].decision.value == "blocked"
    assert intents[0].not_executed_reason == "no_entry"


@pytest.mark.asyncio
async def test_record_trial_trade_intent_auto_within_budget_records_candidate_without_execution():
    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context(
        execution_mode=AdmissionExecutionMode.AUTO_WITHIN_BUDGET,
    )
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
        result = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert result.status == "executed"
    assert result.result_summary["trial_trade_intent_result"] == "recorded"
    assert "decision" not in result.result_summary
    assert result.result_summary["not_executed_reason"] == "live_read_only_detection_no_execution"
    assert result.result_summary["auto_within_budget_enabled"] is False
    assert result.result_summary["execution_intent_created"] is False
    assert result.result_summary["order_created"] is False
    assert intents[0].execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET
    assert intents[0].risk_snapshot_json["execution_permission_resolution"]["final_permission"] == "intent_recording"


@pytest.mark.asyncio
async def test_record_trial_trade_intent_owner_confirm_each_entry_unavailable():
    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context(
        execution_mode=AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY,
    )
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
    finally:
        await engine.dispose()

    assert preflight.preflight_result == "unavailable"
    assert "owner_confirm_each_entry execution is reserved and not implemented" in preflight.summary


@pytest.mark.asyncio
async def test_record_trial_trade_intent_double_confirm_and_new_operation_are_idempotent():
    admission, engine, binding, service, brc_repo, _ = await _phase18_signal_evaluated_context()
    try:
        preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
        first = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        second = await service.confirm(
            operation_id=preflight.operation_id,
            preflight_id=preflight.preflight_id,
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            idempotency_key=preflight.idempotency_key,
        )
        noop_preflight = await service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by="owner",
            input_params={
                "campaign_id": brc_repo.campaign.campaign_id,
                "binding_id": binding.binding_id,
                "intended_action": "entry",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
            },
        )
        noop_result = await service.confirm(
            operation_id=noop_preflight.operation_id,
            preflight_id=noop_preflight.preflight_id,
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            idempotency_key=noop_preflight.idempotency_key,
        )
        intents = await admission._repo.list_trial_trade_intents_by_campaign(
            brc_repo.campaign.campaign_id
        )
    finally:
        await engine.dispose()

    assert first.status == "executed"
    assert second.result_summary == first.result_summary
    assert noop_preflight.preflight_result in {"allow", "warn"}
    assert noop_preflight.after["idempotent_intent"] is True
    assert noop_result.status == "noop"
    assert noop_result.result_summary["idempotent"] is True
    assert len(intents) == 1


@pytest.mark.asyncio
async def test_record_trial_trade_intent_no_trading_endpoints_added():
    service, _, _, _ = await _operation_service()
    capabilities = {item.operation_type: item for item in service.capabilities()}

    assert capabilities["live_execution"].status == "forbidden"
    assert capabilities["unrestricted_order_execution"].status == "forbidden"
    assert capabilities["withdrawal"].status == "forbidden"
    assert capabilities["transfer"].status == "forbidden"


@pytest.mark.asyncio
async def test_emergency_stop_runtime_capability_becomes_executable_when_adapter_available():
    service, _, _, _ = await _operation_service(runtime_stop_adapter=True)
    capabilities = {item.operation_type: item for item in service.capabilities()}

    capability = capabilities["emergency_stop_runtime"]
    assert capability.status == "enabled"
    assert capability.executable_through_operation is True
    assert capability.confirmation_required is True
    assert capability.backend_executor == "brc_operation_runtime_stop"
    assert "does not flatten positions or cancel orders" in capability.current_reason


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_capability_becomes_executable_when_adapter_available():
    service, _, _, _ = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    capabilities = {item.operation_type: item for item in service.capabilities()}

    capability = capabilities["run_fixed_testnet_rehearsal"]
    assert capability.status == "enabled"
    assert capability.executable_through_operation is True
    assert capability.backend_executor == "brc_operation_fixed_testnet_rehearsal"
    assert capability.confirmation_required is True
    assert "Operation-authorized fixed ETH/BTC testnet rehearsal" in capability.current_reason


@pytest.mark.asyncio
async def test_switch_playbook_preflight_confirm_executes_once_and_links_refs():
    service, op_repo, brc_repo, _ = await _operation_service()
    preflight = await _switch_preflight(service)

    assert preflight.preflight_result == "allow"
    assert preflight.status == "awaiting_confirmation"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_SWITCH_PLAYBOOK"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.campaign_refs
    assert result.audit_refs[0]["type"] == "operation"
    assert brc_repo.campaign.current_playbook_id == "PB-004-BRC-CONTROLLED-TESTNET"
    assert len(brc_repo.switches) == 1
    switch_event = next(item for item in brc_repo.events if item["event_type"] == "playbook_switched")
    assert switch_event["metadata"]["operation_id"] == preflight.operation_id
    assert switch_event["metadata"]["preflight_id"] == preflight.preflight_id
    assert f"operation:{preflight.operation_id}" in switch_event["metadata"]["evidence_refs"]

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert again.status == "executed"
    assert len(brc_repo.switches) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"


@pytest.mark.asyncio
async def test_tf001_carrier_playbook_can_be_selected_without_trading_authority():
    service, op_repo, brc_repo, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="switch_playbook",
        requested_by="owner",
        input_params={
            "target_playbook_id": "TF-001",
            "reason_text": "TF-001 carrier validation selection",
            "evidence_refs": ["docs/ops/brc-r5-001-tf001-carrier-full-chain-validation-plan.md"],
        },
        source={"kind": "unit"},
    )

    assert preflight.preflight_result == "allow"
    assert preflight.playbook_summary["known"] is True
    assert preflight.playbook_summary["target_playbook_id"] == "TF-001"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert brc_repo.campaign.current_playbook_id == "TF-001"
    assert len(brc_repo.switches) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"
    assert "No orders were placed" in result.result_summary["message"]
    switch_event = next(item for item in brc_repo.events if item["event_type"] == "playbook_switched")
    assert switch_event["metadata"]["preflight_id"] == preflight.preflight_id
    assert f"operation:{preflight.operation_id}" in switch_event["metadata"]["evidence_refs"]


@pytest.mark.asyncio
async def test_unknown_operation_rejected_before_persistence():
    service, op_repo, _, _ = await _operation_service()

    with pytest.raises(OperationLayerError, match="unknown operation_type"):
        await service.preflight(
            operation_type="totally_unknown",
            requested_by="owner",
            input_params={},
        )

    assert await op_repo.list_operations() == []


@pytest.mark.asyncio
async def test_unknown_playbook_persists_blocked_operation_result():
    service, op_repo, brc_repo, _ = await _operation_service()

    preflight = await service.preflight(
        operation_type="switch_playbook",
        requested_by="owner",
        input_params={
            "target_playbook_id": "PB-999-NOT-REAL",
            "evidence_refs": ["evidence"],
        },
    )

    assert preflight.preflight_result == "block"
    assert preflight.status == "blocked"
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "unknown playbook" in (result.blocked_reason or "")
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_wrong_confirmation_phrase_blocks_without_execute():
    service, _, brc_repo, _ = await _operation_service()
    preflight = await _switch_preflight(service)

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="WRONG",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "blocked"
    assert "confirmation phrase mismatch" in str(result.result_summary)
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_expired_preflight_persists_expired_result():
    service, _, brc_repo, _ = await _operation_service(ttl_ms=-1)
    preflight = await _switch_preflight(service)

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "expired"
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_audit_writable_false_blocks_on_confirm_recheck():
    service, _, brc_repo, _ = await _operation_service(audit_writable=False)
    preflight = await _switch_preflight(service)

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "blocked"
    assert "audit is not writable" in str(result.result_summary)
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_market_drift_blocks_on_confirm_recheck():
    service, _, brc_repo, market = await _operation_service()
    preflight = await _switch_preflight(service)
    market["open_order_count"] = 1
    market["all_local_flat"] = False

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "blocked"
    assert "account/order facts changed" in str(result.result_summary)
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_operation_preflight_includes_account_facts_source_and_blocks_unavailable_for_medium_risk():
    service, _, _, _ = await _operation_service()
    preflight = await _switch_preflight(service)

    assert preflight.account_order_summary["source"] == "local_pg"
    assert preflight.account_order_summary["truth_level"] == "summary"
    assert preflight.account_order_summary["reconciliation_status"]["status"] == "not_available"

    blocked_service, op_repo, brc_repo, _ = await _operation_service(
        market_state={
            "source": "unavailable",
            "truth_level": "unavailable",
            "active_position_count": 0,
            "open_order_count": 0,
            "all_local_flat": False,
            "blockers": ["local PG position/order repositories are not available"],
        }
    )
    blocked = await _switch_preflight(blocked_service)

    assert blocked.status == "blocked"
    result = await op_repo.get_execution_result(blocked.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "account facts unavailable" in (result.blocked_reason or "")
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_medium_risk_operation_blocks_on_account_reconciliation_mismatch():
    service, op_repo, brc_repo, _ = await _operation_service(
        market_state={
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "mismatch"},
            "active_position_count": 0,
            "open_order_count": 1,
            "all_local_flat": False,
            "unknown_or_unmanaged_order_count": 1,
            "unknown_or_unmanaged_position_count": 0,
        }
    )
    preflight = await _switch_preflight(service)

    assert preflight.status == "blocked"
    assert preflight.account_order_summary["reconciliation_status"]["status"] == "mismatch"
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "account reconciliation mismatch" in (result.blocked_reason or "")
    assert brc_repo.switches == []


@pytest.mark.asyncio
async def test_cancel_get_and_list_operation():
    service, _, _, _ = await _operation_service()
    preflight = await _switch_preflight(service)

    cancelled = await service.cancel(operation_id=preflight.operation_id)
    detail = await service.get(preflight.operation_id)
    listed = await service.list(limit=10)

    assert cancelled.status == "cancelled"
    assert detail.operation.status == "cancelled"
    assert detail.result is not None
    assert listed.operations[0].operation_id == preflight.operation_id


@pytest.mark.asyncio
async def test_forbidden_operation_preflight_is_not_executable():
    service, op_repo, _, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="withdrawal",
        requested_by="owner",
        input_params={"asset": "USDT", "amount": "1"},
    )

    assert preflight.preflight_result == "block"
    assert preflight.confirmation_requirement.required is False
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"


@pytest.mark.asyncio
async def test_write_review_outcome_preflight_confirm_executes_once_and_links_refs():
    service, op_repo, brc_repo, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="write_review_outcome",
        requested_by="owner",
        input_params={
            "review_outcome": "accepted",
            "reason_text": "owner reviewed operation layer evidence",
            "next_recommended_task": "continue bounded review",
        },
    )

    assert preflight.status == "awaiting_confirmation"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_WRITE_REVIEW"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_WRITE_REVIEW",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.review_refs[0]["type"] == "review_outcome"
    assert result.result_summary["review_outcome"] == "accepted"
    assert "decision" not in result.result_summary
    persisted = await op_repo.get_execution_result(preflight.operation_id)
    assert persisted is not None
    assert "review_outcome" in persisted.adapter_result
    assert "review_decision" not in persisted.adapter_result
    assert "review_outcome" in persisted.final_state_snapshot
    assert "review_decision" not in persisted.final_state_snapshot
    assert result.audit_refs
    assert len(brc_repo.review_decisions) == 1
    assert brc_repo.review_decisions[0].metadata_json["operation_id"] == preflight.operation_id

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_WRITE_REVIEW",
        idempotency_key=preflight.idempotency_key,
    )
    assert again.status == "executed"
    assert len(brc_repo.review_decisions) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"


@pytest.mark.asyncio
async def test_write_review_outcome_wrong_phrase_expired_and_audit_recheck_block():
    service, _, brc_repo, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="write_review_outcome",
        requested_by="owner",
        input_params={
            "review_outcome": "accepted",
            "reason_text": "review",
            "next_recommended_task": "next",
        },
    )
    wrong = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="WRONG",
        idempotency_key=preflight.idempotency_key,
    )
    assert wrong.status == "blocked"
    assert brc_repo.review_decisions == []

    expired_service, _, expired_repo, _ = await _operation_service(ttl_ms=-1)
    expired_preflight = await expired_service.preflight(
        operation_type="write_review_outcome",
        requested_by="owner",
        input_params={
            "review_outcome": "accepted",
            "reason_text": "review",
            "next_recommended_task": "next",
        },
    )
    expired = await expired_service.confirm(
        operation_id=expired_preflight.operation_id,
        preflight_id=expired_preflight.preflight_id,
        confirmation_phrase="CONFIRM_WRITE_REVIEW",
        idempotency_key=expired_preflight.idempotency_key,
    )
    assert expired.status == "expired"
    assert expired_repo.review_decisions == []

    blocked_service, _, blocked_repo, _ = await _operation_service(audit_writable=False)
    blocked_preflight = await blocked_service.preflight(
        operation_type="write_review_outcome",
        requested_by="owner",
        input_params={
            "review_outcome": "accepted",
            "reason_text": "review",
            "next_recommended_task": "next",
        },
    )
    blocked = await blocked_service.confirm(
        operation_id=blocked_preflight.operation_id,
        preflight_id=blocked_preflight.preflight_id,
        confirmation_phrase="CONFIRM_WRITE_REVIEW",
        idempotency_key=blocked_preflight.idempotency_key,
    )
    assert blocked.status == "blocked"
    assert blocked_repo.review_decisions == []


@pytest.mark.asyncio
async def test_start_review_reads_packet_without_mutation():
    service, _, _, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="start_review",
        requested_by="owner",
        input_params={},
    )
    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_START_REVIEW",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.review_refs[0]["type"] == "review_artifact"
    assert result.result_summary["mutation_executed"] is False


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_is_explicitly_unavailable_without_authorized_operation_adapter():
    service, op_repo, _, _ = await _operation_service()
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={"source": "fixed_rehearsal_page"},
    )

    assert preflight.status == "blocked"
    assert preflight.preflight_result == "unavailable"
    assert preflight.confirmation_requirement.required is False
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "fixed rehearsal executor is not wired" in (result.blocked_reason or "").lower()


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_preflight_confirm_executes_once_and_links_refs():
    service, op_repo, _, market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={"source": "fixed_rehearsal_page"},
    )

    assert preflight.status == "awaiting_confirmation"
    assert preflight.preflight_result == "allow"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_FIXED_TESTNET_REHEARSAL"
    assert preflight.after["symbols"] == ["ETH/USDT:USDT", "BTC/USDT:USDT"]
    assert preflight.after["workflow_carrier"] == "internal_ref_only"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.result_summary["workflow_run_id"] == f"op-wf-{preflight.operation_id}"
    assert result.result_summary["campaign_id"] == "brc-rehearsal"
    assert result.result_summary["live_ready"] is False
    assert result.audit_refs[0]["type"] == "workflow_run"
    assert any(item["type"] == "evidence_artifact" for item in result.audit_refs)
    assert not any(item["type"] == "evidence_packet" for item in result.audit_refs)
    assert any(item["type"] == "review_outcome" for item in result.review_refs)
    assert any(item["type"] == "campaign" for item in result.campaign_refs)
    assert market["fixed_rehearsal_calls"][0]["authorization_source"] == "brc_operation_layer"
    assert market["fixed_rehearsal_calls"][0]["workflow_carrier_role"] == "internal_ref_only"
    assert market["fixed_rehearsal_calls"][0]["allowed_symbols"] == ["ETH/USDT:USDT", "BTC/USDT:USDT"]

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=preflight.idempotency_key,
    )

    assert again.status == "executed"
    assert len(market["fixed_rehearsal_calls"]) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_wrong_phrase_expired_and_audit_recheck_block():
    service, _, _, market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    wrong = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="WRONG",
        idempotency_key=preflight.idempotency_key,
    )
    assert wrong.status == "blocked"
    assert market["fixed_rehearsal_calls"] == []

    expired_service, _, _, expired_market = await _operation_service(
        ttl_ms=-1,
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    expired_preflight = await expired_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    expired = await expired_service.confirm(
        operation_id=expired_preflight.operation_id,
        preflight_id=expired_preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=expired_preflight.idempotency_key,
    )
    assert expired.status == "expired"
    assert expired_market["fixed_rehearsal_calls"] == []

    blocked_service, _, _, blocked_market = await _operation_service(
        audit_writable=False,
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    blocked_preflight = await blocked_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    blocked = await blocked_service.confirm(
        operation_id=blocked_preflight.operation_id,
        preflight_id=blocked_preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=blocked_preflight.idempotency_key,
    )
    assert blocked.status == "blocked"
    assert "audit is not writable" in str(blocked.result_summary)
    assert blocked_market["fixed_rehearsal_calls"] == []


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_blocks_mutation_gates_guards_live_and_campaign_state():
    cases = [
        ({"runtime_control_api_enabled": False}, "runtime mutation gate is not enabled"),
        ({"runtime_test_signal_injection_enabled": False}, "controlled test signal gate is not enabled"),
        ({"gks_active": False}, "global kill switch must be active"),
        ({"startup_guard_armed": True}, "startup guard must not already be armed"),
        ({"testnet": False}, "exchange testnet is not confirmed"),
        ({"profile": "live"}, "runtime profile is not brc_btc_eth_testnet_runtime"),
        ({"live_ready": True}, "live/mainnet readiness is forbidden"),
    ]
    for runtime_state, expected in cases:
        service, op_repo, _, market = await _operation_service(
            fixed_rehearsal_adapter=True,
            create_campaign=False,
            runtime_state=runtime_state,
        )
        preflight = await service.preflight(
            operation_type="run_fixed_testnet_rehearsal",
            requested_by="owner",
            input_params={},
        )
        assert preflight.status == "blocked"
        result = await op_repo.get_execution_result(preflight.operation_id)
        assert result is not None
        assert result.status == "blocked"
        assert expected in (result.blocked_reason or "")
        assert market["fixed_rehearsal_calls"] == []

    active_campaign_service, active_campaign_repo, _, active_campaign_market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=True,
    )
    active_campaign_preflight = await active_campaign_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    active_campaign_result = await active_campaign_repo.get_execution_result(
        active_campaign_preflight.operation_id
    )
    assert active_campaign_result is not None
    assert active_campaign_result.status == "blocked"
    assert "active BRC campaign already exists" in (active_campaign_result.blocked_reason or "")
    assert active_campaign_market["fixed_rehearsal_calls"] == []


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_blocks_open_orders_and_market_drift_on_recheck():
    open_order_service, open_order_repo, _, open_order_market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
        market_state={
            "active_position_count": 0,
            "open_order_count": 1,
            "all_local_flat": True,
            "data_source": "unit",
        },
    )
    open_order_preflight = await open_order_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    open_order_result = await open_order_repo.get_execution_result(open_order_preflight.operation_id)
    assert open_order_result is not None
    assert open_order_result.status == "blocked"
    assert "local open orders exist" in (open_order_result.blocked_reason or "")
    assert open_order_market["fixed_rehearsal_calls"] == []

    service, _, _, market = await _operation_service(
        fixed_rehearsal_adapter=True,
        create_campaign=False,
    )
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    market["open_order_count"] = 1
    market["all_local_flat"] = False
    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=preflight.idempotency_key,
    )
    assert result.status == "blocked"
    assert "local open orders exist" in str(result.result_summary)
    assert market["fixed_rehearsal_calls"] == []


@pytest.mark.asyncio
async def test_run_fixed_testnet_rehearsal_runner_failure_and_forbidden_flags_persist_failed():
    service, op_repo, _, market = await _operation_service(
        fixed_rehearsal_adapter=True,
        fixed_rehearsal_failure=RuntimeError("runner failed"),
        create_campaign=False,
    )
    preflight = await service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    failed = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=preflight.idempotency_key,
    )
    assert failed.status == "failed"
    stored_failed = await op_repo.get_execution_result(preflight.operation_id)
    assert stored_failed is not None
    assert stored_failed.failed_reason == "runner failed"
    assert len(market["fixed_rehearsal_calls"]) == 1

    async def _unsafe_executor(_input):
        return {"workflow_run_id": "wf-unsafe", "live_ready": True, "withdrawal_executed": False}

    unsafe_repo = InMemoryOperationRepository()
    runtime = _default_runtime_summary()
    unsafe_service = BrcOperationService(
        repository=unsafe_repo,
        brc_campaign_service=(await _campaign_service(create_campaign=False))[0],
        readers=OperationLayerReaders(
            runtime_summary=lambda: _async_dict(runtime),
            markets_orders_summary=lambda: _async_dict({
                "active_position_count": 0,
                "open_order_count": 0,
                "all_local_flat": True,
            }),
            audit_writable=lambda: _async_bool(True),
            fixed_rehearsal_executor=_unsafe_executor,
        ),
    )
    await unsafe_service.initialize()
    unsafe_preflight = await unsafe_service.preflight(
        operation_type="run_fixed_testnet_rehearsal",
        requested_by="owner",
        input_params={},
    )
    unsafe = await unsafe_service.confirm(
        operation_id=unsafe_preflight.operation_id,
        preflight_id=unsafe_preflight.preflight_id,
        confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
        idempotency_key=unsafe_preflight.idempotency_key,
    )
    assert unsafe.status == "failed"
    assert "forbidden live/withdrawal flags" in str(unsafe.result_summary)


@pytest.mark.asyncio
async def test_runtime_state_operations_execute_or_degrade_safely():
    service, _, _, _ = await _operation_service()
    observe_preflight = await service.preflight(
        operation_type="enter_observe",
        requested_by="owner",
        input_params={"reason": "owner observe"},
    )
    observe = await service.confirm(
        operation_id=observe_preflight.operation_id,
        preflight_id=observe_preflight.preflight_id,
        confirmation_phrase="CONFIRM_ENTER_OBSERVE",
        idempotency_key=observe_preflight.idempotency_key,
    )
    assert observe.status == "noop"
    assert observe.next_state["runtime_transition"]["status"] == "observe"

    pause_preflight = await service.preflight(
        operation_type="enter_pause",
        requested_by="owner",
        input_params={"reason": "owner pause"},
    )
    pause = await service.confirm(
        operation_id=pause_preflight.operation_id,
        preflight_id=pause_preflight.preflight_id,
        confirmation_phrase="CONFIRM_ENTER_PAUSE",
        idempotency_key=pause_preflight.idempotency_key,
    )
    assert pause.status == "executed"
    assert pause.next_state["runtime_transition"]["status"] == "paused"
    assert pause.result_summary["pg_state_mutated"] is True
    assert pause.result_summary["places_orders"] is False
    assert pause.result_summary["live_ready"] is False

    monitor_preflight = await service.preflight(
        operation_type="enter_strategy_or_monitor",
        requested_by="owner",
        input_params={},
    )
    monitor = await service.confirm(
        operation_id=monitor_preflight.operation_id,
        preflight_id=monitor_preflight.preflight_id,
        confirmation_phrase="CONFIRM_ENTER_MONITOR",
        idempotency_key=monitor_preflight.idempotency_key,
    )
    assert monitor.status == "noop"
    assert monitor.next_state["carrier"] == "monitor"
    assert "unrestricted auto trading" in monitor.result_summary["message"]


@pytest.mark.asyncio
async def test_runtime_transition_unavailable_when_adapter_missing():
    service, op_repo, _, _ = await _operation_service(runtime_adapter=False)
    preflight = await service.preflight(
        operation_type="enter_pause",
        requested_by="owner",
        input_params={},
    )

    assert preflight.status == "blocked"
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "runtime transition adapter unavailable" in (result.blocked_reason or "")


@pytest.mark.asyncio
async def test_revoke_budget_preflight_and_confirmation_persist_effective_state():
    service, _, _, market = await _operation_service()
    preflight = await service.preflight(
        operation_type="revoke_budget",
        requested_by="owner",
        input_params={"reason": "owner revoke budget"},
    )

    assert preflight.status == "awaiting_confirmation"
    assert preflight.preflight_result == "warn"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_REVOKE_BUDGET"
    assert preflight.after["budget_authorization_id"] == "budget-1"
    assert preflight.after["budget_effective_state"] == "revoked"
    assert preflight.after["future_budgeted_actions_allowed"] is False

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_REVOKE_BUDGET",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.result_summary["budget_authorization_id"] == "budget-1"
    assert result.result_summary["budget_effective_state"] == "revoked"
    assert result.result_summary["future_budgeted_actions_allowed"] is False
    assert result.result_summary["places_orders"] is False
    assert result.result_summary["closes_positions"] is False
    assert result.result_summary["cancels_orders"] is False
    assert result.result_summary["transfer_executed"] is False
    assert result.result_summary["withdrawal_executed"] is False
    assert market["budget_state"]["latest_budget_authorization"]["status"] == "revoked"
    assert market["budget_state"]["latest_budget_authorization"]["last_control_operation_id"] == preflight.operation_id
    assert len(market["budget_revoke_calls"]) == 1


@pytest.mark.asyncio
async def test_revoke_budget_repeated_confirm_is_idempotent_noop():
    service, _, _, market = await _operation_service(budget_authorization_status="revoked")
    preflight = await service.preflight(
        operation_type="revoke_budget",
        requested_by="owner",
        input_params={"reason": "owner revoke budget again"},
    )

    assert preflight.status == "awaiting_confirmation"
    assert preflight.after["already_revoked"] is True

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_REVOKE_BUDGET",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "noop"
    assert result.result_summary["already_revoked"] is True
    assert result.result_summary["future_budgeted_actions_allowed"] is False
    assert len(market["budget_revoke_calls"]) == 1


@pytest.mark.asyncio
async def test_revoke_budget_blocks_when_no_current_budget_authorization():
    service, op_repo, _, _ = await _operation_service(budget_authorization_status=None)
    preflight = await service.preflight(
        operation_type="revoke_budget",
        requested_by="owner",
        input_params={},
    )

    assert preflight.status == "blocked"
    result = await op_repo.get_execution_result(preflight.operation_id)
    assert result is not None
    assert result.status == "blocked"
    assert "current budget authorization unavailable" in (result.blocked_reason or "")


@pytest.mark.asyncio
async def test_emergency_flatten_dry_run_no_exposure_persists_noop_without_trading():
    service, op_repo, _, _ = await _operation_service()

    preflight = await service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={"reason": "owner dry-run"},
    )

    assert preflight.preflight_result == "warn"
    assert preflight.status == "awaiting_confirmation"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_FLATTEN_DRY_RUN"
    assert preflight.after["dry_run_only"] is True
    assert preflight.after["actual_execution_available"] is False
    assert preflight.after["actual_execution"] is False
    assert preflight.after["dry_run_plan"]["estimated_actions_count"] == 0
    assert preflight.after["dry_run_plan"]["plan_status"] == "noop"
    assert preflight.after["estimated_flatten_impact"]["planned_result_status"] == "noop"
    assert any("no positions and no open orders" in item for item in preflight.risk_summary["warnings"])
    assert preflight.risk_summary["blockers"] == []

    confirm = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FLATTEN_DRY_RUN",
        idempotency_key=preflight.idempotency_key,
    )
    stored = await op_repo.get_execution_result(preflight.operation_id)
    assert confirm.status == "noop"
    assert stored is not None
    assert stored.status == "noop"
    assert stored.result_summary["dry_run_only"] is True
    assert stored.result_summary["actual_execution"] is False
    assert stored.result_summary["orders_cancelled"] is False
    assert stored.result_summary["positions_closed"] is False
    assert stored.audit_refs[0]["type"] == "flatten_dry_run"


@pytest.mark.asyncio
async def test_emergency_flatten_dry_run_with_clean_exposure_returns_candidates_and_confirms_once():
    service, op_repo, _, _ = await _operation_service(
        market_state={
            "active_position_count": 1,
            "open_order_count": 1,
            "all_local_flat": False,
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "clean"},
            "positions": [{"position_id": "pos-1", "symbol": "ETH/USDT:USDT", "side": "long", "size": "0.01"}],
            "open_orders": [{"order_id": "ord-1", "symbol": "ETH/USDT:USDT", "side": "sell", "order_type": "STOP_MARKET"}],
        }
    )
    preflight = await service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )

    assert preflight.preflight_result == "allow"
    assert preflight.status == "awaiting_confirmation"
    plan = preflight.after["dry_run_plan"]
    assert plan["dry_run_only"] is True
    assert plan["actual_execution"] is False
    assert plan["estimated_actions_count"] == 2
    assert plan["cancel_order_candidates"][0]["candidate_only"] is True
    assert plan["cancel_order_candidates"][0]["executable_order_request"] is False
    assert plan["close_position_candidates"][0]["candidate_only"] is True
    assert plan["close_position_candidates"][0]["executable_order_request"] is False

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FLATTEN_DRY_RUN",
        idempotency_key=preflight.idempotency_key,
    )
    assert result.status == "executed"
    assert result.result_summary["estimated_actions_count"] == 2
    assert result.result_summary["orders_cancelled"] is False
    assert result.result_summary["positions_closed"] is False
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_FLATTEN_DRY_RUN",
        idempotency_key=preflight.idempotency_key,
    )
    assert again.status == "executed"


@pytest.mark.asyncio
async def test_emergency_flatten_diagnostic_dry_run_on_mismatch_or_unmanaged_exposure():
    mismatch_service, _, _, _ = await _operation_service(
        market_state={
            "active_position_count": 0,
            "open_order_count": 0,
            "all_local_flat": True,
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "mismatch"},
        }
    )
    mismatch = await mismatch_service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )
    assert mismatch.preflight_result == "warn"
    assert mismatch.status == "awaiting_confirmation"
    assert mismatch.after["actual_execution"] is False
    assert mismatch.after["dry_run_plan"]["exposure_summary"]["reconciliation_status"] == "mismatch"
    assert any("reconciliation mismatch" in item for item in mismatch.risk_summary["warnings"])

    unmanaged_service, _, _, _ = await _operation_service(
        market_state={
            "active_position_count": 0,
            "open_order_count": 1,
            "all_local_flat": False,
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "clean"},
            "unknown_or_unmanaged_orders": [{"id": "exchange-orphan"}],
        }
    )
    unmanaged = await unmanaged_service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )
    assert unmanaged.preflight_result == "warn"
    assert unmanaged.status == "awaiting_confirmation"
    assert unmanaged.after["unknown_or_unmanaged_orders"][0]["id"] == "exchange-orphan"
    assert any("unknown or unmanaged" in item for item in unmanaged.risk_summary["warnings"])


@pytest.mark.asyncio
async def test_emergency_flatten_account_unavailable_and_live_are_blocked_without_confirm():
    unavailable_service, unavailable_repo, _, _ = await _operation_service(
        market_state={
            "source": "unavailable",
            "truth_level": "unavailable",
            "active_position_count": 0,
            "open_order_count": 0,
            "all_local_flat": False,
        }
    )
    unavailable = await unavailable_service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )
    assert unavailable.status == "blocked"
    unavailable_result = await unavailable_repo.get_execution_result(unavailable.operation_id)
    assert unavailable_result is not None
    assert "account facts unavailable" in (unavailable_result.blocked_reason or "")

    live_service, live_repo, _, _ = await _operation_service(
        runtime_state={"testnet": False, "live_ready": True},
    )
    live = await live_service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={},
    )
    assert live.status == "blocked"
    live_result = await live_repo.get_execution_result(live.operation_id)
    assert live_result is not None
    assert "live/mainnet flatten execution is forbidden" in (live_result.blocked_reason or "")


@pytest.mark.asyncio
async def test_emergency_stop_runtime_preflight_planning_unavailable_without_executor():
    service, op_repo, _, _ = await _operation_service()

    preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={"reason": "owner planning only"},
    )

    assert preflight.preflight_result == "unavailable"
    assert preflight.status == "blocked"
    assert preflight.after["planning_only"] is True
    assert preflight.after["actual_execution_available"] is False
    assert preflight.after["expected_stop_behavior"]["does_not_flatten"] is True
    assert preflight.after["expected_stop_behavior"]["does_not_cancel_orders"] is True
    assert any("executor unavailable" in item for item in preflight.risk_summary["blockers"])

    confirm = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="",
        idempotency_key=preflight.idempotency_key,
    )
    assert confirm.status == "blocked"
    assert (await op_repo.get_execution_result(preflight.operation_id)).status == "blocked"


@pytest.mark.asyncio
async def test_emergency_stop_runtime_preflight_confirm_executes_once_and_links_runtime_refs():
    service, op_repo, _, market = await _operation_service(runtime_stop_adapter=True)

    preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={"reason": "owner emergency stop"},
    )

    assert preflight.preflight_result == "allow"
    assert preflight.status == "awaiting_confirmation"
    assert preflight.confirmation_requirement.phrase == "CONFIRM_STOP_RUNTIME"
    assert preflight.after["actual_execution_available"] is True
    assert preflight.after["planning_only"] is False
    assert preflight.after["does_not_flatten"] is True
    assert preflight.after["does_not_cancel_orders"] is True
    assert preflight.after["expected_stop_behavior"]["does_not_flatten"] is True
    assert preflight.after["expected_stop_behavior"]["does_not_cancel_orders"] is True

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "executed"
    assert result.result_summary["runtime_state"] == "hard_locked"
    assert result.result_summary["does_not_flatten"] is True
    assert result.result_summary["does_not_cancel_orders"] is True
    assert result.audit_refs[0]["type"] == "runtime_stop"
    assert result.next_state["runtime_state"] == "hard_locked"
    assert market["runtime_stop_calls"][0]["authorization_source"] == "brc_operation_layer"
    assert market["runtime_stop_calls"][0]["does_not_flatten"] is True
    assert market["runtime_stop_calls"][0]["does_not_cancel_orders"] is True

    again = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=preflight.idempotency_key,
    )

    assert again.status == "executed"
    assert len(market["runtime_stop_calls"]) == 1
    assert (await op_repo.get_operation(preflight.operation_id)).status == "executed"


@pytest.mark.asyncio
async def test_emergency_stop_runtime_already_stopped_records_noop_without_calling_adapter():
    service, _, _, market = await _operation_service(
        runtime_stop_adapter=True,
        runtime_state={"current_runtime_state": "hard_locked"},
    )

    preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    assert preflight.preflight_result == "warn"
    assert preflight.after["already_stopped"] is True
    assert preflight.after["planned_result_status"] == "noop"

    result = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=preflight.idempotency_key,
    )

    assert result.status == "noop"
    assert result.result_summary["runtime_state"] == "hard_locked"
    assert market["runtime_stop_calls"] == []


@pytest.mark.asyncio
async def test_emergency_stop_runtime_wrong_phrase_expired_audit_and_failure_paths():
    service, _, _, market = await _operation_service(runtime_stop_adapter=True)
    preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    wrong = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="WRONG",
        idempotency_key=preflight.idempotency_key,
    )
    assert wrong.status == "blocked"
    assert market["runtime_stop_calls"] == []

    expired_service, _, _, expired_market = await _operation_service(
        ttl_ms=-1,
        runtime_stop_adapter=True,
    )
    expired_preflight = await expired_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    expired = await expired_service.confirm(
        operation_id=expired_preflight.operation_id,
        preflight_id=expired_preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=expired_preflight.idempotency_key,
    )
    assert expired.status == "expired"
    assert expired_market["runtime_stop_calls"] == []

    audit_block_service, audit_block_repo, _, audit_block_market = await _operation_service(
        audit_writable=False,
        runtime_stop_adapter=True,
    )
    audit_block_preflight = await audit_block_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    assert audit_block_preflight.status == "blocked"
    audit_block_result = await audit_block_repo.get_execution_result(audit_block_preflight.operation_id)
    assert audit_block_result is not None
    assert audit_block_result.status == "blocked"
    assert "audit is not writable" in (audit_block_result.blocked_reason or "")
    assert audit_block_market["runtime_stop_calls"] == []

    failed_service, failed_repo, _, failed_market = await _operation_service(
        runtime_stop_adapter=True,
        runtime_stop_failure=RuntimeError("stop adapter failed"),
    )
    failed_preflight = await failed_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    failed = await failed_service.confirm(
        operation_id=failed_preflight.operation_id,
        preflight_id=failed_preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=failed_preflight.idempotency_key,
    )
    assert failed.status == "failed"
    stored_failed = await failed_repo.get_execution_result(failed_preflight.operation_id)
    assert stored_failed is not None
    assert stored_failed.failed_reason == "stop adapter failed"
    assert len(failed_market["runtime_stop_calls"]) == 1


@pytest.mark.asyncio
async def test_emergency_stop_runtime_blocks_live_and_unmanaged_account_facts_without_claiming_cleanup():
    live_service, live_repo, _, live_market = await _operation_service(
        runtime_stop_adapter=True,
        runtime_state={"live_ready": True},
    )
    live_preflight = await live_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    assert live_preflight.status == "blocked"
    live_result = await live_repo.get_execution_result(live_preflight.operation_id)
    assert live_result is not None
    assert "live/mainnet runtime stop execution is forbidden" in (live_result.blocked_reason or "")
    assert live_market["runtime_stop_calls"] == []

    unmanaged_service, unmanaged_repo, _, unmanaged_market = await _operation_service(
        runtime_stop_adapter=True,
        market_state={
            "source": "mixed",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "clean"},
            "active_position_count": 0,
            "open_order_count": 1,
            "all_local_flat": False,
            "unknown_or_unmanaged_orders": [{"id": "orphan-order"}],
        },
    )
    unmanaged = await unmanaged_service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={},
    )
    assert unmanaged.status == "blocked"
    assert unmanaged.after["does_not_flatten"] is True
    assert unmanaged.after["does_not_cancel_orders"] is True
    unmanaged_result = await unmanaged_repo.get_execution_result(unmanaged.operation_id)
    assert unmanaged_result is not None
    assert "unknown or unmanaged exchange exposure" in (unmanaged_result.blocked_reason or "")
    assert unmanaged_market["runtime_stop_calls"] == []


@pytest.mark.asyncio
async def test_no_live_withdrawal_or_arbitrary_trading_paths_are_executable():
    service, _, _, _ = await _operation_service()
    capabilities = {item.operation_type: item for item in service.capabilities()}

    for operation_type in [
        "live_execution",
        "withdrawal",
        "transfer",
        "unrestricted_order_execution",
        "arbitrary_symbol_order",
        "arbitrary_side_size_order",
        "llm_direct_execution",
    ]:
        assert capabilities[operation_type].status == "forbidden"
        assert capabilities[operation_type].executable_through_operation is False


@pytest.mark.asyncio
async def test_pg_operation_repository_initialize_fails_when_migration_missing():
    from src.infrastructure.pg_brc_operation_repository import PgBrcOperationRepository

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        repository = PgBrcOperationRepository(async_sessionmaker(engine, expire_on_commit=False))
        with pytest.raises(RuntimeError, match="migration is not applied"):
            await repository.initialize()
    finally:
        await engine.dispose()
