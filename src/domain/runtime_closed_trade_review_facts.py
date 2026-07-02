"""Resolve closed-trade review inputs from runtime order facts.

This artifact is deliberately read-only. It resolves the lifecycle review
inputs between a runtime reduce-only close and the existing closed-trade review
writer by identifying the entry/exit order IDs that should be passed to the
review step.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.models import Order, OrderRole, OrderStatus, Position
from src.domain.strategy_runtime import StrategyRuntimeInstance


EXIT_ROLES = {
    OrderRole.EXIT,
    OrderRole.SL,
    OrderRole.TP1,
    OrderRole.TP2,
    OrderRole.TP3,
    OrderRole.TP4,
    OrderRole.TP5,
}


class RuntimeClosedTradeReviewFactsStatus(str, Enum):
    BLOCKED = "blocked"
    WAITING_FOR_CLOSE = "waiting_for_close"
    READY_FOR_CLOSED_REVIEW = "ready_for_closed_review"


class RuntimeClosedTradeReviewFactsArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=320)
    status: RuntimeClosedTradeReviewFactsStatus
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    active_position_count: int = Field(ge=0)
    open_order_count: int = Field(ge=0)
    entry_order_id: Optional[str] = Field(default=None, max_length=128)
    exit_order_id: Optional[str] = Field(default=None, max_length=128)
    authorization_id: Optional[str] = Field(default=None, max_length=220)
    review_command_args: list[str] = Field(default_factory=list)
    recommended_review_checkpoint: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    closed_trade_review_facts_evidence_only: Literal[True] = True
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True
    review_record_created: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    order_created: Literal[False] = False
    order_cancelled: Literal[False] = False
    order_amended: Literal[False] = False
    position_closed: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _status_contract(self) -> "RuntimeClosedTradeReviewFactsArtifact":
        if self.status == RuntimeClosedTradeReviewFactsStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked review facts artifact requires blockers")
        if self.status == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW:
            if not self.entry_order_id or not self.exit_order_id:
                raise ValueError("ready review facts artifact requires entry and exit order IDs")
            if not self.review_command_args:
                raise ValueError("ready review facts artifact requires review command args")
        return self


def build_runtime_closed_trade_review_facts_artifact(
    *,
    runtime: StrategyRuntimeInstance,
    orders: list[Order],
    active_positions: list[Position],
    open_orders: list[Order],
    now_ms: int,
) -> RuntimeClosedTradeReviewFactsArtifact:
    active_positions = _runtime_positions(runtime, active_positions)
    open_orders = _runtime_orders(runtime, open_orders)
    scoped_orders = _runtime_orders(runtime, orders)
    blockers: list[str] = []
    warnings: list[str] = []
    entry_order = _select_entry_order(scoped_orders)

    if active_positions:
        status = RuntimeClosedTradeReviewFactsStatus.WAITING_FOR_CLOSE
        recommended = "wait_for_runtime_close_before_closed_review"
    elif entry_order is None:
        status = RuntimeClosedTradeReviewFactsStatus.BLOCKED
        blockers.append("entry_order_not_found")
        recommended = "repair_or_recover_entry_order_before_closed_review"
    else:
        exit_order = _select_exit_order(scoped_orders, entry_order)
        if exit_order is None:
            status = RuntimeClosedTradeReviewFactsStatus.BLOCKED
            blockers.append("terminal_exit_order_not_found")
            recommended = "recover_or_register_terminal_exit_order_before_closed_review"
        elif open_orders:
            status = RuntimeClosedTradeReviewFactsStatus.BLOCKED
            blockers.append("local_open_order_still_present")
            recommended = "resolve_open_orders_before_closed_review"
        else:
            status = RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
            recommended = "run_create_runtime_closed_trade_review_dry_run_then_apply"

    entry_order = entry_order if "entry_order_not_found" not in blockers else None
    exit_order = (
        _select_exit_order(scoped_orders, entry_order)
        if entry_order is not None and not active_positions
        else None
    )
    authorization_id = _authorization_id(runtime)
    command_args = (
        _review_command_args(runtime, entry_order, exit_order, authorization_id)
        if status == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
        and entry_order is not None
        and exit_order is not None
        else []
    )
    if scoped_orders and entry_order is not None and exit_order is not None:
        if exit_order.parent_order_id != entry_order.id:
            warnings.append("exit_order_resolved_by_signal_id_without_parent_link")
    if not scoped_orders:
        warnings.append("runtime_scoped_orders_empty")

    return RuntimeClosedTradeReviewFactsArtifact(
        artifact_id=f"runtime-closed-review-facts-{runtime.runtime_instance_id}-{now_ms}",
        status=status,
        runtime_instance_id=runtime.runtime_instance_id,
        symbol=runtime.symbol,
        active_position_count=len(active_positions),
        open_order_count=len(open_orders),
        entry_order_id=entry_order.id if entry_order is not None else None,
        exit_order_id=exit_order.id if exit_order is not None else None,
        authorization_id=authorization_id,
        review_command_args=command_args,
        recommended_review_checkpoint=recommended,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata={
            "scope": "runtime_closed_trade_review_facts",
            "right_tail_objective": "Closed review facts preserve attempt learning after bounded losses or tail wins.",
        },
        created_at_ms=now_ms,
    )


def _runtime_orders(runtime: StrategyRuntimeInstance, orders: list[Order]) -> list[Order]:
    strict = [
        order
        for order in orders
        if order.runtime_instance_id == runtime.runtime_instance_id
        and order.symbol == runtime.symbol
    ]
    if strict:
        runtime_signal_ids = {order.signal_id for order in strict}
        return [
            order
            for order in orders
            if order.symbol == runtime.symbol and order.signal_id in runtime_signal_ids
        ]
    return []


def _runtime_positions(
    runtime: StrategyRuntimeInstance,
    positions: list[Position],
) -> list[Position]:
    return [
        position
        for position in positions
        if position.symbol == runtime.symbol
        and (
            position.runtime_instance_id == runtime.runtime_instance_id
            or position.runtime_instance_id is None
        )
    ]


def _select_entry_order(orders: list[Order]) -> Order | None:
    candidates = [
        order
        for order in orders
        if order.order_role == OrderRole.ENTRY and order.status == OrderStatus.FILLED
    ]
    return _latest_order(candidates)


def _select_exit_order(orders: list[Order], entry_order: Order | None) -> Order | None:
    if entry_order is None:
        return None
    candidates = [
        order
        for order in orders
        if order.order_role in EXIT_ROLES
        and order.status == OrderStatus.FILLED
        and (order.parent_order_id == entry_order.id or order.signal_id == entry_order.signal_id)
    ]
    return _latest_order(candidates)


def _latest_order(orders: list[Order]) -> Order | None:
    if not orders:
        return None
    return sorted(
        orders,
        key=lambda order: (
            order.filled_at or order.updated_at or order.created_at,
            order.updated_at,
            order.id,
        ),
        reverse=True,
    )[0]


def _authorization_id(runtime: StrategyRuntimeInstance) -> str | None:
    value = runtime.metadata.get("last_exchange_submit_action_authorization_id")
    return str(value) if value else None


def _review_command_args(
    runtime: StrategyRuntimeInstance,
    entry_order: Order,
    exit_order: Order,
    authorization_id: str | None,
) -> list[str]:
    args = [
        "scripts/create_runtime_closed_trade_review.py",
        "--runtime-instance-id",
        runtime.runtime_instance_id,
        "--entry-order-id",
        entry_order.id,
        "--exit-order-id",
        exit_order.id,
    ]
    if authorization_id:
        args.extend(["--authorization-id", authorization_id])
    return args


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
