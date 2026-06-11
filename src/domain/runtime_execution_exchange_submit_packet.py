"""Non-executing exchange submit packet preview for runtime local orders.

This is the explicit design boundary after runtime local CREATED-order
registration. It maps already registered local orders to the shape a future
ExchangeGateway.place_order adapter would need, without creating exchange
payloads, assigning client order IDs, mutating order/intent state, or calling
the exchange.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType
from src.domain.runtime_execution_intent_local_order_binding import (
    RuntimeExecutionIntentLocalOrderBinding,
    RuntimeExecutionIntentLocalOrderBindingStatus,
)


class RuntimeExecutionExchangeSubmitPacketModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionExchangeSubmitPacketPreviewStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_EXCHANGE_SUBMIT_ADAPTER_DESIGN = (
        "ready_for_exchange_submit_adapter_design"
    )


class RuntimeExecutionExchangeOrderSubmitRequestPreview(
    RuntimeExecutionExchangeSubmitPacketModel
):
    local_order_id: str = Field(min_length=1, max_length=260)
    parent_order_id: Optional[str] = Field(default=None, max_length=260)
    order_role: OrderRole
    local_order_status: OrderStatus
    symbol: str = Field(min_length=1, max_length=128)
    direction: Direction
    gateway_order_type: str = Field(min_length=1, max_length=32)
    gateway_side: str = Field(pattern="^(buy|sell)$")
    position_side: Optional[str] = Field(default=None, pattern="^(LONG|SHORT)$")
    amount: Decimal = Field(gt=Decimal("0"))
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    reduce_only: bool
    future_client_order_reference: str = Field(min_length=1, max_length=260)
    future_client_order_reference_policy: Literal["use_local_order_id"] = (
        "use_local_order_id"
    )
    exchange_payload_created: Literal[False] = False
    exchange_order_id_assigned: Literal[False] = False

    @model_validator(mode="after")
    def _validate_request_preview(
        self,
    ) -> "RuntimeExecutionExchangeOrderSubmitRequestPreview":
        if self.order_role == OrderRole.ENTRY and self.reduce_only:
            raise ValueError("entry exchange submit preview cannot be reduce_only")
        if self.order_role != OrderRole.ENTRY and not self.reduce_only:
            raise ValueError("protection exchange submit preview must be reduce_only")
        return self


class RuntimeExecutionExchangeSubmitPacketPreview(
    RuntimeExecutionExchangeSubmitPacketModel
):
    packet_preview_id: str = Field(min_length=1, max_length=460)
    binding_id: str = Field(min_length=1, max_length=460)
    adapter_result_id: str = Field(min_length=1, max_length=420)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionExchangeSubmitPacketPreviewStatus
    symbol: str = Field(min_length=1, max_length=128)
    entry_order_id: Optional[str] = Field(default=None, max_length=260)
    local_order_ids: list[str] = Field(default_factory=list)
    protection_order_ids: list[str] = Field(default_factory=list)
    submit_request_previews: list[
        RuntimeExecutionExchangeOrderSubmitRequestPreview
    ] = Field(default_factory=list)
    entry_submit_request_preview: Optional[
        RuntimeExecutionExchangeOrderSubmitRequestPreview
    ] = None
    protection_submit_request_previews: list[
        RuntimeExecutionExchangeOrderSubmitRequestPreview
    ] = Field(default_factory=list)
    local_orders_resolved: bool = False
    local_order_count: int = Field(ge=0)
    entry_submit_request_count: int = Field(ge=0)
    protection_submit_request_count: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_exchange_submit_adapter: Literal[True] = True
    requires_order_lifecycle_submit_transition: Literal[True] = True
    requires_exchange_gateway_place_order: Literal[True] = True
    requires_entry_then_protection_submit_sequence: Literal[True] = True
    exchange_submit_adapter_enabled: Literal[False] = False
    exchange_submit_adapter_implemented: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_lifecycle_submit_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    not_exchange_submit_authority: Literal[True] = True
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_packet(self) -> "RuntimeExecutionExchangeSubmitPacketPreview":
        forbidden = {
            "client_order_id",
            "exchange_order_id",
            "exchange_payload",
            "place_order",
            "submit_order",
        }
        scanned = {
            "metadata": self.metadata,
            "submit_request_previews": self.submit_request_previews,
        }
        for key in _walk_keys(scanned):
            if key.lower() in forbidden:
                raise ValueError(
                    "exchange submit packet preview contains forbidden "
                    f"execution field: {key}"
                )
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("exchange submit packet preview cannot call exchange")
        if self.order_lifecycle_submit_called:
            raise ValueError(
                "exchange submit packet preview cannot call OrderLifecycle.submit_order"
            )
        if self.execution_intent_status_changed:
            raise ValueError("exchange submit packet preview cannot mutate intent status")
        if self.owner_bounded_execution_called:
            raise ValueError("exchange submit packet preview cannot call OwnerBoundedExecution")
        if self.withdrawal_or_transfer_created:
            raise ValueError("exchange submit packet preview cannot create withdrawal/transfer")
        if (
            self.status
            == RuntimeExecutionExchangeSubmitPacketPreviewStatus
            .READY_FOR_EXCHANGE_SUBMIT_ADAPTER_DESIGN
            and self.blockers
        ):
            raise ValueError("ready exchange submit packet preview cannot have blockers")
        return self


def build_runtime_execution_exchange_submit_packet_preview(
    *,
    binding: RuntimeExecutionIntentLocalOrderBinding,
    local_orders: list[Order],
    now_ms: int,
) -> RuntimeExecutionExchangeSubmitPacketPreview:
    blockers = list(binding.blockers)
    warnings = list(binding.warnings)
    local_orders = list(local_orders)

    if (
        binding.status
        != RuntimeExecutionIntentLocalOrderBindingStatus.READY_FOR_EXCHANGE_SUBMIT_DESIGN
    ):
        blockers.append("intent_local_order_binding_not_ready")
    if binding.execution_intent_status_changed:
        blockers.append("binding_already_changed_intent_status")
    if binding.exchange_called or binding.exchange_order_submitted:
        blockers.append("binding_exchange_artifact_present")
    if binding.owner_bounded_execution_called:
        blockers.append("binding_owner_bounded_execution_called")
    if binding.withdrawal_or_transfer_created:
        blockers.append("binding_withdrawal_or_transfer_created")
    if not binding.entry_order_id:
        blockers.append("entry_order_id_missing_from_binding")
    if not binding.local_order_ids:
        blockers.append("local_order_ids_missing_from_binding")
    if not binding.protection_order_ids:
        blockers.append("protection_order_ids_missing_from_binding")

    orders_by_id = {order.id: order for order in local_orders}
    duplicate_ids = _duplicates([order.id for order in local_orders])
    if duplicate_ids:
        blockers.append("local_order_duplicate_ids_present")
    expected_ids = set(binding.local_order_ids)
    resolved_ids = set(orders_by_id)
    missing_ids = expected_ids - resolved_ids
    extra_ids = resolved_ids - expected_ids
    if missing_ids:
        blockers.append("local_order_ids_unresolved")
    if extra_ids:
        blockers.append("unexpected_local_order_ids_resolved")

    entry_orders = [
        order
        for order in local_orders
        if order.id == binding.entry_order_id or order.order_role == OrderRole.ENTRY
    ]
    if len({order.id for order in entry_orders}) != 1:
        blockers.append("entry_local_order_count_invalid")
    entry_order = orders_by_id.get(binding.entry_order_id or "")
    if entry_order is None and entry_orders:
        entry_order = entry_orders[0]
    if entry_order is not None and entry_order.id != binding.entry_order_id:
        blockers.append("entry_local_order_id_mismatch")

    protection_orders = [
        order for order in local_orders if order.id in set(binding.protection_order_ids)
    ]
    if len(protection_orders) != len(binding.protection_order_ids):
        blockers.append("protection_local_order_count_mismatch")

    request_previews: list[RuntimeExecutionExchangeOrderSubmitRequestPreview] = []
    for order in local_orders:
        blockers.extend(
            _validate_local_order_for_submit_packet(
                order=order,
                binding=binding,
                entry_order_id=binding.entry_order_id,
            )
        )
        request = _request_preview_for_order(order)
        if request is not None:
            request_previews.append(request)
        else:
            blockers.append("local_order_gateway_type_unsupported")

    entry_requests = [
        request
        for request in request_previews
        if request.local_order_id == binding.entry_order_id
    ]
    protection_requests = [
        request
        for request in request_previews
        if request.local_order_id in set(binding.protection_order_ids)
    ]
    if len(entry_requests) != 1:
        blockers.append("entry_submit_request_count_invalid")
    if len(protection_requests) != len(binding.protection_order_ids):
        blockers.append("protection_submit_request_count_mismatch")

    status = (
        RuntimeExecutionExchangeSubmitPacketPreviewStatus.BLOCKED
        if blockers
        else RuntimeExecutionExchangeSubmitPacketPreviewStatus
        .READY_FOR_EXCHANGE_SUBMIT_ADAPTER_DESIGN
    )
    symbol = (
        entry_order.symbol
        if entry_order is not None
        else local_orders[0].symbol
        if local_orders
        else binding.metadata.get("symbol")  # type: ignore[union-attr]
        if isinstance(binding.metadata, dict)
        else ""
    )
    if not symbol:
        symbol = "UNKNOWN"
        blockers.append("symbol_missing_from_local_orders")
    return RuntimeExecutionExchangeSubmitPacketPreview(
        packet_preview_id=f"runtime-exchange-submit-packet-preview-{binding.authorization_id}",
        binding_id=binding.binding_id,
        adapter_result_id=binding.adapter_result_id,
        authorization_id=binding.authorization_id,
        execution_intent_id=binding.execution_intent_id,
        runtime_instance_id=binding.runtime_instance_id,
        source_type=binding.source_type,
        source_id=binding.source_id,
        semantic_ids=binding.semantic_ids,
        status=status,
        symbol=symbol,
        entry_order_id=binding.entry_order_id,
        local_order_ids=list(binding.local_order_ids),
        protection_order_ids=list(binding.protection_order_ids),
        submit_request_previews=request_previews,
        entry_submit_request_preview=entry_requests[0] if len(entry_requests) == 1 else None,
        protection_submit_request_previews=protection_requests,
        local_orders_resolved=not missing_ids and bool(local_orders),
        local_order_count=len(local_orders),
        entry_submit_request_count=len(entry_requests),
        protection_submit_request_count=len(protection_requests),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_exchange_submit_packet_preview",
            "non_executing_exchange_submit_design_boundary": True,
            "local_order_binding_id": binding.binding_id,
            "adapter_result_id": binding.adapter_result_id,
            "does_not_mutate_execution_intent": True,
            "does_not_call_order_lifecycle_submit": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _validate_local_order_for_submit_packet(
    *,
    order: Order,
    binding: RuntimeExecutionIntentLocalOrderBinding,
    entry_order_id: str | None,
) -> list[str]:
    blockers: list[str] = []
    if order.status != OrderStatus.CREATED:
        blockers.append("local_order_status_not_created")
    if order.exchange_order_id is not None:
        blockers.append("local_order_exchange_artifact_present")
    if order.runtime_instance_id != binding.runtime_instance_id:
        blockers.append("local_order_runtime_instance_mismatch")
    if order.signal_evaluation_id != binding.semantic_ids.signal_evaluation_id:
        blockers.append("local_order_signal_evaluation_mismatch")
    if order.order_candidate_id != binding.semantic_ids.order_candidate_id:
        blockers.append("local_order_candidate_mismatch")
    if order.requested_qty <= Decimal("0"):
        blockers.append("local_order_requested_qty_invalid")
    if order.order_role == OrderRole.ENTRY:
        if order.id != entry_order_id:
            blockers.append("entry_local_order_id_mismatch")
        if order.reduce_only:
            blockers.append("entry_local_order_reduce_only_invalid")
        if order.parent_order_id is not None:
            blockers.append("entry_local_order_parent_invalid")
    else:
        if order.id not in set(binding.protection_order_ids):
            blockers.append("unexpected_protection_local_order")
        if not order.reduce_only:
            blockers.append("protection_local_order_reduce_only_missing")
        if order.parent_order_id != entry_order_id:
            blockers.append("protection_local_order_parent_mismatch")
    if order.order_type == OrderType.LIMIT and order.price is None:
        blockers.append("limit_local_order_price_missing")
    if order.order_type == OrderType.STOP_MARKET and order.trigger_price is None:
        blockers.append("stop_market_local_order_trigger_price_missing")
    if order.order_type not in {
        OrderType.MARKET,
        OrderType.LIMIT,
        OrderType.STOP_MARKET,
    }:
        blockers.append("local_order_type_not_supported_by_gateway_preview")
    return blockers


def _request_preview_for_order(
    order: Order,
) -> RuntimeExecutionExchangeOrderSubmitRequestPreview | None:
    gateway_order_type = _gateway_order_type(order.order_type)
    if gateway_order_type is None:
        return None
    return RuntimeExecutionExchangeOrderSubmitRequestPreview(
        local_order_id=order.id,
        parent_order_id=order.parent_order_id,
        order_role=order.order_role,
        local_order_status=order.status,
        symbol=order.symbol,
        direction=order.direction,
        gateway_order_type=gateway_order_type,
        gateway_side=_gateway_side(order),
        position_side=_gateway_position_side(order),
        amount=order.requested_qty,
        price=order.price,
        trigger_price=order.trigger_price,
        reduce_only=order.reduce_only,
        future_client_order_reference=order.id,
    )


def _gateway_order_type(order_type: OrderType) -> str | None:
    if order_type == OrderType.MARKET:
        return "market"
    if order_type == OrderType.LIMIT:
        return "limit"
    if order_type == OrderType.STOP_MARKET:
        return "stop_market"
    return None


def _gateway_side(order: Order) -> str:
    if order.order_role == OrderRole.ENTRY:
        return "buy" if order.direction == Direction.LONG else "sell"
    return "sell" if order.direction == Direction.LONG else "buy"


def _gateway_position_side(order: Order) -> str:
    return "LONG" if order.direction == Direction.LONG else "SHORT"


def _duplicates(items: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in items:
        if item in seen and item not in duplicates:
            duplicates.append(item)
        seen.add(item)
    return duplicates


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys
