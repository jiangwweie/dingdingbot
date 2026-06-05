"""BNB one-shot live execution bridge dry run.

This module verifies the path from PG-backed Owner live authorization to the
execution boundary. It never creates execution intents, orders, permissions,
runtime starts, or exchange writes.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.owner_action_carrier_catalog import get_owner_action_carrier
from src.application.owner_trial_flow import (
    OwnerTrialFlowError,
    OwnerTrialFlowService,
    SUPPORTED_OWNER_TRIAL_CARRIER_ID,
)
from src.application.production_strategy_family_admission import GenericActionSpec
from src.application.strategy_trial_preflight_facts import TrialPreflightFactsSnapshot
from src.infrastructure.database import get_pg_session_maker


BridgeStatus = Literal[
    "dry_run_reached_execution_boundary",
    "blocked_before_execution_boundary",
]
PlanPreviewStatus = Literal[
    "preview_ready",
    "preview_blocked_by_hard_gates",
    "preview_unavailable_invalid_scope",
]
CORE_FINAL_GATE_FACT_IDS = {
    "active_position",
    "open_order",
    "gks",
    "startup_guard",
    "account_facts",
}


class BnbLiveExecutionBridgeDryRunRequest(BaseModel):
    carrier_id: str = SUPPORTED_OWNER_TRIAL_CARRIER_ID
    symbol: str = "BNB/USDT:USDT"
    side: Literal["long", "short"] = "long"
    max_notional: Decimal = Field(default=Decimal("20"), gt=Decimal("0"))
    quantity: Decimal = Field(default=Decimal("0.01"), gt=Decimal("0"))
    leverage: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    protection_plan_type: Literal["single_tp_plus_sl"] = "single_tp_plus_sl"


class BnbLiveExecutionBridgeTableAudit(BaseModel):
    execution_intents: bool
    orders: bool
    brc_execution_results: bool
    expected_execution_intents_migration: str = "033"
    order_table_migration: str = "002"
    result_logging_migration: str = "017"
    correct_pg_database_checked: bool = True


class BnbLiveExecutionBridgeAuthorizationState(BaseModel):
    exists: bool
    status: str
    live_authorized: bool
    single_use: bool
    unconsumed: bool
    live_ready: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    order_permission_granted: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False


class BnbLiveExecutionBridgeGateFactState(BaseModel):
    state: str
    status: str
    source: str
    blockers: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class BnbLiveExecutionBridgePersistenceReadiness(BaseModel):
    execution_intents: bool
    orders: bool
    result_review_logging: bool
    source: Literal["pg_table_audit"] = "pg_table_audit"


class BnbExecutionPlanEntryOrderPreview(BaseModel):
    order_type: Literal["market"]
    intended_behavior: str
    quantity: Decimal
    max_notional: Decimal
    leverage: Decimal


class BnbExecutionPlanProtectionPreview(BaseModel):
    plan_type: Literal["single_tp_plus_sl"]
    take_profit_quantity: Decimal
    stop_loss_quantity: Decimal
    safety_assumptions: list[str]


class BnbExecutionPlanPreviewFlags(BaseModel):
    preview_only: Literal[True] = True
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_permission_granted: Literal[False] = False
    auto_execution_enabled: Literal[False] = False


class BnbExecutionPlanPreview(BaseModel):
    status: PlanPreviewStatus
    authorization_id: str | None = None
    draft_id: str | None = None
    carrier_id: str
    symbol: str
    side: Literal["long", "short"]
    max_notional: Decimal
    quantity: Decimal
    leverage: Decimal
    entry_order: BnbExecutionPlanEntryOrderPreview
    protection_plan: BnbExecutionPlanProtectionPreview
    expected_record_path: list[str]
    expected_review_state: str
    cleanup_behavior_if_protection_attach_fails: str
    exact_blockers: list[str] = Field(default_factory=list)
    flags: BnbExecutionPlanPreviewFlags = Field(default_factory=BnbExecutionPlanPreviewFlags)
    executable: Literal[False] = False


class BnbLiveExecutionBridgeFinalGateReadModel(BaseModel):
    result: Literal["passed", "blocked"]
    exact_blockers: list[str] = Field(default_factory=list)
    runtime_safety_state: str
    startup_guard: BnbLiveExecutionBridgeGateFactState
    gks: BnbLiveExecutionBridgeGateFactState
    account_facts: BnbLiveExecutionBridgeGateFactState
    market_metadata: BnbLiveExecutionBridgeGateFactState
    protection_readiness: BnbLiveExecutionBridgeGateFactState
    recording_readiness: BnbLiveExecutionBridgeGateFactState
    bnb_position: BnbLiveExecutionBridgeGateFactState
    bnb_open_order: BnbLiveExecutionBridgeGateFactState
    persistence_readiness: BnbLiveExecutionBridgePersistenceReadiness
    execution_boundary_status: BridgeStatus
    no_order_created: Literal[True] = True
    no_executable_execution_intent_created: Literal[True] = True
    no_permission_granted: Literal[True] = True


class BnbOwnerExecutionTriggerReadModel(BaseModel):
    """Owner-visible trigger readiness without performing execution."""

    label: Literal["执行这一次小额实盘试验"] = "执行这一次小额实盘试验"
    visible: bool
    enabled: bool = False
    status: Literal[
        "hidden_until_final_gate_clear",
        "blocked_execution_endpoint_not_available",
        "blocked_execution_readiness",
        "ready_for_owner_click",
    ]
    endpoint: str | None = None
    reason: str
    blockers: list[str] = Field(default_factory=list)
    creates_execution_intent_on_click: bool = False
    creates_order_on_click: bool = False
    order_permission_granted: Literal[False] = False
    exact_scope: dict[str, str] = Field(default_factory=dict)


class BnbLiveExecutionBridgeDryRunResponse(BaseModel):
    generated_from: Literal["bnb_live_execution_bridge_dry_run_v1"] = (
        "bnb_live_execution_bridge_dry_run_v1"
    )
    generated_at_ms: int
    carrier_id: str
    symbol: str
    side: Literal["long", "short"]
    bridge_status: BridgeStatus
    final_preflight_result: Literal["passed", "blocked"]
    hard_blockers: list[str] = Field(default_factory=list)
    authorization_state: BnbLiveExecutionBridgeAuthorizationState
    final_gate_read_model: BnbLiveExecutionBridgeFinalGateReadModel
    authorization_hard_blockers_snapshot: list[str] = Field(default_factory=list)
    acknowledged_strategy_warnings: list[str] = Field(default_factory=list)
    strategy_warnings_block_execution: Literal[False] = False
    owner_execution_trigger: BnbOwnerExecutionTriggerReadModel
    execution_plan_preview: BnbExecutionPlanPreview
    execution_boundary: dict[str, Any]
    table_audit: BnbLiveExecutionBridgeTableAudit
    environment_checks: dict[str, bool | str]
    preflight_fact_checks: dict[str, dict[str, Any]]
    non_permissions: dict[str, bool]
    dry_run_only: Literal[True] = True


class BnbLiveExecutionBridgeDryRunService:
    def __init__(
        self,
        *,
        owner_trial_flow_service: OwnerTrialFlowService,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        env: Mapping[str, str] | None = None,
        permission_mode: Literal["read_only_probe", "official_execute"] = "read_only_probe",
    ) -> None:
        self._owner_trial_flow_service = owner_trial_flow_service
        self._session_maker = session_maker or get_pg_session_maker()
        self._env = env or os.environ
        self._permission_mode = permission_mode

    async def run(
        self,
        request: BnbLiveExecutionBridgeDryRunRequest | None = None,
        *,
        fact_snapshot: TrialPreflightFactsSnapshot | None = None,
    ) -> BnbLiveExecutionBridgeDryRunResponse:
        request = request or BnbLiveExecutionBridgeDryRunRequest()
        hard_blockers: list[str] = []
        authorization_hard_blockers_snapshot: list[str] = []
        carrier = get_owner_action_carrier(request.carrier_id)
        try:
            current = await self._owner_trial_flow_service.current(carrier_id=request.carrier_id)
        except OwnerTrialFlowError as exc:
            hard_blockers.append(exc.code)
            current = None

        if carrier is None:
            hard_blockers.append("unsupported_carrier")
            carrier = get_owner_action_carrier(SUPPORTED_OWNER_TRIAL_CARRIER_ID)
        if carrier is not None:
            if request.symbol not in {carrier.symbol, carrier.runtime_symbol}:
                hard_blockers.append("symbol_mismatch")
            if request.side != carrier.side:
                hard_blockers.append("side_mismatch")
            if not _decimal_scope_equal(request.max_notional, carrier.max_notional):
                hard_blockers.append("cap_mismatch")
            if not _decimal_scope_equal(request.quantity, carrier.quantity):
                hard_blockers.append("quantity_mismatch")
            if not _decimal_scope_equal(request.leverage, carrier.leverage):
                hard_blockers.append("leverage_mismatch")
            if request.protection_plan_type != carrier.protection_plan_type:
                hard_blockers.append("protection_plan_mismatch")

        hard_blockers.extend(_fact_snapshot_scope_blockers(request, carrier, fact_snapshot))

        authorization = current.live_authorization if current is not None else None
        if authorization is None:
            hard_blockers.append("missing_explicit_owner_live_authorization")
        else:
            if authorization.carrier_id != request.carrier_id:
                hard_blockers.append("authorization_carrier_mismatch")
            carrier_symbols = {request.symbol}
            if carrier is not None:
                carrier_symbols.update({carrier.symbol, carrier.runtime_symbol})
            if authorization.symbol not in carrier_symbols:
                hard_blockers.append("authorization_symbol_mismatch")
            if authorization.side != request.side:
                hard_blockers.append("authorization_side_mismatch")
            if not _decimal_scope_equal(authorization.max_notional, request.max_notional):
                hard_blockers.append("authorization_cap_mismatch")
            if not _decimal_scope_equal(authorization.quantity, request.quantity):
                hard_blockers.append("authorization_quantity_mismatch")
            if not _decimal_scope_equal(authorization.leverage, request.leverage):
                hard_blockers.append("authorization_leverage_mismatch")
            if authorization.protection_plan_type != request.protection_plan_type:
                hard_blockers.append("authorization_protection_plan_mismatch")
            if not authorization.single_use:
                hard_blockers.append("authorization_not_single_use")
            if authorization.consumed:
                hard_blockers.append("authorization_already_consumed")
            if authorization.execution_intent_created or authorization.order_created:
                hard_blockers.append("authorization_already_executed")
            if (
                authorization.live_ready
                or authorization.order_permission_granted
                or authorization.execution_permission_granted
                or authorization.auto_execution_enabled
            ):
                hard_blockers.append("authorization_contains_executable_state")
            authorization_hard_blockers_snapshot = list(authorization.hard_blockers)

        if current is not None and current.unacknowledged_warnings:
            hard_blockers.append("strategy_warning_acknowledgement_incomplete")

        environment_checks = _environment_checks(self._env, permission_mode=self._permission_mode)
        hard_blockers.extend(
            code for code, ok in environment_checks.items() if isinstance(ok, bool) and not ok
        )

        fact_checks = _fact_checks(fact_snapshot)
        for fact_id, fact in fact_checks.items():
            if fact_id in CORE_FINAL_GATE_FACT_IDS:
                hard_blockers.extend(str(code) for code in fact.get("blockers", []))
        hard_blockers.extend(_fact_gate_blockers(fact_checks))

        table_audit = await self._audit_tables()
        if not table_audit.execution_intents:
            hard_blockers.append("execution_intents_table_missing")
        if not table_audit.orders:
            hard_blockers.append("orders_table_missing")
        if not table_audit.brc_execution_results:
            hard_blockers.append("result_logging_table_missing")

        hard_blockers = _dedupe(hard_blockers)
        order_result_logging_available = table_audit.orders and table_audit.brc_execution_results
        protection_executable = (
            carrier is not None
            and request.protection_plan_type == carrier.protection_plan_type
        )
        exit_cleanup_available = order_result_logging_available and protection_executable
        bridge_status: BridgeStatus = (
            "blocked_before_execution_boundary"
            if hard_blockers
            else "dry_run_reached_execution_boundary"
        )
        return BnbLiveExecutionBridgeDryRunResponse(
            generated_at_ms=int(time.time() * 1000),
            carrier_id=request.carrier_id,
            symbol=request.symbol,
            side=request.side,
            bridge_status=bridge_status,
            final_preflight_result="blocked" if hard_blockers else "passed",
            hard_blockers=hard_blockers,
            authorization_state=_authorization_state(authorization),
            final_gate_read_model=_final_gate_read_model(
                fact_checks=fact_checks,
                table_audit=table_audit,
                bridge_status=bridge_status,
                hard_blockers=hard_blockers,
            ),
            authorization_hard_blockers_snapshot=authorization_hard_blockers_snapshot,
            acknowledged_strategy_warnings=(
                current.acknowledged_warnings if current is not None else []
            ),
            owner_execution_trigger=_owner_execution_trigger_read_model(
                request=request,
                authorization=authorization,
                hard_blockers=hard_blockers,
            ),
            execution_plan_preview=_execution_plan_preview(
                request=request,
                authorization=authorization,
                hard_blockers=hard_blockers,
            ),
            execution_boundary={
                "would_create_execution_intent_if_all_gates_passed": False,
                "would_create_order": False,
                "order_path_enabled": False,
                "protection_executable": protection_executable,
                "exit_cleanup_available": exit_cleanup_available,
                "order_result_logging_available": order_result_logging_available,
                "boundary": "dry_run_preview_only",
                "reason": "This task verifies gates only; executable intent/order creation remains disabled.",
            },
            table_audit=table_audit,
            environment_checks=environment_checks,
            preflight_fact_checks=fact_checks,
            non_permissions={
                "live_ready": False,
                "execution_permission_granted": False,
                "order_permission_granted": False,
                "execution_intent_created": False,
                "order_created": False,
                "runtime_started": False,
                "exchange_write_api_called": False,
            },
        )

    async def run_action_spec(
        self,
        action_spec: GenericActionSpec,
        *,
        fact_snapshot: TrialPreflightFactsSnapshot | None = None,
    ) -> BnbLiveExecutionBridgeDryRunResponse:
        request, spec_blockers = _request_from_generic_action_spec(action_spec)
        response = await self.run(request, fact_snapshot=fact_snapshot)
        action_spec_fact_blockers = _generic_action_spec_fact_blockers(
            action_spec,
            response.preflight_fact_checks,
        )
        blockers = _dedupe([*spec_blockers, *action_spec_fact_blockers])
        if not blockers:
            return response
        hard_blockers = _dedupe([*blockers, *response.hard_blockers])
        return response.model_copy(
            update={
                "bridge_status": "blocked_before_execution_boundary",
                "final_preflight_result": "blocked",
                "hard_blockers": hard_blockers,
                "final_gate_read_model": response.final_gate_read_model.model_copy(
                    update={
                        "result": "blocked",
                        "exact_blockers": hard_blockers,
                        "execution_boundary_status": "blocked_before_execution_boundary",
                    }
                ),
                "owner_execution_trigger": response.owner_execution_trigger.model_copy(
                    update={
                        "visible": False,
                        "enabled": False,
                        "status": "hidden_until_final_gate_clear",
                        "reason": "GenericActionSpec failed final gate validation.",
                        "blockers": hard_blockers,
                        "creates_execution_intent_on_click": False,
                        "creates_order_on_click": False,
                    }
                ),
                "execution_plan_preview": response.execution_plan_preview.model_copy(
                    update={
                        "status": (
                            "preview_unavailable_invalid_scope"
                            if _has_scope_blocker(hard_blockers)
                            else "preview_blocked_by_hard_gates"
                        ),
                        "exact_blockers": hard_blockers,
                    }
                ),
            }
        )

    async def _audit_tables(self) -> BnbLiveExecutionBridgeTableAudit:
        async with self._session_maker() as session:
            bind = session.get_bind()
            dialect_name = bind.dialect.name if bind is not None else ""
            if dialect_name == "sqlite":
                names = await session.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name IN "
                        "('execution_intents', 'orders', 'brc_execution_results')"
                    )
                )
                existing = set(names.scalars().all())
            else:
                existing = set()
                for table_name in ["execution_intents", "orders", "brc_execution_results"]:
                    result = await session.execute(
                        text("SELECT to_regclass(:name)"),
                        {"name": f"public.{table_name}"},
                    )
                    if result.scalar() is not None:
                        existing.add(table_name)
        return BnbLiveExecutionBridgeTableAudit(
            execution_intents="execution_intents" in existing,
            orders="orders" in existing,
            brc_execution_results="brc_execution_results" in existing,
        )


def _environment_checks(
    env: Mapping[str, str],
    *,
    permission_mode: Literal["read_only_probe", "official_execute"] = "read_only_probe",
) -> dict[str, bool | str]:
    trading_env = str(env.get("TRADING_ENV", "")).lower()
    exchange_testnet = str(env.get("EXCHANGE_TESTNET", "")).lower()
    runtime_control = str(env.get("RUNTIME_CONTROL_API_ENABLED", "false")).lower()
    test_injection = str(env.get("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")).lower()
    permission_max = str(env.get("BRC_EXECUTION_PERMISSION_MAX", "read_only")).lower()
    permission_safe = (
        permission_max == "order_allowed"
        if permission_mode == "official_execute"
        else permission_max != "order_allowed"
    )
    return {
        "live_environment_valid": trading_env == "live",
        "exchange_testnet_false": exchange_testnet == "false",
        "runtime_control_disabled": runtime_control not in {"1", "true", "yes", "on"},
        "test_signal_injection_disabled": test_injection not in {"1", "true", "yes", "on"},
        "global_permission_not_order_allowed": permission_safe,
        "global_permission_not_execution_intent_allowed": permission_max != "execution_intent_allowed",
        "TRADING_ENV": trading_env or "unset",
        "EXCHANGE_TESTNET": exchange_testnet or "unset",
        "BRC_EXECUTION_PERMISSION_MAX": permission_max or "unset",
        "permission_mode": permission_mode,
    }


def _request_from_generic_action_spec(
    action_spec: GenericActionSpec,
) -> tuple[BnbLiveExecutionBridgeDryRunRequest, list[str]]:
    blockers: list[str] = []
    carrier = get_owner_action_carrier(action_spec.carrier_id or "")
    if action_spec.status != "valid_blocked_final_gate":
        blockers.append("generic_action_spec_status_not_final_gate_ready")
    if not action_spec.action_registry_supported:
        blockers.append("generic_action_spec_not_action_registry_supported")
    if carrier is None:
        blockers.append("unsupported_carrier")
    required_values = {
        "carrier_id": action_spec.carrier_id,
        "symbol": action_spec.symbol,
        "side": action_spec.side,
        "quantity": action_spec.quantity,
        "max_notional": action_spec.max_notional,
        "leverage": action_spec.leverage,
        "protection_mode": action_spec.protection_mode,
    }
    missing = [field for field, value in required_values.items() if value in (None, "")]
    blockers.extend(f"generic_action_spec_{field}_missing" for field in missing)
    protection_plan_type = str(action_spec.protection_mode or "single_tp_plus_sl")
    if protection_plan_type != "single_tp_plus_sl":
        blockers.append("generic_action_spec_protection_plan_mismatch")
        protection_plan_type = "single_tp_plus_sl"

    return (
        BnbLiveExecutionBridgeDryRunRequest(
            carrier_id=str(action_spec.carrier_id or ""),
            symbol=str(action_spec.symbol or ""),
            side=_request_side(action_spec.side),
            max_notional=_request_decimal(action_spec.max_notional, "0.00000001"),
            quantity=_request_decimal(action_spec.quantity, "0.00000001"),
            leverage=_request_decimal(action_spec.leverage, "0.00000001"),
            protection_plan_type=protection_plan_type,
        ),
        _dedupe(blockers),
    )


def _request_side(value: str | None) -> Literal["long", "short"]:
    return "short" if str(value or "").lower() == "short" else "long"


def _request_decimal(value: object, fallback: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(fallback)


def _fact_snapshot_scope_blockers(
    request: BnbLiveExecutionBridgeDryRunRequest,
    carrier: Any | None,
    fact_snapshot: TrialPreflightFactsSnapshot | None,
) -> list[str]:
    if fact_snapshot is None:
        return []
    blockers: list[str] = []
    symbols = {request.symbol}
    if carrier is not None:
        symbols.update({carrier.symbol, carrier.runtime_symbol})
    if fact_snapshot.symbol not in symbols:
        blockers.append("preflight_fact_symbol_mismatch")
    if str(fact_snapshot.side).lower() != request.side:
        blockers.append("preflight_fact_side_mismatch")
    if carrier is not None and fact_snapshot.candidate_id != carrier.carrier_id:
        blockers.append("preflight_fact_candidate_mismatch")
    return blockers


def _decimal_scope_equal(left: Decimal, right: Decimal) -> bool:
    return abs(Decimal(str(left)) - Decimal(str(right))) <= Decimal("0.000000000001")


def _fact_checks(
    snapshot: TrialPreflightFactsSnapshot | None,
) -> dict[str, dict[str, Any]]:
    if snapshot is None:
        return {
            "preflight_facts": {
                "status": "unavailable",
                "blocking": True,
                "blockers": ["preflight_facts_unavailable"],
            }
        }
    checks: dict[str, dict[str, Any]] = {}
    for fact in snapshot.facts:
        checks[fact.fact_id] = {
            "status": fact.status,
            "blocking": fact.blocking,
            "blocker": fact.blocker,
            "blockers": fact.blockers or ([fact.blocker] if fact.blocker else []),
            "source": fact.source,
            "evidence": fact.evidence,
        }
    return checks


def _authorization_state(authorization: Any | None) -> BnbLiveExecutionBridgeAuthorizationState:
    if authorization is None:
        return BnbLiveExecutionBridgeAuthorizationState(
            exists=False,
            status="missing_explicit_owner_live_authorization",
            live_authorized=False,
            single_use=False,
            unconsumed=False,
        )
    return BnbLiveExecutionBridgeAuthorizationState(
        exists=True,
        status=str(authorization.status),
        live_authorized=bool(authorization.live_authorized),
        single_use=bool(authorization.single_use),
        unconsumed=not bool(authorization.consumed),
    )


def _final_gate_read_model(
    *,
    fact_checks: dict[str, dict[str, Any]],
    table_audit: BnbLiveExecutionBridgeTableAudit,
    bridge_status: BridgeStatus,
    hard_blockers: list[str],
) -> BnbLiveExecutionBridgeFinalGateReadModel:
    startup_guard = _gate_fact_state(fact_checks, "startup_guard")
    gks = _gate_fact_state(fact_checks, "gks")
    return BnbLiveExecutionBridgeFinalGateReadModel(
        result="blocked" if hard_blockers else "passed",
        exact_blockers=hard_blockers,
        runtime_safety_state=_runtime_safety_state(startup_guard, gks),
        startup_guard=startup_guard,
        gks=gks,
        account_facts=_gate_fact_state(fact_checks, "account_facts"),
        market_metadata=_gate_fact_state(fact_checks, "market_metadata"),
        protection_readiness=_gate_fact_state(fact_checks, "protection_readiness"),
        recording_readiness=_gate_fact_state(fact_checks, "recording_readiness"),
        bnb_position=_gate_fact_state(fact_checks, "active_position"),
        bnb_open_order=_gate_fact_state(fact_checks, "open_order"),
        persistence_readiness=BnbLiveExecutionBridgePersistenceReadiness(
            execution_intents=table_audit.execution_intents,
            orders=table_audit.orders,
            result_review_logging=table_audit.brc_execution_results,
        ),
        execution_boundary_status=bridge_status,
    )


def _execution_plan_preview(
    *,
    request: BnbLiveExecutionBridgeDryRunRequest,
    authorization: Any | None,
    hard_blockers: list[str],
) -> BnbExecutionPlanPreview:
    status: PlanPreviewStatus = (
        "preview_unavailable_invalid_scope"
        if _has_scope_blocker(hard_blockers)
        else "preview_blocked_by_hard_gates"
        if hard_blockers
        else "preview_ready"
    )
    return BnbExecutionPlanPreview(
        status=status,
        authorization_id=getattr(authorization, "authorization_id", None),
        draft_id=getattr(authorization, "draft_id", None),
        carrier_id=request.carrier_id,
        symbol=request.symbol,
        side=request.side,
        max_notional=request.max_notional,
        quantity=request.quantity,
        leverage=request.leverage,
        entry_order=BnbExecutionPlanEntryOrderPreview(
            order_type="market",
            intended_behavior=(
                "one-shot BNB entry only after explicit Owner authorization and final hard gates; "
                "this preview creates no execution intent or order"
            ),
            quantity=request.quantity,
            max_notional=request.max_notional,
            leverage=request.leverage,
        ),
        protection_plan=BnbExecutionPlanProtectionPreview(
            plan_type="single_tp_plus_sl",
            take_profit_quantity=request.quantity,
            stop_loss_quantity=request.quantity,
            safety_assumptions=[
                "single TP and SL cover the full preview entry quantity",
                "protection attach failure must stop/record/review before any further action",
                "preview does not reserve balance and does not grant order permission",
            ],
        ),
        expected_record_path=[
            "pg_execution_intents_non_preview_only_after_separate_executable_authorization",
            "pg_orders_after_exchange_write_boundary_only",
            "pg_brc_execution_results",
            "owner_review_record",
        ],
        expected_review_state="pending_owner_review_after_execution_result",
        cleanup_behavior_if_protection_attach_fails=(
            "record failed protection attach, block further order action, require owner review and cleanup path"
        ),
        exact_blockers=hard_blockers,
    )


def _owner_execution_trigger_read_model(
    *,
    request: BnbLiveExecutionBridgeDryRunRequest,
    authorization: Any,
    hard_blockers: list[str],
) -> BnbOwnerExecutionTriggerReadModel:
    final_gate_clear = not hard_blockers and authorization is not None
    exact_scope = {
        "carrier_id": request.carrier_id,
        "symbol": request.symbol,
        "side": request.side,
        "quantity": str(request.quantity),
        "max_notional": str(request.max_notional),
        "leverage": str(request.leverage),
        "protection_plan_type": request.protection_plan_type,
    }
    if not final_gate_clear:
        return BnbOwnerExecutionTriggerReadModel(
            visible=False,
            status="hidden_until_final_gate_clear",
            reason="Owner execution trigger remains hidden until authorization and final hard gate are clear.",
            blockers=hard_blockers,
            exact_scope=exact_scope,
        )
    endpoint = (
        f"/api/brc/owner-trial-flow/authorizations/"
        f"{authorization.authorization_id}/execute"
    )
    return BnbOwnerExecutionTriggerReadModel(
        visible=True,
        enabled=True,
        status="ready_for_owner_click",
        endpoint=endpoint,
        reason=(
            "Owner can click this button to create one scoped ExecutionIntent, submit one real BNB "
            "entry order, and attach one TP plus one SL after the final hard gate is rechecked."
        ),
        blockers=[],
        creates_execution_intent_on_click=True,
        creates_order_on_click=True,
        exact_scope=exact_scope,
    )


def _has_scope_blocker(hard_blockers: list[str]) -> bool:
    scope_blockers = {
        "unsupported_carrier",
        "symbol_mismatch",
        "side_mismatch",
        "cap_mismatch",
        "quantity_mismatch",
        "leverage_mismatch",
        "protection_plan_mismatch",
        "authorization_carrier_mismatch",
        "authorization_symbol_mismatch",
        "authorization_side_mismatch",
        "authorization_cap_mismatch",
        "authorization_quantity_mismatch",
        "authorization_leverage_mismatch",
        "authorization_protection_plan_mismatch",
        "preflight_fact_symbol_mismatch",
        "preflight_fact_side_mismatch",
        "preflight_fact_candidate_mismatch",
        "generic_action_spec_carrier_id_missing",
        "generic_action_spec_symbol_missing",
        "generic_action_spec_side_missing",
        "generic_action_spec_quantity_missing",
        "generic_action_spec_max_notional_missing",
        "generic_action_spec_leverage_missing",
        "generic_action_spec_protection_mode_missing",
        "generic_action_spec_protection_plan_mismatch",
        "generic_action_spec_below_min_notional",
        "generic_action_spec_below_min_amount",
        "generic_action_spec_quantity_step_mismatch",
    }
    return any(
        blocker in scope_blockers or blocker.startswith("market_metadata_")
        for blocker in hard_blockers
    )


def _gate_fact_state(
    fact_checks: dict[str, dict[str, Any]],
    fact_id: str,
) -> BnbLiveExecutionBridgeGateFactState:
    fact = fact_checks.get(fact_id)
    if fact is None:
        return BnbLiveExecutionBridgeGateFactState(
            state="missing",
            status="missing",
            source="not_supplied",
            blockers=[f"{fact_id}_fact_missing"],
        )
    blockers = [str(code) for code in fact.get("blockers", [])]
    evidence = dict(fact.get("evidence") or {})
    status = str(fact.get("status") or "unknown")
    state = _gate_state_name(fact_id, status, evidence, blockers)
    return BnbLiveExecutionBridgeGateFactState(
        state=state,
        status=status,
        source=str(fact.get("source") or "unknown"),
        blockers=blockers,
        evidence=evidence,
    )


def _gate_state_name(
    fact_id: str,
    status: str,
    evidence: dict[str, Any],
    blockers: list[str],
) -> str:
    if fact_id == "startup_guard":
        scoped_context_bound = evidence.get("runtime_safety_context_bound") is True
        if (
            evidence.get("runtime_started") is False
            and not scoped_context_bound
        ) or evidence.get("runtime_state") in {
            "not_started",
            "stopped",
        }:
            return "not_started"
        if evidence.get("armed") is False:
            return "not_armed"
        if status == "unavailable":
            return "unavailable"
        if blockers or status in {"blocked", "failed"}:
            return "blocked"
    if status == "unavailable":
        return "unavailable"
    if fact_id == "gks" and evidence.get("active") is True:
        return "blocked"
    if fact_id == "account_facts":
        if evidence.get("freshness") != "fresh":
            return "stale"
        if evidence.get("read_only_guarantee") is not True:
            return "blocked"
    if fact_id == "active_position" and _int_from_mapping(evidence, "active_position_count") not in {None, 0}:
        return "conflict"
    if fact_id == "open_order" and _int_from_mapping(evidence, "open_order_count") not in {None, 0}:
        return "conflict"
    if status == "clear" and not blockers:
        return "clear"
    if blockers or status in {"blocked", "failed"}:
        return "blocked"
    return status or "unknown"


def _runtime_safety_state(
    startup_guard: BnbLiveExecutionBridgeGateFactState,
    gks: BnbLiveExecutionBridgeGateFactState,
) -> str:
    if startup_guard.state != "clear":
        return f"startup_guard_{startup_guard.state}"
    if gks.state != "clear":
        return f"gks_{gks.state}"
    return "clear"


def _fact_gate_blockers(fact_checks: dict[str, dict[str, Any]]) -> list[str]:
    if "preflight_facts" in fact_checks:
        return []

    blockers: list[str] = []
    required_facts = ["active_position", "open_order", "gks", "startup_guard", "account_facts"]
    for fact_id in required_facts:
        if fact_id not in fact_checks:
            blockers.append(f"{fact_id}_fact_missing")

    active_position = fact_checks.get("active_position")
    if active_position is not None:
        blockers.extend(_status_blockers(active_position, "active_position"))
        count = _int_evidence(active_position, "active_position_count")
        if count is not None and count > 0:
            blockers.append("active_position_conflict")

    open_order = fact_checks.get("open_order")
    if open_order is not None:
        blockers.extend(_status_blockers(open_order, "open_order"))
        count = _int_evidence(open_order, "open_order_count")
        if count is not None and count > 0:
            blockers.append("open_order_conflict")

    gks = fact_checks.get("gks")
    if gks is not None:
        blockers.extend(_status_blockers(gks, "gks"))
        if _bool_evidence(gks, "active") is True:
            blockers.append("gks_active")

    startup_guard = fact_checks.get("startup_guard")
    if startup_guard is not None:
        blockers.extend(_status_blockers(startup_guard, "startup_guard"))

    account_facts = fact_checks.get("account_facts")
    if account_facts is not None:
        blockers.extend(_status_blockers(account_facts, "account_facts"))
        evidence = account_facts.get("evidence") or {}
        if evidence.get("freshness") != "fresh":
            blockers.append("account_facts_not_fresh")
        if evidence.get("read_only_guarantee") is not True:
            blockers.append("account_facts_read_only_unverified")
    startup_guard = fact_checks.get("startup_guard")
    if startup_guard is not None and _bool_evidence(startup_guard, "armed") is False:
        blockers.append("startup_guard_not_armed")
    if startup_guard is not None and (
        (
            _bool_evidence(startup_guard, "runtime_started") is False
            and _bool_evidence(startup_guard, "runtime_safety_context_bound") is not True
        )
        or (startup_guard.get("evidence") or {}).get("runtime_state") in {"not_started", "stopped"}
    ):
        blockers.append("startup_guard_not_started")

    return blockers


def _generic_action_spec_fact_blockers(
    action_spec: GenericActionSpec,
    fact_checks: dict[str, dict[str, Any]],
) -> list[str]:
    if "preflight_facts" in fact_checks:
        return []

    blockers: list[str] = []
    market_metadata = fact_checks.get("market_metadata")
    if market_metadata is None:
        blockers.append("market_metadata_fact_missing")
    else:
        blockers.extend(_action_spec_fact_status_blockers(market_metadata, "market_metadata"))
        evidence = market_metadata.get("evidence") or {}

        metadata_symbol = str(evidence.get("symbol") or "")
        if metadata_symbol and action_spec.symbol and metadata_symbol != action_spec.symbol:
            blockers.append("market_metadata_symbol_mismatch")
        if evidence.get("read_only_guarantee") is not True:
            blockers.append("market_metadata_read_only_unverified")

        min_notional = _decimal_from_mapping(evidence, "min_notional")
        min_amount = _decimal_from_mapping(evidence, "min_amount")
        amount_step = _decimal_from_mapping(evidence, "amount_step")
        tick_size = _decimal_from_mapping(evidence, "tick_size")
        price_precision = evidence.get("price_precision")
        quantity = _decimal_from_value(action_spec.quantity)
        max_notional = _decimal_from_value(action_spec.max_notional)

        if min_notional is None:
            blockers.append("market_metadata_min_notional_missing")
        elif max_notional is not None and max_notional < min_notional:
            blockers.append("generic_action_spec_below_min_notional")

        if min_amount is None:
            blockers.append("market_metadata_min_amount_missing")
        elif quantity is not None and quantity < min_amount:
            blockers.append("generic_action_spec_below_min_amount")

        if amount_step is None:
            blockers.append("market_metadata_amount_step_missing")
        elif (
            quantity is not None
            and amount_step > 0
            and not _decimal_step_aligned(quantity, amount_step)
        ):
            blockers.append("generic_action_spec_quantity_step_mismatch")

        if tick_size is None and price_precision in (None, ""):
            blockers.append("market_metadata_price_precision_missing")

    for fact_id in ["protection_readiness", "recording_readiness"]:
        fact = fact_checks.get(fact_id)
        if fact is None:
            blockers.append(f"{fact_id}_fact_missing")
            continue
        blockers.extend(_action_spec_fact_status_blockers(fact, fact_id))
        if fact_id == "protection_readiness":
            blockers.extend(_protection_readiness_evidence_blockers(fact))
        if fact_id == "recording_readiness":
            blockers.extend(_recording_readiness_evidence_blockers(fact))

    return _dedupe(blockers)


def _protection_readiness_evidence_blockers(fact: dict[str, Any]) -> list[str]:
    evidence = fact.get("evidence") or {}
    blockers: list[str] = []
    if evidence.get("protection_plan_type") != "single_tp_plus_sl":
        blockers.append("protection_plan_type_unsupported")
    if evidence.get("tp_ready") is not True:
        blockers.append("take_profit_readiness_missing")
    if evidence.get("sl_ready") is not True:
        blockers.append("stop_loss_readiness_missing")
    if evidence.get("price_source_ready") is not True:
        blockers.append("protection_price_source_missing")
    if evidence.get("read_only_guarantee") is not True:
        blockers.append("protection_readiness_read_only_unverified")
    return blockers


def _recording_readiness_evidence_blockers(fact: dict[str, Any]) -> list[str]:
    evidence = fact.get("evidence") or {}
    blockers: list[str] = []
    if evidence.get("execution_intents_writable") is not True:
        blockers.append("execution_intents_write_unavailable")
    if evidence.get("orders_writable") is not True:
        blockers.append("orders_write_unavailable")
    if evidence.get("review_writable") is not True:
        blockers.append("review_write_unavailable")
    if evidence.get("audit_writable") is not True:
        blockers.append("audit_write_unavailable")
    if evidence.get("read_only_check") is not True:
        blockers.append("recording_readiness_check_not_read_only")
    return blockers


def _action_spec_fact_status_blockers(fact: dict[str, Any], fact_id: str) -> list[str]:
    blockers = [str(code) for code in fact.get("blockers", [])]
    if blockers:
        return blockers
    return _status_blockers(fact, fact_id)


def _status_blockers(fact: dict[str, Any], fact_id: str) -> list[str]:
    if fact.get("status") == "clear":
        return []
    if fact.get("blockers"):
        return []
    status = str(fact.get("status") or "unknown")
    return [f"{fact_id}_status_{status}"]


def _int_evidence(fact: dict[str, Any], key: str) -> int | None:
    evidence = fact.get("evidence") or {}
    return _int_from_mapping(evidence, key)


def _int_from_mapping(evidence: Mapping[str, Any], key: str) -> int | None:
    value = evidence.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_evidence(fact: dict[str, Any], key: str) -> bool | None:
    evidence = fact.get("evidence") or {}
    value = evidence.get(key)
    return value if isinstance(value, bool) else None


def _decimal_from_mapping(evidence: Mapping[str, Any], key: str) -> Decimal | None:
    return _decimal_from_value(evidence.get(key))


def _decimal_from_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        decimal = Decimal(str(value))
    except Exception:
        return None
    return decimal if decimal > 0 else None


def _decimal_step_aligned(value: Decimal, step: Decimal) -> bool:
    units = value / step
    return abs(units - units.to_integral_value()) <= Decimal("0.000000000001")


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
