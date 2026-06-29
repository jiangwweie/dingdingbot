"""Owner-operated bounded live-trial execution chain.

This module owns the generic authorization-driven execution boundary. Adapter
registration is deliberately narrow and driven by the Owner action-carrier
catalog.
"""

from __future__ import annotations

import time
import uuid
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.bnb_live_execution_boundary import (
    BnbLiveExecutionBoundaryDryRunResponse,
    BnbLiveExecutionBoundaryDryRunService,
)
from src.application.owner_action_carrier_catalog import (
    get_owner_action_carrier,
    supported_owner_action_carrier_ids,
)
from src.application.owner_trial_flow import BoundedLiveTrialAuthorization
from src.application.production_strategy_family_admission import GenericActionSpec
from src.application.protection_price_planner import (
    ProtectionExchangeFilters,
    ProtectionPlannerService,
    ProtectionPricePlanRecord,
    ProtectionPriceSourceUnavailable,
)
from src.application.position_projection_service import PositionProjectionService
from src.application.strategy_trial_preflight_facts import TrialPreflightFactsSnapshot
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import (
    Direction,
    Order,
    OrderPlacementResult,
    OrderRole,
    OrderStatus,
    OrderStrategy,
    OrderType,
    SignalResult,
)
from src.infrastructure.database import get_pg_session_maker
from src.infrastructure.owner_trial_flow_repository import PgOwnerTrialFlowRepository
from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.logger import logger


OWNER_BOUNDED_EXECUTE_LABEL = "执行这一次小额实盘试验"
OWNER_BOUNDED_EXECUTE_ROUTE_TEMPLATE = (
    "/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
)


class OwnerBoundedExecutionError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        blockers: list[str] | None = None,
        *,
        execution_intent_created: bool = False,
        order_created: bool = False,
        order_permission_granted: bool = False,
        execution_intent_id: str | None = None,
        entry_order_id: str | None = None,
        entry_exchange_order_id: str | None = None,
        execution_intent_status: str | None = None,
        protection_status: str | None = None,
        tp_order_ids: list[str] | None = None,
        sl_order_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.blockers = blockers or [code]
        self.execution_intent_created = execution_intent_created
        self.order_created = order_created
        self.order_permission_granted = order_permission_granted
        self.execution_intent_id = execution_intent_id
        self.entry_order_id = entry_order_id
        self.entry_exchange_order_id = entry_exchange_order_id
        self.execution_intent_status = execution_intent_status
        self.protection_status = protection_status
        self.tp_order_ids = tp_order_ids or []
        self.sl_order_id = sl_order_id


class OwnerBoundedExecutionReadiness(BaseModel):
    authorization_id: str | None = None
    carrier_id: str | None = None
    supported: bool = False
    ready: bool = False
    blockers: list[str] = Field(default_factory=list)
    endpoint: str | None = None
    action_label: str = OWNER_BOUNDED_EXECUTE_LABEL
    creates_execution_intent_when_invoked: bool = False
    creates_order_when_invoked: bool = False
    order_permission_granted: bool = False


class OwnerBoundedExecutionState(BaseModel):
    authorization_id: str
    carrier_id: str | None = None
    retry_allowed: bool = False
    retry_reason: str | None = None
    retry_blockers: list[str] = Field(default_factory=list)
    execution_intent_count: int = 0
    local_order_count: int = 0
    result_count: int = 0
    execution_intents: list[dict[str, object]] = Field(default_factory=list)
    local_orders: list[dict[str, object]] = Field(default_factory=list)
    execution_results: list[dict[str, object]] = Field(default_factory=list)
    review_ledger: dict[str, object] = Field(default_factory=dict)
    safety: dict[str, bool] = Field(
        default_factory=lambda: {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "creates_order": False,
            "starts_runtime": False,
            "calls_exchange": False,
            "mutates_pg": False,
        }
    )


class OwnerBoundedExecutionResponse(BaseModel):
    generated_from: str = "owner_bounded_execution_v1"
    authorization_id: str
    carrier_id: str
    status: str
    final_gate_result: str
    blockers: list[str] = Field(default_factory=list)
    execution_intent_id: str | None = None
    entry_order_id: str | None = None
    entry_exchange_order_id: str | None = None
    tp_order_ids: list[str] = Field(default_factory=list)
    sl_order_id: str | None = None
    review_record_id: str | None = None
    execution_intent_status: str | None = None
    protection_status: str | None = None
    consumed: bool = False
    no_permission_granted: bool = True
    auto_execution_enabled: bool = False


class OwnerBoundedProtectionOrderResult(BaseModel):
    order_id: str
    exchange_order_id: str | None = None
    status: str


class OwnerBoundedEntryExecutionResult(BaseModel):
    execution_intent_id: str
    entry_order_id: str
    entry_exchange_order_id: str | None = None
    entry_status: str
    filled_qty: Decimal
    average_fill_price: Decimal | None = None
    tp_order: OwnerBoundedProtectionOrderResult
    sl_order: OwnerBoundedProtectionOrderResult
    review_record_id: str
    status: str = "executed"


class BoundedOrderExecutor(Protocol):
    async def submit_entry(
        self,
        *,
        authorization: BoundedLiveTrialAuthorization,
        client_order_id: str,
    ) -> OrderPlacementResult:
        ...

    async def submit_take_profit(
        self,
        *,
        authorization: BoundedLiveTrialAuthorization,
        protection_plan: ProtectionPricePlanRecord,
        client_order_id: str,
    ) -> OrderPlacementResult:
        ...

    async def submit_stop_loss(
        self,
        *,
        authorization: BoundedLiveTrialAuthorization,
        protection_plan: ProtectionPricePlanRecord,
        client_order_id: str,
    ) -> OrderPlacementResult:
        ...


class ExchangeGatewayBoundedOrderExecutor:
    def __init__(self, gateway: object | None) -> None:
        self._gateway = gateway

    @property
    def can_submit_orders(self) -> bool:
        return self._gateway is not None and hasattr(self._gateway, "place_order")

    async def submit_entry(
        self,
        *,
        authorization: BoundedLiveTrialAuthorization,
        client_order_id: str,
    ) -> OrderPlacementResult:
        if self._gateway is None or not hasattr(self._gateway, "place_order"):
            raise OwnerBoundedExecutionError(
                "entry_order_executor_unavailable",
                "Exchange gateway place_order is unavailable.",
            )
        return await self._gateway.place_order(
            symbol=authorization.symbol,
            order_type="market",
            side="buy" if authorization.side == "long" else "sell",
            amount=_catalog_authorized_quantity(authorization),
            position_side=_position_side_for_authorization(authorization),
            client_order_id=client_order_id,
        )

    async def submit_take_profit(
        self,
        *,
        authorization: BoundedLiveTrialAuthorization,
        protection_plan: ProtectionPricePlanRecord,
        client_order_id: str,
    ) -> OrderPlacementResult:
        if self._gateway is None or not hasattr(self._gateway, "place_order"):
            raise OwnerBoundedExecutionError(
                "tp_order_executor_unavailable",
                "Exchange gateway place_order is unavailable.",
            )
        if protection_plan.tp_price is None or protection_plan.tp_quantity is None:
            raise OwnerBoundedExecutionError("tp_plan_missing", "TP price/quantity missing.")
        return await self._gateway.place_order(
            symbol=authorization.symbol,
            order_type="limit",
            side="sell" if authorization.side == "long" else "buy",
            amount=protection_plan.tp_quantity,
            price=protection_plan.tp_price,
            reduce_only=True,
            position_side=_position_side_for_authorization(authorization),
            client_order_id=client_order_id,
        )

    async def submit_stop_loss(
        self,
        *,
        authorization: BoundedLiveTrialAuthorization,
        protection_plan: ProtectionPricePlanRecord,
        client_order_id: str,
    ) -> OrderPlacementResult:
        if self._gateway is None or not hasattr(self._gateway, "place_order"):
            raise OwnerBoundedExecutionError(
                "sl_order_executor_unavailable",
                "Exchange gateway place_order is unavailable.",
            )
        if protection_plan.sl_price is None or protection_plan.sl_quantity is None:
            raise OwnerBoundedExecutionError("sl_plan_missing", "SL price/quantity missing.")
        return await self._gateway.place_order(
            symbol=authorization.symbol,
            order_type="stop_market",
            side="sell" if authorization.side == "long" else "buy",
            amount=protection_plan.sl_quantity,
            trigger_price=protection_plan.sl_price,
            reduce_only=True,
            position_side=_position_side_for_authorization(authorization),
            client_order_id=client_order_id,
        )


class OwnerBoundedCarrierExecutionAdapter(Protocol):
    carrier_id: str

    def readiness(self, authorization: BoundedLiveTrialAuthorization) -> OwnerBoundedExecutionReadiness:
        ...

    async def execute(
        self,
        authorization: BoundedLiveTrialAuthorization,
        *,
        final_gate: BnbLiveExecutionBoundaryDryRunResponse,
        protection_plan: ProtectionPricePlanRecord,
        protection_planner_service: ProtectionPlannerService,
        executor: BoundedOrderExecutor,
        intent_repository: PgExecutionIntentRepository,
        order_repository: PgOrderRepository,
        position_projection_service: PositionProjectionService | None = None,
    ) -> OwnerBoundedExecutionResponse:
        ...


class OwnerBoundedExecutionRegistry:
    def __init__(self, adapters: list[OwnerBoundedCarrierExecutionAdapter]) -> None:
        self._adapters = {adapter.carrier_id: adapter for adapter in adapters}

    @property
    def supported_carrier_ids(self) -> list[str]:
        return sorted(self._adapters)

    def get(self, carrier_id: str) -> OwnerBoundedCarrierExecutionAdapter | None:
        return self._adapters.get(carrier_id)


@dataclass(frozen=True)
class OwnerCatalogExecutionAdapter:
    """Adapter for an exact-scope carrier in the Owner action catalog.

    The generic Owner-bounded execution service owns authorization, final-gate,
    duplicate, and persistence checks. This adapter remains strict about the
    exact catalog scope and reuses the common one-shot entry plus TP/SL flow.
    """

    carrier_id: str

    def readiness(self, authorization: BoundedLiveTrialAuthorization) -> OwnerBoundedExecutionReadiness:
        blockers = _catalog_scope_blockers(authorization)
        return OwnerBoundedExecutionReadiness(
            authorization_id=authorization.authorization_id,
            carrier_id=authorization.carrier_id,
            supported=not any(blocker.startswith("unsupported") for blocker in blockers),
            ready=not blockers,
            blockers=blockers,
            endpoint=OWNER_BOUNDED_EXECUTE_ROUTE_TEMPLATE.format(
                authorization_id=authorization.authorization_id,
            ),
            creates_execution_intent_when_invoked=not blockers,
            creates_order_when_invoked=not blockers,
            order_permission_granted=False,
        )

    async def execute(
        self,
        authorization: BoundedLiveTrialAuthorization,
        *,
        final_gate: BnbLiveExecutionBoundaryDryRunResponse,
        protection_plan: ProtectionPricePlanRecord,
        protection_planner_service: ProtectionPlannerService,
        executor: BoundedOrderExecutor,
        intent_repository: PgExecutionIntentRepository,
        order_repository: PgOrderRepository,
        position_projection_service: PositionProjectionService | None = None,
    ) -> OwnerBoundedExecutionResponse:
        readiness = self.readiness(authorization)
        if readiness.blockers:
            raise OwnerBoundedExecutionError(
                "adapter_not_executable",
                "Owner catalog adapter scope is not executable.",
                readiness.blockers,
            )
        result = await _execute_owner_catalog_one_shot(
            authorization=authorization,
            protection_plan=protection_plan,
            protection_planner_service=protection_planner_service,
            executor=executor,
            intent_repository=intent_repository,
            order_repository=order_repository,
            position_projection_service=position_projection_service,
        )
        return OwnerBoundedExecutionResponse(
            authorization_id=authorization.authorization_id,
            carrier_id=authorization.carrier_id,
            status=result.status,
            final_gate_result=final_gate.final_preflight_result,
            execution_intent_id=result.execution_intent_id,
            entry_order_id=result.entry_order_id,
            entry_exchange_order_id=result.entry_exchange_order_id,
            tp_order_ids=[result.tp_order.order_id] if result.tp_order.order_id else [],
            sl_order_id=result.sl_order.order_id or None,
            review_record_id=result.review_record_id,
            execution_intent_status=(
                ExecutionIntentStatus.COMPLETED.value
                if result.status == "executed"
                else ExecutionIntentStatus.SUBMITTED.value
            ),
            protection_status="protected" if result.status == "executed" else "not_complete",
            consumed=False,
            no_permission_granted=True,
            auto_execution_enabled=False,
        )


def default_owner_bounded_execution_registry() -> OwnerBoundedExecutionRegistry:
    return OwnerBoundedExecutionRegistry(
        [
            OwnerCatalogExecutionAdapter(carrier_id=carrier_id)
            for carrier_id in supported_owner_action_carrier_ids()
        ]
    )


def _generic_action_spec_from_authorization(
    authorization: BoundedLiveTrialAuthorization,
) -> GenericActionSpec:
    carrier = get_owner_action_carrier(authorization.carrier_id)
    return GenericActionSpec(
        family=(carrier.strategy_family if carrier is not None else authorization.carrier_id),
        strategy_family_id=(carrier.strategy_id if carrier is not None else authorization.strategy_family_id),
        carrier_id=authorization.carrier_id,
        admission_level="L3",
        status=(
            "valid_blocked_final_gate"
            if carrier is not None
            else "invalid_blocked"
        ),
        action_registry_supported=carrier is not None,
        symbol=authorization.symbol,
        side=authorization.side,
        quantity=str(authorization.quantity),
        max_notional=str(authorization.max_notional),
        leverage=str(authorization.leverage),
        max_attempts=1,
        protection_mode=authorization.protection_plan_type,
        review_requirement="post_action_review_required",
        hard_blockers=[] if carrier is not None else ["unsupported_carrier"],
        action_entry_payload_ref=f"action-entry:{authorization.carrier_id}",
    )


async def _execute_owner_catalog_one_shot(
    *,
    authorization: BoundedLiveTrialAuthorization,
    protection_plan: ProtectionPricePlanRecord,
    protection_planner_service: ProtectionPlannerService,
    executor: BoundedOrderExecutor,
    intent_repository: PgExecutionIntentRepository,
    order_repository: PgOrderRepository,
    position_projection_service: PositionProjectionService | None = None,
) -> OwnerBoundedEntryExecutionResult:
    intent = _build_execution_intent(authorization, protection_plan)
    await intent_repository.save(intent)

    entry_result = await executor.submit_entry(
        authorization=authorization,
        client_order_id=_client_order_id(authorization.authorization_id, "entry"),
    )
    entry_order = _order_from_placement(
        placement=entry_result,
        intent=intent,
        role=OrderRole.ENTRY,
        parent_order_id=None,
    )
    await order_repository.save(entry_order)
    if not entry_result.is_success:
        intent.status = ExecutionIntentStatus.FAILED
        intent.order_id = entry_order.id
        intent.exchange_order_id = entry_order.exchange_order_id
        intent.failed_reason = entry_result.error_code or "entry_order_failed"
        intent.updated_at = _now_ms()
        await intent_repository.update(intent)
        raise OwnerBoundedExecutionError(
            "entry_order_failed",
            entry_result.error_message or "Entry order submission failed.",
            [entry_result.error_code or "entry_order_failed"],
            execution_intent_created=True,
            order_created=bool(entry_order.exchange_order_id),
            execution_intent_id=intent.id,
            entry_order_id=entry_order.id,
            entry_exchange_order_id=entry_order.exchange_order_id,
            execution_intent_status=ExecutionIntentStatus.FAILED.value,
            protection_status="not_created",
        )

    filled_qty = entry_result.filled_qty or Decimal("0")
    if filled_qty <= Decimal("0") or entry_result.average_exec_price is None:
        intent.status = ExecutionIntentStatus.SUBMITTED
        intent.order_id = entry_order.id
        intent.exchange_order_id = entry_order.exchange_order_id
        intent.updated_at = _now_ms()
        await intent_repository.update(intent)
        return OwnerBoundedEntryExecutionResult(
            execution_intent_id=intent.id,
            entry_order_id=entry_order.id,
            entry_exchange_order_id=entry_order.exchange_order_id,
            entry_status=entry_order.status.value,
            filled_qty=filled_qty,
            average_fill_price=entry_result.average_exec_price,
            tp_order=OwnerBoundedProtectionOrderResult(order_id="", status="not_created"),
            sl_order=OwnerBoundedProtectionOrderResult(order_id="", status="not_created"),
            review_record_id=f"review-{authorization.authorization_id}",
            status="entry_submitted_pending_fill",
        )

    fill_plan = await protection_planner_service.create_fill_based_plan(
        authorization,
        fill_price=entry_result.average_exec_price,
        filters=_filters_from_plan(protection_plan),
        source_ref=f"entry_order:{entry_order.exchange_order_id or entry_order.id}:average_fill",
    )

    intent.status = ExecutionIntentStatus.PROTECTING
    intent.order_id = entry_order.id
    intent.exchange_order_id = entry_order.exchange_order_id
    intent.updated_at = _now_ms()
    await intent_repository.update(intent)

    try:
        tp_result = await executor.submit_take_profit(
            authorization=authorization,
            protection_plan=fill_plan,
            client_order_id=_client_order_id(authorization.authorization_id, "tp"),
        )
    except Exception as exc:
        reason = f"tp_order_submit_exception:{type(exc).__name__}"
        intent.status = ExecutionIntentStatus.PARTIALLY_PROTECTED
        intent.failed_reason = reason
        intent.updated_at = _now_ms()
        await intent_repository.update(intent)
        raise OwnerBoundedExecutionError(
            "protection_order_failed",
            "TP order submission failed after entry order.",
            _dedupe(
                [
                    "protection_attach_failed_after_entry_fill",
                    reason,
                    "manual_review_required_before_retry",
                ]
            ),
            execution_intent_created=True,
            order_created=True,
            execution_intent_id=intent.id,
            entry_order_id=entry_order.id,
            entry_exchange_order_id=entry_order.exchange_order_id,
            execution_intent_status=ExecutionIntentStatus.PARTIALLY_PROTECTED.value,
            protection_status="tp_submit_failed",
        ) from exc
    tp_order = _order_from_placement(
        placement=tp_result,
        intent=intent,
        role=OrderRole.TP1,
        parent_order_id=entry_order.id,
    )
    await order_repository.save(tp_order)

    try:
        sl_result = await executor.submit_stop_loss(
            authorization=authorization,
            protection_plan=fill_plan,
            client_order_id=_client_order_id(authorization.authorization_id, "sl"),
        )
    except Exception as exc:
        reason = f"sl_order_submit_exception:{type(exc).__name__}"
        intent.status = ExecutionIntentStatus.PARTIALLY_PROTECTED
        intent.failed_reason = reason
        intent.updated_at = _now_ms()
        await intent_repository.update(intent)
        raise OwnerBoundedExecutionError(
            "protection_order_failed",
            "SL order submission failed after entry order.",
            _dedupe(
                [
                    "protection_attach_failed_after_entry_fill",
                    reason,
                    "manual_review_required_before_retry",
                ]
            ),
            execution_intent_created=True,
            order_created=True,
            execution_intent_id=intent.id,
            entry_order_id=entry_order.id,
            entry_exchange_order_id=entry_order.exchange_order_id,
            execution_intent_status=ExecutionIntentStatus.PARTIALLY_PROTECTED.value,
            protection_status="sl_submit_failed",
            tp_order_ids=[tp_order.id],
        ) from exc
    sl_order = _order_from_placement(
        placement=sl_result,
        intent=intent,
        role=OrderRole.SL,
        parent_order_id=entry_order.id,
    )
    await order_repository.save(sl_order)

    failed_protection = [
        result.error_code or "protection_order_failed"
        for result in [tp_result, sl_result]
        if not result.is_success
    ]
    if failed_protection:
        intent.status = ExecutionIntentStatus.PARTIALLY_PROTECTED
        intent.failed_reason = ",".join(failed_protection)
        intent.updated_at = _now_ms()
        await intent_repository.update(intent)
        raise OwnerBoundedExecutionError(
            "protection_order_failed",
            "Protection order submission failed after entry order.",
            _dedupe(
                [
                    "protection_attach_failed_after_entry_fill",
                    *failed_protection,
                    "manual_review_required_before_retry",
                ]
            ),
            execution_intent_created=True,
            order_created=True,
            execution_intent_id=intent.id,
            entry_order_id=entry_order.id,
            entry_exchange_order_id=entry_order.exchange_order_id,
            execution_intent_status=ExecutionIntentStatus.PARTIALLY_PROTECTED.value,
            protection_status="partial_protection_failed",
            tp_order_ids=[tp_order.id],
            sl_order_id=sl_order.id,
        )

    await _project_owner_bounded_entry_position(position_projection_service, entry_order)

    intent.status = ExecutionIntentStatus.COMPLETED
    intent.updated_at = _now_ms()
    await intent_repository.update(intent)
    return OwnerBoundedEntryExecutionResult(
        execution_intent_id=intent.id,
        entry_order_id=entry_order.id,
        entry_exchange_order_id=entry_order.exchange_order_id,
        entry_status=entry_order.status.value,
        filled_qty=filled_qty,
        average_fill_price=entry_result.average_exec_price,
        tp_order=OwnerBoundedProtectionOrderResult(
            order_id=tp_order.id,
            exchange_order_id=tp_order.exchange_order_id,
            status=tp_order.status.value,
        ),
        sl_order=OwnerBoundedProtectionOrderResult(
            order_id=sl_order.id,
            exchange_order_id=sl_order.exchange_order_id,
            status=sl_order.status.value,
        ),
        review_record_id=f"review-{authorization.authorization_id}",
        status="executed",
    )


class OwnerBoundedExecutionService:
    def __init__(
        self,
        *,
        owner_trial_repository: PgOwnerTrialFlowRepository | None = None,
        final_gate_service: BnbLiveExecutionBoundaryDryRunService,
        registry: OwnerBoundedExecutionRegistry | None = None,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        protection_planner_service: ProtectionPlannerService | None = None,
        order_executor: BoundedOrderExecutor | None = None,
        intent_repository: PgExecutionIntentRepository | None = None,
        order_repository: PgOrderRepository | None = None,
        position_projection_service: PositionProjectionService | None = None,
    ) -> None:
        self._owner_trial_repository = owner_trial_repository or PgOwnerTrialFlowRepository(session_maker)
        self._final_gate_service = final_gate_service
        self._registry = registry or default_owner_bounded_execution_registry()
        self._session_maker = session_maker or get_pg_session_maker()
        self._protection_planner_service = protection_planner_service
        self._order_executor = order_executor
        self._intent_repository = intent_repository or PgExecutionIntentRepository(session_maker)
        self._order_repository = order_repository or PgOrderRepository(session_maker)
        self._position_projection_service = position_projection_service

    @property
    def registry(self) -> OwnerBoundedExecutionRegistry:
        return self._registry

    async def readiness(self, authorization_id: str) -> OwnerBoundedExecutionReadiness:
        authorization = await self._load_authorization(authorization_id)
        blockers = await self._pre_adapter_blockers(authorization)
        adapter = self._registry.get(authorization.carrier_id)
        if adapter is None:
            blockers.append("unsupported_carrier")
            return OwnerBoundedExecutionReadiness(
                authorization_id=authorization.authorization_id,
                carrier_id=authorization.carrier_id,
                supported=False,
                ready=False,
                blockers=blockers,
            )
        adapter_readiness = adapter.readiness(authorization)
        blockers.extend(adapter_readiness.blockers)
        return adapter_readiness.model_copy(
            update={
                "ready": not blockers,
                "blockers": _dedupe(blockers),
                "creates_execution_intent_when_invoked": not blockers,
                "creates_order_when_invoked": not blockers,
                "order_permission_granted": False,
            }
        )

    async def execution_state(self, authorization_id: str) -> OwnerBoundedExecutionState:
        authorization = await self._load_authorization(authorization_id)
        retry_classification = await self._execution_intent_retry_classification(
            authorization.authorization_id,
        )
        async with self._session_maker() as session:
            intents = await self._execution_intent_rows(session, authorization.authorization_id)
            local_orders = await self._local_order_rows_for_intents(session, intents)
            results = await self._execution_result_rows_for_authorization(
                session,
                authorization.authorization_id,
            )
        retry_blockers: list[str] = []
        if not bool(retry_classification.get("retry_allowed")):
            retry_blockers.append("duplicate_execution_intent_for_authorization")
            reason = retry_classification.get("reason")
            if reason and reason != "no_previous_intent":
                retry_blockers.append(str(reason))
            retry_blockers.extend(
                str(item)
                for item in retry_classification.get("blocking_reasons", [])  # type: ignore[union-attr]
                if str(item) not in retry_blockers
            )
        return OwnerBoundedExecutionState(
            authorization_id=authorization.authorization_id,
            carrier_id=authorization.carrier_id,
            retry_allowed=bool(retry_classification.get("retry_allowed")),
            retry_reason=str(retry_classification.get("reason") or ""),
            retry_blockers=_dedupe(retry_blockers),
            execution_intent_count=len(intents),
            local_order_count=len(local_orders),
            result_count=len(results),
            execution_intents=intents,
            local_orders=local_orders,
            execution_results=results,
            review_ledger=_build_owner_bounded_review_ledger(
                authorization=authorization,
                local_orders=local_orders,
                execution_results=results,
            ),
        )

    async def execute_authorization(
        self,
        authorization_id: str,
        *,
        operator_id: str,
        fact_snapshot: TrialPreflightFactsSnapshot | None = None,
    ) -> OwnerBoundedExecutionResponse:
        authorization = await self._load_authorization(authorization_id)
        blockers = await self._pre_adapter_blockers(authorization)
        adapter = self._registry.get(authorization.carrier_id)
        if adapter is None:
            blockers.append("unsupported_carrier")
        final_gate = await self._rerun_final_gate(authorization, fact_snapshot=fact_snapshot)
        if final_gate.final_preflight_result != "passed":
            blockers.extend(final_gate.hard_blockers or ["final_gate_blocked"])
        protection_blockers: list[str] = []
        protection_plan: ProtectionPricePlanRecord | None = None
        if adapter is not None and final_gate.final_preflight_result == "passed":
            protection_plan, protection_blockers = await self._protection_plan_readiness(authorization)
            blockers.extend(protection_blockers)
        if adapter is not None:
            adapter_readiness = adapter.readiness(authorization)
            order_executor_ready = (
                self._order_executor is not None
                and bool(getattr(self._order_executor, "can_submit_orders", True))
            )
            if not order_executor_ready and not protection_blockers and not adapter_readiness.blockers:
                blockers.append("entry_order_executor_not_enabled")
            blockers.extend(adapter_readiness.blockers)
        blockers = _dedupe(blockers)
        if blockers:
            if "duplicate_execution_intent_for_authorization" not in blockers:
                await self._assert_no_execution_state_created(authorization.authorization_id)
            raise OwnerBoundedExecutionError(
                "owner_bounded_execution_blocked",
                "Owner bounded execution is blocked before ExecutionIntent/order creation.",
                blockers,
            )
        assert adapter is not None
        assert protection_plan is not None
        assert self._order_executor is not None
        assert self._protection_planner_service is not None
        try:
            result = await adapter.execute(
                authorization,
                final_gate=final_gate,
                protection_plan=protection_plan,
                protection_planner_service=self._protection_planner_service,
                executor=self._order_executor,
                intent_repository=self._intent_repository,
                order_repository=self._order_repository,
                position_projection_service=self._position_projection_service,
            )
        except OwnerBoundedExecutionError as exc:
            if exc.execution_intent_created or exc.order_created:
                await self._record_execution_failure_result(
                    authorization=authorization,
                    exc=exc,
                    final_gate=final_gate,
                )
            raise
        consumed = result.status == "executed"
        if consumed:
            await self._owner_trial_repository.mark_live_authorization_consumed(
                authorization.authorization_id,
                occurred_at_ms=_now_ms(),
            )
        result = result.model_copy(update={"consumed": consumed})
        _ = operator_id
        await self._record_execution_result(authorization=authorization, result=result, final_gate=final_gate)
        return result

    async def _protection_plan_readiness(
        self,
        authorization: BoundedLiveTrialAuthorization,
    ) -> tuple[ProtectionPricePlanRecord | None, list[str]]:
        if self._protection_planner_service is None:
            return None, ["protection_price_source_missing"]
        try:
            plan = await self._protection_planner_service.ensure_pre_entry_plan(authorization)
        except ProtectionPriceSourceUnavailable as exc:
            return None, [str(exc) or "protection_price_source_missing"]
        except RuntimeError as exc:
            return None, [str(exc)]
        if plan.status != "valid":
            return plan, plan.blockers or ["protection_plan_blocked"]
        return plan, []

    async def _load_authorization(self, authorization_id: str) -> BoundedLiveTrialAuthorization:
        authorization = await self._owner_trial_repository.get_live_authorization(authorization_id)
        if authorization is None:
            raise OwnerBoundedExecutionError("authorization_not_found", "Owner live authorization not found.")
        return authorization

    async def _pre_adapter_blockers(self, authorization: BoundedLiveTrialAuthorization) -> list[str]:
        blockers: list[str] = []
        if authorization.consumed:
            blockers.append("authorization_already_consumed")
        if not authorization.single_use:
            blockers.append("authorization_not_single_use")
        if authorization.expires_at_ms is not None and authorization.expires_at_ms <= _now_ms():
            blockers.append("authorization_expired")
        link_state = await self._execution_intent_authorization_link_state()
        if link_state != "ready":
            blockers.append(link_state)
        else:
            retry_classification = await self._execution_intent_retry_classification(
                authorization.authorization_id,
            )
            if not retry_classification["retry_allowed"]:
                blockers.append("duplicate_execution_intent_for_authorization")
                reason = retry_classification.get("reason")
                if reason and reason != "no_previous_intent":
                    blockers.append(str(reason))
        return blockers

    async def _rerun_final_gate(
        self,
        authorization: BoundedLiveTrialAuthorization,
        *,
        fact_snapshot: TrialPreflightFactsSnapshot | None = None,
    ) -> BnbLiveExecutionBoundaryDryRunResponse:
        return await self._final_gate_service.run_action_spec(
            _generic_action_spec_from_authorization(authorization),
            fact_snapshot=fact_snapshot,
        )

    async def _execution_intent_authorization_link_state(self) -> str:
        async with self._session_maker() as session:
            bind = session.get_bind()
            dialect_name = bind.dialect.name if bind is not None else ""
            try:
                if dialect_name == "sqlite":
                    table_exists = await session.scalar(
                        text(
                            "SELECT count(*) FROM sqlite_master "
                            "WHERE type='table' AND name='execution_intents'"
                        )
                    )
                    if int(table_exists or 0) == 0:
                        return "execution_intents_table_missing"
                    columns = await session.execute(text("PRAGMA table_info(execution_intents)"))
                    if "authorization_id" not in {str(row[1]) for row in columns.fetchall()}:
                        return "execution_intents_authorization_link_missing"
                    return "ready"
                table_exists = await session.scalar(
                    text("SELECT to_regclass(:name)"),
                    {"name": "public.execution_intents"},
                )
                if table_exists is None:
                    return "execution_intents_table_missing"
                column_exists = await session.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'execution_intents'
                          AND column_name = 'authorization_id'
                        """
                    )
                )
                if int(column_exists or 0) == 0:
                    return "execution_intents_authorization_link_missing"
            except SQLAlchemyError:
                return "execution_intents_authorization_link_unavailable"
        return "ready"

    async def _execution_intent_rows(
        self,
        session: AsyncSession,
        authorization_id: str,
    ) -> list[dict[str, object]]:
        columns = await _table_columns(session, "execution_intents")
        if not columns:
            return []
        selectable = [
            column
            for column in [
                "id",
                "signal_id",
                "symbol",
                "status",
                "authorization_id",
                "order_id",
                "exchange_order_id",
                "failed_reason",
                "created_at",
                "updated_at",
            ]
            if column in columns
        ]
        if not selectable:
            return []
        order_clause = " ORDER BY created_at DESC" if "created_at" in columns else ""
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT {", ".join(selectable)}
                    FROM execution_intents
                    WHERE authorization_id = :authorization_id
                    {order_clause}
                    """
                ),
                {"authorization_id": authorization_id},
            )
        ).mappings().all()
        result: list[dict[str, object]] = []
        for row in rows:
            item = {key: row.get(key) for key in selectable}
            signal_id = str(row.get("signal_id") or "")
            item["local_order_count_for_signal"] = (
                await _local_order_count_for_signal(session, signal_id)
                if signal_id
                else 0
            )
            result.append(item)
        return result

    async def _local_order_rows_for_intents(
        self,
        session: AsyncSession,
        intents: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        columns = await _table_columns(session, "orders")
        if not columns:
            return []
        selectable = [
            column
            for column in [
                "id",
                "signal_id",
                "symbol",
                "status",
                "order_type",
                "exchange_order_id",
                "order_role",
                "requested_qty",
                "filled_qty",
                "average_exec_price",
                "reduce_only",
                "price",
                "trigger_price",
                "created_at",
                "updated_at",
            ]
            if column in columns
        ]
        if not selectable:
            return []
        order_ids = {
            str(intent.get("order_id"))
            for intent in intents
            if intent.get("order_id")
        }
        signal_ids = {
            str(intent.get("signal_id"))
            for intent in intents
            if intent.get("signal_id")
        }
        filters: list[str] = []
        params: dict[str, object] = {}
        if order_ids and "id" in columns:
            placeholders: list[str] = []
            for index, value in enumerate(sorted(order_ids)):
                key = f"order_id_{index}"
                placeholders.append(f":{key}")
                params[key] = value
            filters.append(f"id IN ({', '.join(placeholders)})")
        if signal_ids and "signal_id" in columns:
            placeholders = []
            for index, value in enumerate(sorted(signal_ids)):
                key = f"signal_id_{index}"
                placeholders.append(f":{key}")
                params[key] = value
            filters.append(f"signal_id IN ({', '.join(placeholders)})")
        if not filters:
            return []
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT {", ".join(selectable)}
                    FROM orders
                    WHERE {" OR ".join(filters)}
                    """
                ),
                params,
            )
        ).mappings().all()
        return [{key: row.get(key) for key in selectable} for row in rows]

    async def _execution_result_rows_for_authorization(
        self,
        session: AsyncSession,
        authorization_id: str,
    ) -> list[dict[str, object]]:
        columns = await _table_columns(session, "brc_execution_results")
        if not columns:
            return []
        selectable = [
            column
            for column in [
                "operation_id",
                "status",
                "failed_reason",
                "preflight_id",
                "occurred_at_ms",
            ]
            if column in columns
        ]
        if not selectable:
            return []
        filters = ["operation_id LIKE :operation_like"]
        params: dict[str, object] = {"operation_like": f"%{authorization_id}%"}
        if "audit_refs" in columns:
            filters.append("CAST(audit_refs AS TEXT) LIKE :authorization_like")
            params["authorization_like"] = f"%{authorization_id}%"
        if "result_summary" in columns:
            filters.append("CAST(result_summary AS TEXT) LIKE :authorization_like")
            params["authorization_like"] = f"%{authorization_id}%"
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT {", ".join(selectable)}
                    FROM brc_execution_results
                    WHERE {" OR ".join(filters)}
                    """
                ),
                params,
            )
        ).mappings().all()
        return [{key: row.get(key) for key in selectable} for row in rows]

    async def _has_execution_intent_for_authorization(self, authorization_id: str) -> bool:
        async with self._session_maker() as session:
            exists = await session.scalar(
                text(
                    "SELECT count(*) FROM execution_intents "
                    "WHERE authorization_id = :authorization_id"
                ),
                {"authorization_id": authorization_id},
            )
            return int(exists or 0) > 0

    async def _execution_intent_retry_classification(self, authorization_id: str) -> dict[str, object]:
        async with self._session_maker() as session:
            columns = await _table_columns(session, "execution_intents")
            if not columns:
                return {
                    "retry_allowed": False,
                    "reason": "execution_intents_table_missing",
                }
            optional_selects = {
                "order_id": "order_id" if "order_id" in columns else "NULL AS order_id",
                "exchange_order_id": (
                    "exchange_order_id" if "exchange_order_id" in columns else "NULL AS exchange_order_id"
                ),
                "failed_reason": "failed_reason" if "failed_reason" in columns else "NULL AS failed_reason",
            }
            rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT id, signal_id, status,
                               {optional_selects["order_id"]},
                               {optional_selects["exchange_order_id"]},
                               {optional_selects["failed_reason"]}
                        FROM execution_intents
                        WHERE authorization_id = :authorization_id
                        ORDER BY created_at DESC
                        """
                        if "created_at" in columns
                        else f"""
                        SELECT id, signal_id, status,
                               {optional_selects["order_id"]},
                               {optional_selects["exchange_order_id"]},
                               {optional_selects["failed_reason"]}
                        FROM execution_intents
                        WHERE authorization_id = :authorization_id
                        """
                    ),
                    {"authorization_id": authorization_id},
                )
            ).mappings().all()
            if not rows:
                return {
                    "retry_allowed": True,
                    "reason": "no_previous_intent",
                    "retryable_pre_order_failure": False,
                }
            retryable_intents: list[str] = []
            blocking_reasons: list[str] = []
            for row in rows:
                local_order_count = await _local_order_count_for_signal(session, str(row["signal_id"]))
                classification = _classify_previous_intent_for_retry(
                    intent_id=str(row["id"]),
                    status=str(row["status"]),
                    order_id=row["order_id"],
                    exchange_order_id=row["exchange_order_id"],
                    failed_reason=row["failed_reason"],
                    local_order_count=local_order_count,
                )
                if classification["retry_allowed"]:
                    retryable_intents.append(str(row["id"]))
                else:
                    blocking_reasons.append(str(classification["reason"]))
            if blocking_reasons:
                return {
                    "retry_allowed": False,
                    "reason": blocking_reasons[0],
                    "blocking_reasons": _dedupe(blocking_reasons),
                    "retryable_previous_intent_ids": retryable_intents,
                }
            return {
                "retry_allowed": True,
                "reason": "retryable_pre_order_failure",
                "failure_phase": "pre_order_rejected",
                "retryable_pre_order_failure": True,
                "previous_intent_id": retryable_intents[-1] if retryable_intents else None,
                "retryable_previous_intent_ids": retryable_intents,
            }

    async def _assert_no_execution_state_created(self, authorization_id: str) -> None:
        if await self._has_execution_intent_for_authorization(authorization_id):
            raise OwnerBoundedExecutionError(
                "execution_state_created_unexpectedly",
                "ExecutionIntent exists after a blocked owner bounded execution preflight.",
            )

    async def _record_execution_result(
        self,
        *,
        authorization: BoundedLiveTrialAuthorization,
        result: OwnerBoundedExecutionResponse,
        final_gate: BnbLiveExecutionBoundaryDryRunResponse,
    ) -> None:
        async with self._session_maker() as session:
            bind = session.get_bind()
            dialect_name = bind.dialect.name if bind is not None else ""
            try:
                if dialect_name == "sqlite":
                    columns_result = await session.execute(text("PRAGMA table_info(brc_execution_results)"))
                    columns = {str(row[1]) for row in columns_result.fetchall()}
                else:
                    rows = await session.execute(
                        text(
                            """
                            SELECT column_name
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'brc_execution_results'
                            """
                        )
                    )
                    columns = {str(row[0]) for row in rows.fetchall()}
                if {"operation_id", "status"} == columns:
                    await session.execute(
                        text(
                            "INSERT INTO brc_execution_results (operation_id, status) "
                            "VALUES (:operation_id, :status)"
                        ),
                        {
                            "operation_id": result.review_record_id or f"review-{authorization.authorization_id}",
                            "status": result.status,
                        },
                    )
                else:
                    json_cast = "JSONB" if dialect_name == "postgresql" else "TEXT"
                    await session.execute(
                        text(
                            f"""
                            INSERT INTO brc_execution_results (
                                operation_id, preflight_id, status, rechecked,
                                recheck_result, adapter_result, result_summary,
                                audit_refs, campaign_refs, review_refs,
                                final_state_snapshot, occurred_at_ms
                            )
                            VALUES (
                                :operation_id, :preflight_id, :status, :rechecked,
                                CAST(:recheck_result AS {json_cast}),
                                CAST(:adapter_result AS {json_cast}),
                                CAST(:result_summary AS {json_cast}),
                                CAST(:audit_refs AS {json_cast}),
                                CAST(:campaign_refs AS {json_cast}),
                                CAST(:review_refs AS {json_cast}),
                                CAST(:final_state_snapshot AS {json_cast}),
                                :occurred_at_ms
                            )
                            """
                        ),
                        {
                            "operation_id": result.review_record_id or f"review-{authorization.authorization_id}",
                            "preflight_id": f"final-gate-{authorization.authorization_id}",
                            "status": result.status if result.status in {"executed", "failed"} else "noop",
                            "rechecked": True,
                            "recheck_result": json.dumps(final_gate.model_dump(mode="json")),
                            "adapter_result": json.dumps(result.model_dump(mode="json")),
                            "result_summary": json.dumps({
                                "authorization_id": authorization.authorization_id,
                                "execution_intent_id": result.execution_intent_id,
                                "entry_order_id": result.entry_order_id,
                                "tp_order_ids": result.tp_order_ids,
                                "sl_order_id": result.sl_order_id,
                                "review_ledger": _build_owner_bounded_result_review_ledger(
                                    authorization=authorization,
                                    result=result,
                                    final_gate=final_gate,
                                ),
                            }),
                            "audit_refs": json.dumps([authorization.authorization_id, result.execution_intent_id]),
                            "campaign_refs": json.dumps([]),
                            "review_refs": json.dumps([result.review_record_id] if result.review_record_id else []),
                            "final_state_snapshot": json.dumps({"consumed": result.consumed}),
                            "occurred_at_ms": _now_ms(),
                        },
                    )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                raise OwnerBoundedExecutionError(
                    "execution_result_logging_failed",
                    "Execution result/review logging failed.",
                    ["execution_result_logging_failed"],
                ) from exc

    async def _record_execution_failure_result(
        self,
        *,
        authorization: BoundedLiveTrialAuthorization,
        exc: OwnerBoundedExecutionError,
        final_gate: BnbLiveExecutionBoundaryDryRunResponse,
    ) -> None:
        operation_id = (
            f"review-{authorization.authorization_id}-{exc.execution_intent_id}"
            if exc.execution_intent_id
            else f"review-{authorization.authorization_id}-failed"
        )
        async with self._session_maker() as session:
            bind = session.get_bind()
            dialect_name = bind.dialect.name if bind is not None else ""
            try:
                if dialect_name == "sqlite":
                    columns_result = await session.execute(text("PRAGMA table_info(brc_execution_results)"))
                    columns = {str(row[1]) for row in columns_result.fetchall()}
                else:
                    rows = await session.execute(
                        text(
                            """
                            SELECT column_name
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'brc_execution_results'
                            """
                        )
                    )
                    columns = {str(row[0]) for row in rows.fetchall()}
                if {"operation_id", "status"} == columns:
                    await session.execute(
                        text(
                            "INSERT INTO brc_execution_results (operation_id, status) "
                            "VALUES (:operation_id, :status)"
                        ),
                        {
                            "operation_id": operation_id,
                            "status": "failed",
                        },
                    )
                else:
                    json_cast = "JSONB" if dialect_name == "postgresql" else "TEXT"
                    adapter_result = {
                        "authorization_id": authorization.authorization_id,
                        "carrier_id": authorization.carrier_id,
                        "status": "failed",
                        "code": exc.code,
                        "blockers": exc.blockers,
                        "execution_intent_id": exc.execution_intent_id,
                        "entry_order_id": exc.entry_order_id,
                        "entry_exchange_order_id": exc.entry_exchange_order_id,
                        "tp_order_ids": exc.tp_order_ids,
                        "sl_order_id": exc.sl_order_id,
                        "execution_intent_status": exc.execution_intent_status,
                        "protection_status": exc.protection_status,
                        "consumed": False,
                        "no_permission_granted": True,
                        "auto_execution_enabled": False,
                    }
                    await session.execute(
                        text(
                            f"""
                            INSERT INTO brc_execution_results (
                                operation_id, preflight_id, status, rechecked,
                                recheck_result, adapter_result, failed_reason, result_summary,
                                audit_refs, campaign_refs, review_refs,
                                final_state_snapshot, occurred_at_ms
                            )
                            VALUES (
                                :operation_id, :preflight_id, :status, :rechecked,
                                CAST(:recheck_result AS {json_cast}),
                                CAST(:adapter_result AS {json_cast}),
                                :failed_reason,
                                CAST(:result_summary AS {json_cast}),
                                CAST(:audit_refs AS {json_cast}),
                                CAST(:campaign_refs AS {json_cast}),
                                CAST(:review_refs AS {json_cast}),
                                CAST(:final_state_snapshot AS {json_cast}),
                                :occurred_at_ms
                            )
                            """
                        ),
                        {
                            "operation_id": operation_id,
                            "preflight_id": f"final-gate-{authorization.authorization_id}",
                            "status": "failed",
                            "rechecked": True,
                            "recheck_result": json.dumps(final_gate.model_dump(mode="json")),
                            "adapter_result": json.dumps(adapter_result),
                            "failed_reason": exc.code,
                            "result_summary": json.dumps({
                                "authorization_id": authorization.authorization_id,
                                "execution_intent_id": exc.execution_intent_id,
                                "entry_order_id": exc.entry_order_id,
                                "tp_order_ids": exc.tp_order_ids,
                                "sl_order_id": exc.sl_order_id,
                                "protection_status": exc.protection_status,
                                "review_ledger": _build_owner_bounded_failure_review_ledger(
                                    authorization=authorization,
                                    exc=exc,
                                    final_gate=final_gate,
                                ),
                            }),
                            "audit_refs": json.dumps([authorization.authorization_id, exc.execution_intent_id]),
                            "campaign_refs": json.dumps([]),
                            "review_refs": json.dumps([operation_id]),
                            "final_state_snapshot": json.dumps({
                                "consumed": False,
                                "manual_review_required": True,
                                "protection_status": exc.protection_status,
                            }),
                            "occurred_at_ms": _now_ms(),
                        },
                    )
                await session.commit()
            except SQLAlchemyError as sql_exc:
                await session.rollback()
                raise OwnerBoundedExecutionError(
                    "execution_result_logging_failed",
                    "Execution failure result/review logging failed.",
                    ["execution_result_logging_failed"],
                ) from sql_exc


def _catalog_scope_blockers(authorization: BoundedLiveTrialAuthorization) -> list[str]:
    blockers: list[str] = []
    carrier = get_owner_action_carrier(authorization.carrier_id)
    if carrier is None:
        blockers.append("unsupported_carrier")
        return blockers
    if authorization.symbol != carrier.runtime_symbol:
        blockers.append("symbol_mismatch")
    if authorization.side != carrier.side:
        blockers.append("side_mismatch")
    if (
        getattr(carrier, "sizing_mode", "fixed_quantity") != "notional_derived"
        and not _decimal_scope_equal(authorization.quantity, carrier.quantity)
    ):
        blockers.append("quantity_mismatch")
    if getattr(carrier, "sizing_mode", "fixed_quantity") == "notional_derived":
        if authorization.max_notional > carrier.max_notional:
            blockers.append("cap_mismatch")
    elif not _decimal_scope_equal(authorization.max_notional, carrier.max_notional):
        blockers.append("cap_mismatch")
    if not _decimal_scope_equal(authorization.leverage, carrier.leverage):
        blockers.append("leverage_mismatch")
    if authorization.protection_plan_type != carrier.protection_plan_type:
        blockers.append("protection_plan_mismatch")
    return blockers


def _decimal_scope_equal(left: Decimal, right: Decimal) -> bool:
    return abs(Decimal(str(left)) - Decimal(str(right))) <= Decimal("0.000000000001")


def _catalog_authorized_quantity(authorization: BoundedLiveTrialAuthorization) -> Decimal:
    carrier = get_owner_action_carrier(authorization.carrier_id)
    if carrier is not None and _decimal_scope_equal(authorization.quantity, carrier.quantity):
        return carrier.quantity
    return authorization.quantity


def _build_execution_intent(
    authorization: BoundedLiveTrialAuthorization,
    protection_plan: ProtectionPricePlanRecord,
) -> ExecutionIntent:
    signal_id = f"owner-live-{authorization.authorization_id}"
    entry_price = protection_plan.reference_price or protection_plan.fill_price or Decimal("0")
    signal = SignalResult(
        symbol=authorization.symbol,
        timeframe="owner_one_shot",
        direction=_direction_for_authorization(authorization),
        entry_price=entry_price,
        suggested_stop_loss=protection_plan.sl_price or entry_price,
        suggested_position_size=_catalog_authorized_quantity(authorization),
        current_leverage=int(authorization.leverage),
        tags=[
            {"name": "carrier_id", "value": authorization.carrier_id},
            {"name": "authorization_id", "value": authorization.authorization_id},
            {"name": "execution_mode", "value": "owner_operated_one_shot"},
        ],
        risk_reward_info=(
            "Owner-authorized bounded live trial; "
            f"max notional {authorization.max_notional} USDT; {authorization.leverage}x."
        ),
        strategy_name=authorization.carrier_id,
        take_profit_levels=[
            {
                "id": "TP1",
                "position_ratio": "1",
                "risk_reward": "single_tp_plus_sl",
                "price": str(protection_plan.tp_price or ""),
            }
        ],
    )
    strategy = OrderStrategy(
        id=f"owner-bounded-{authorization.carrier_id}",
        name="Owner bounded single TP plus SL",
        tp_levels=1,
        tp_ratios=[Decimal("1")],
        tp_targets=[Decimal("1")],
        initial_stop_loss_rr=Decimal("-1"),
        trailing_stop_enabled=False,
        oco_enabled=False,
    )
    return ExecutionIntent(
        id=f"intent-{uuid.uuid4().hex}",
        signal_id=signal_id,
        signal=signal,
        status=ExecutionIntentStatus.PENDING,
        strategy=strategy,
        authorization_id=authorization.authorization_id,
    )


def _order_from_placement(
    *,
    placement: OrderPlacementResult,
    intent: ExecutionIntent,
    role: OrderRole,
    parent_order_id: str | None,
) -> Order:
    now = _now_ms()
    return Order(
        id=placement.order_id,
        signal_id=intent.signal_id,
        exchange_order_id=placement.exchange_order_id,
        symbol=placement.symbol,
        direction=placement.direction,
        order_type=placement.order_type,
        order_role=role,
        price=placement.price,
        trigger_price=placement.trigger_price,
        requested_qty=placement.amount,
        filled_qty=placement.filled_qty or Decimal("0"),
        average_exec_price=placement.average_exec_price,
        status=placement.status,
        created_at=placement.created_at or now,
        updated_at=now,
        reduce_only=placement.reduce_only,
        exchange_reduce_only_param_sent=placement.exchange_reduce_only_param_sent,
        exchange_reduce_only_omit_reason=placement.exchange_reduce_only_omit_reason,
        parent_order_id=parent_order_id,
    )


async def _project_owner_bounded_entry_position(
    position_projection_service: PositionProjectionService | None,
    entry_order: Order,
) -> None:
    if position_projection_service is None:
        return
    try:
        await position_projection_service.project_entry_fill(entry_order)
    except Exception as exc:
        logger.warning(
            "Owner-bounded entry position projection failed: "
            "order_id=%s signal_id=%s error=%s",
            entry_order.id,
            entry_order.signal_id,
            exc,
            exc_info=True,
        )


def _direction_for_authorization(authorization: BoundedLiveTrialAuthorization) -> Direction:
    return Direction.LONG if authorization.side == "long" else Direction.SHORT


def _position_side_for_authorization(authorization: BoundedLiveTrialAuthorization) -> str:
    return "LONG" if authorization.side == "long" else "SHORT"


def _filters_from_plan(plan: ProtectionPricePlanRecord) -> ProtectionExchangeFilters:
    return ProtectionExchangeFilters(
        min_amount=plan.min_amount,
        amount_step=plan.amount_step,
        min_notional=plan.min_notional,
        min_notional_source=plan.filters.get("min_notional_source") if plan.filters else None,
        tick_size=plan.tick_size,
    )


def _client_order_id(authorization_id: str, role: str) -> str:
    suffix = authorization_id.replace("-", "")[:18]
    return f"brc-{suffix}-{role}"


async def _table_columns(session: AsyncSession, table_name: str) -> set[str]:
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name == "sqlite":
        rows = await session.execute(text(f"PRAGMA table_info({table_name})"))
        return {str(row[1]) for row in rows.fetchall()}
    rows = await session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {str(row[0]) for row in rows.fetchall()}


async def _local_order_count_for_signal(session: AsyncSession, signal_id: str) -> int:
    order_columns = await _table_columns(session, "orders")
    if not order_columns or "signal_id" not in order_columns:
        return 0
    count = await session.scalar(
        text("SELECT count(*) FROM orders WHERE signal_id = :signal_id"),
        {"signal_id": signal_id},
    )
    return int(count or 0)


def _classify_previous_intent_for_retry(
    *,
    intent_id: str,
    status: str,
    order_id: object,
    exchange_order_id: object,
    failed_reason: object,
    local_order_count: int,
) -> dict[str, object]:
    status_value = status.lower()
    reason_value = str(failed_reason or "")
    if status_value not in {"failed", "rejected"}:
        return {
            "retry_allowed": False,
            "previous_intent_id": intent_id,
            "reason": f"previous_intent_status_not_retryable:{status_value}",
        }
    if order_id:
        return {
            "retry_allowed": False,
            "previous_intent_id": intent_id,
            "reason": "previous_intent_has_order_id",
        }
    if exchange_order_id:
        return {
            "retry_allowed": False,
            "previous_intent_id": intent_id,
            "reason": "previous_intent_has_exchange_order_id",
        }
    if local_order_count > 0:
        return {
            "retry_allowed": False,
            "previous_intent_id": intent_id,
            "reason": "previous_intent_has_local_order",
        }
    if not _failed_reason_is_pre_order(reason_value):
        return {
            "retry_allowed": False,
            "previous_intent_id": intent_id,
            "reason": "previous_intent_failure_phase_ambiguous",
        }
    return {
        "retry_allowed": True,
        "retryable_pre_order_failure": True,
        "failure_phase": "pre_order_rejected",
        "previous_intent_id": intent_id,
        "reason": "retryable_pre_order_failure",
    }


def _failed_reason_is_pre_order(reason: str) -> bool:
    lowered = reason.lower()
    return any(
        marker in lowered
        for marker in [
            "pre_order",
            "before_order",
            "before order",
            "position_side_mismatch",
            "position side mismatch",
        ]
    )


def _build_owner_bounded_result_review_ledger(
    *,
    authorization: BoundedLiveTrialAuthorization,
    result: OwnerBoundedExecutionResponse,
    final_gate: BnbLiveExecutionBoundaryDryRunResponse,
) -> dict[str, object]:
    return {
        "ledger_version": "owner_bounded_review_ledger_v0",
        "authorization_id": authorization.authorization_id,
        "carrier_id": authorization.carrier_id,
        "symbol": authorization.symbol,
        "side": authorization.side,
        "entry": {
            "status": "filled_or_submitted",
            "order_id": result.entry_order_id,
            "exchange_order_id": result.entry_exchange_order_id,
            "quantity": str(authorization.quantity),
            "max_notional": str(authorization.max_notional),
        },
        "exit": _not_available_field("exit_not_recorded_at_entry_execution_time"),
        "realized_pnl": _not_available_field("position_not_closed"),
        "unrealized_pnl": _not_available_field("exchange_mark_price_read_required"),
        "costs": _cost_ledger_not_available(),
        "holding_time": _not_available_field("position_lifecycle_still_open"),
        "tp_sl_result": {
            "status": result.protection_status or "not_available",
            "tp_order_ids": list(result.tp_order_ids),
            "sl_order_id": result.sl_order_id,
        },
        "strategy_outcome": "pending_post_action_review",
        "review_outcome": {
            "status": "pending",
            "allowed_values": ["promote", "revise", "park"],
            "requires_owner_review": True,
        },
        "warnings": [
            "fee_not_available",
            "funding_not_available",
            "slippage_not_available",
        ],
        "hard_blockers": [],
        "final_gate_result": final_gate.final_preflight_result,
    }


def _build_owner_bounded_failure_review_ledger(
    *,
    authorization: BoundedLiveTrialAuthorization,
    exc: OwnerBoundedExecutionError,
    final_gate: BnbLiveExecutionBoundaryDryRunResponse,
) -> dict[str, object]:
    return {
        "ledger_version": "owner_bounded_review_ledger_v0",
        "authorization_id": authorization.authorization_id,
        "carrier_id": authorization.carrier_id,
        "symbol": authorization.symbol,
        "side": authorization.side,
        "entry": {
            "status": "failed_or_partial",
            "order_id": exc.entry_order_id,
            "exchange_order_id": exc.entry_exchange_order_id,
            "quantity": str(authorization.quantity),
            "max_notional": str(authorization.max_notional),
        },
        "exit": _not_available_field("execution_failed_before_complete_lifecycle"),
        "realized_pnl": _not_available_field("execution_failed_before_close"),
        "unrealized_pnl": _not_available_field("execution_failed_or_exchange_read_required"),
        "costs": _cost_ledger_not_available(),
        "holding_time": _not_available_field("execution_failed_before_complete_lifecycle"),
        "tp_sl_result": {
            "status": exc.protection_status or "not_available",
            "tp_order_ids": list(exc.tp_order_ids),
            "sl_order_id": exc.sl_order_id,
        },
        "strategy_outcome": "failed_requires_owner_review",
        "review_outcome": {
            "status": "pending",
            "allowed_values": ["revise", "park"],
            "requires_owner_review": True,
        },
        "warnings": [
            "fee_not_available",
            "funding_not_available",
            "slippage_not_available",
        ],
        "hard_blockers": list(exc.blockers),
        "final_gate_result": final_gate.final_preflight_result,
    }


def _build_owner_bounded_review_ledger(
    *,
    authorization: BoundedLiveTrialAuthorization,
    local_orders: list[dict[str, object]],
    execution_results: list[dict[str, object]],
) -> dict[str, object]:
    entry_order = _first_order_by_role(local_orders, "ENTRY")
    protection_orders = [
        order for order in local_orders if str(order.get("order_role") or "").upper() in {"TP1", "SL"}
    ]
    exit_orders = [
        order
        for order in protection_orders
        if str(order.get("status") or "").upper() in {"FILLED", "CLOSED"}
    ]
    entry_filled = str((entry_order or {}).get("status") or "").upper() in {"FILLED", "CLOSED"}
    protection_open = bool(protection_orders) and all(
        str(order.get("status") or "").upper() in {"OPEN", "SUBMITTED", "NEW"}
        for order in protection_orders
    )
    if exit_orders:
        lifecycle_status = "closed_from_pg_exit_order"
        tp_sl_result = "tp_or_sl_filled"
    elif entry_filled and protection_open:
        lifecycle_status = "protected_open_from_pg_orders"
        tp_sl_result = "protected_open"
    elif entry_filled:
        lifecycle_status = "entry_filled_protection_state_incomplete"
        tp_sl_result = "protection_state_incomplete"
    else:
        lifecycle_status = "not_started_or_unknown"
        tp_sl_result = "not_available"

    realized = _realized_pnl_from_orders(entry_order, exit_orders)
    return {
        "ledger_version": "owner_bounded_review_ledger_v0",
        "authorization_id": authorization.authorization_id,
        "carrier_id": authorization.carrier_id,
        "symbol": authorization.symbol,
        "side": authorization.side,
        "lifecycle_status": lifecycle_status,
        "entry": _order_ledger_entry(entry_order),
        "exit": _exit_ledger_entry(exit_orders),
        "realized_pnl": realized,
        "unrealized_pnl": _not_available_field("execution_state_endpoint_does_not_call_exchange"),
        "costs": _cost_ledger_not_available(),
        "holding_time": _holding_time_ledger(entry_order, exit_orders),
        "tp_sl_result": {
            "status": tp_sl_result,
            "protection_order_count": len(protection_orders),
            "open_protection_order_count": sum(
                1
                for order in protection_orders
                if str(order.get("status") or "").upper() in {"OPEN", "SUBMITTED", "NEW"}
            ),
        },
        "strategy_outcome": "pending_post_action_review"
        if lifecycle_status != "closed_from_pg_exit_order"
        else "pending_closed_trade_review",
        "review_outcome": {
            "status": "pending",
            "allowed_values": ["promote", "revise", "park"],
            "requires_owner_review": True,
        },
        "result_records": len(execution_results),
        "warnings": [
            "fee_not_available",
            "funding_not_available",
            "slippage_not_available",
        ],
        "hard_blockers": [],
    }


def _cost_ledger_not_available() -> dict[str, object]:
    return {
        "fees": _not_available_field("fee_fetch_not_integrated"),
        "funding": _not_available_field("funding_fetch_not_integrated"),
        "slippage": _not_available_field("entry_quote_snapshot_not_available"),
        "total_cost": _not_available_field("cost_components_not_available"),
    }


def _not_available_field(reason: str) -> dict[str, object]:
    return {
        "status": "not_available",
        "value": None,
        "asset": "USDT",
        "reason": reason,
        "hard_blocker": False,
    }


def _first_order_by_role(
    orders: list[dict[str, object]],
    role: str,
) -> dict[str, object] | None:
    for order in orders:
        if str(order.get("order_role") or "").upper() == role:
            return order
    return None


def _order_ledger_entry(order: dict[str, object] | None) -> dict[str, object]:
    if order is None:
        return {"status": "not_available", "reason": "entry_order_not_recorded"}
    return {
        "status": str(order.get("status") or "unknown").lower(),
        "order_id": order.get("id"),
        "exchange_order_id": order.get("exchange_order_id"),
        "quantity": _decimal_str(order.get("filled_qty") or order.get("requested_qty")),
        "requested_quantity": _decimal_str(order.get("requested_qty")),
        "average_price": _decimal_str(order.get("average_exec_price")),
        "created_at_ms": order.get("created_at"),
    }


def _exit_ledger_entry(exit_orders: list[dict[str, object]]) -> dict[str, object]:
    if not exit_orders:
        return {
            "status": "not_available",
            "reason": "no_exit_fill_recorded",
            "hard_blocker": False,
        }
    order = exit_orders[-1]
    return {
        "status": str(order.get("status") or "unknown").lower(),
        "order_id": order.get("id"),
        "exchange_order_id": order.get("exchange_order_id"),
        "order_role": order.get("order_role"),
        "quantity": _decimal_str(order.get("filled_qty") or order.get("requested_qty")),
        "average_price": _decimal_str(order.get("average_exec_price") or order.get("price")),
        "created_at_ms": order.get("created_at"),
    }


def _realized_pnl_from_orders(
    entry_order: dict[str, object] | None,
    exit_orders: list[dict[str, object]],
) -> dict[str, object]:
    if entry_order is None or not exit_orders:
        return _not_available_field("position_not_closed")
    entry_price = _decimal_or_none(entry_order.get("average_exec_price"))
    exit_order = exit_orders[-1]
    exit_price = _decimal_or_none(exit_order.get("average_exec_price") or exit_order.get("price"))
    quantity = _decimal_or_none(exit_order.get("filled_qty") or entry_order.get("filled_qty"))
    if entry_price is None or exit_price is None or quantity is None:
        return _not_available_field("entry_or_exit_price_missing")
    value = (exit_price - entry_price) * quantity
    return {
        "status": "estimated_from_pg_orders_before_costs",
        "value": str(value),
        "asset": "USDT",
        "costs_included": False,
        "hard_blocker": False,
    }


def _holding_time_ledger(
    entry_order: dict[str, object] | None,
    exit_orders: list[dict[str, object]],
) -> dict[str, object]:
    entry_created = _int_or_none((entry_order or {}).get("created_at"))
    if entry_created is None:
        return _not_available_field("entry_timestamp_missing")
    if exit_orders:
        exit_created = _int_or_none(exit_orders[-1].get("created_at"))
        if exit_created is not None:
            return {
                "status": "closed",
                "value_ms": max(0, exit_created - entry_created),
                "hard_blocker": False,
            }
    return {
        "status": "in_progress",
        "value_ms": max(0, _now_ms() - entry_created),
        "hard_blocker": False,
    }


def _decimal_or_none(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _decimal_str(value: object) -> str | None:
    decimal_value = _decimal_or_none(value)
    return str(decimal_value) if decimal_value is not None else None


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _now_ms() -> int:
    return int(time.time() * 1000)
