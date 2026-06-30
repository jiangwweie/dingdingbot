"""Create closed lifecycle review records from resolved runtime trade facts."""

from __future__ import annotations

from decimal import Decimal
import time
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.domain.live_lifecycle_review import BrcLiveLifecycleReviewRecord
from src.domain.models import Direction, Order, OrderRole, OrderStatus, Position
from src.domain.right_tail_review import (
    RightTailTradeClassification,
    review_right_tail_trade_path,
)
from src.domain.runtime_semantic_review_artifact import (
    build_runtime_semantic_review_artifact,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimeRepositoryPort(Protocol):
    async def get(self, runtime_instance_id: str) -> StrategyRuntimeInstance | None:
        ...


class OrderRepositoryPort(Protocol):
    async def get_order(self, order_id: str) -> Order | None:
        ...

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        ...


class PositionRepositoryPort(Protocol):
    async def get_by_signal_id(self, signal_id: str) -> list[Position]:
        ...

    async def list_active(self, *, symbol: str | None = None, limit: int = 100) -> list[Position]:
        ...


class LiveLifecycleReviewRepositoryPort(Protocol):
    async def append(
        self,
        record: BrcLiveLifecycleReviewRecord,
    ) -> BrcLiveLifecycleReviewRecord:
        ...

    async def list(
        self,
        *,
        authorization_id: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[BrcLiveLifecycleReviewRecord]:
        ...


class ReconciliationServicePort(Protocol):
    async def build_read_model(self, symbol: str) -> Any:
        ...


class RuntimeClosedTradeLifecycleReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["blocked", "ready_to_record", "recorded", "already_recorded"]
    review_id: str
    runtime_instance_id: str
    authorization_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    entry_order_id: str
    exit_order_id: str
    review_record: BrcLiveLifecycleReviewRecord | None = None
    right_tail_classification: str | None = None
    attempt_continuation_quality: str | None = None
    semantic_trace_complete: bool = False
    local_state_mutated: bool = False
    live_lifecycle_review_written: bool = False
    exchange_read_only: bool
    exchange_write_called: Literal[False] = False
    order_created: Literal[False] = False
    order_cancelled: Literal[False] = False
    order_amended: Literal[False] = False
    position_closed: Literal[False] = False
    runtime_budget_mutated: Literal[False] = False
    execution_intent_created: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeClosedTradeLifecycleReviewService:
    """Record review evidence after a runtime trade is already closed.

    The service reads local order/position facts and optional reconciliation
    facts, then appends a `BrcLiveLifecycleReviewRecord`. It never calls order
    placement, OrderLifecycle, exchange writes, runtime budget mutation, or
    withdrawal/transfer flows.
    """

    def __init__(
        self,
        *,
        runtime_repository: RuntimeRepositoryPort,
        order_repository: OrderRepositoryPort,
        position_repository: PositionRepositoryPort,
        live_lifecycle_review_repository: LiveLifecycleReviewRepositoryPort,
        reconciliation_service: ReconciliationServicePort | None = None,
    ) -> None:
        self._runtime_repository = runtime_repository
        self._order_repository = order_repository
        self._position_repository = position_repository
        self._live_lifecycle_review_repository = live_lifecycle_review_repository
        self._reconciliation_service = reconciliation_service

    async def create_closed_trade_review(
        self,
        *,
        runtime_instance_id: str,
        entry_order_id: str,
        exit_order_id: str,
        authorization_id: str | None = None,
        review_outcome: Literal["auto", "promote", "revise", "park"] = "auto",
        apply: bool = False,
        now_ms: int | None = None,
    ) -> RuntimeClosedTradeLifecycleReviewResult:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        blockers: list[str] = []
        warnings: list[str] = []
        runtime = await self._runtime_repository.get(runtime_instance_id)
        entry_order = await self._order_repository.get_order(entry_order_id)
        exit_order = await self._order_repository.get_order(exit_order_id)

        if runtime is None:
            blockers.append("runtime_not_found")
        if entry_order is None:
            blockers.append("entry_order_not_found")
        if exit_order is None:
            blockers.append("exit_order_not_found")
        if runtime is None or entry_order is None or exit_order is None:
            return self._result(
                status="blocked",
                runtime_instance_id=runtime_instance_id,
                entry_order_id=entry_order_id,
                exit_order_id=exit_order_id,
                review_id=_review_id(authorization_id, runtime_instance_id, exit_order_id),
                authorization_id=authorization_id,
                blockers=blockers,
                warnings=warnings,
            )

        authorization_id = _resolve_authorization_id(
            explicit=authorization_id,
            runtime=runtime,
        )
        review_id = _review_id(authorization_id, runtime_instance_id, exit_order.id)

        positions = await self._position_repository.get_by_signal_id(entry_order.signal_id)
        closed_positions = [item for item in positions if item.is_closed]
        active_positions = await self._position_repository.list_active(
            symbol=runtime.symbol,
            limit=max(runtime.boundary.max_active_positions + 5, 20),
        )
        open_orders = await self._order_repository.get_open_orders(runtime.symbol)
        reconciliation = await self._reconciliation(runtime.symbol)

        blockers.extend(
            _validate_trade_facts(
                runtime=runtime,
                entry_order=entry_order,
                exit_order=exit_order,
                closed_positions=closed_positions,
                active_positions=active_positions,
                open_orders=open_orders,
                reconciliation=reconciliation,
            )
        )
        warnings.extend(reconciliation["warnings"])
        if (
            runtime.boundary.budget_reserved == Decimal("0")
            and runtime.boundary.total_budget is not None
        ):
            warnings.append("runtime_budget_reserved_zero_max_loss_basis_may_be_missing")

        existing = await self._existing_review(review_id, authorization_id, runtime.symbol)
        if existing is not None:
            return self._record_result(
                status="already_recorded",
                runtime=runtime,
                entry_order=entry_order,
                exit_order=exit_order,
                record=existing,
                blockers=[],
                warnings=warnings,
                exchange_read_only=reconciliation["exchange_read_only"],
            )

        if blockers:
            return self._result(
                status="blocked",
                runtime_instance_id=runtime.runtime_instance_id,
                entry_order_id=entry_order.id,
                exit_order_id=exit_order.id,
                review_id=review_id,
                authorization_id=authorization_id,
                symbol=runtime.symbol,
                side=runtime.side,
                blockers=_dedupe(blockers),
                warnings=_dedupe(warnings),
                exchange_read_only=reconciliation["exchange_read_only"],
            )

        position = closed_positions[0] if closed_positions else None
        right_tail_path = _right_tail_trade_path(
            runtime=runtime,
            entry_order=entry_order,
            exit_order=exit_order,
            position=position,
        )
        right_tail_review = review_right_tail_trade_path(
            _right_tail_trade_path_facts(right_tail_path)
        )
        if right_tail_review.status != "reviewed":
            blockers.extend(
                f"right_tail_review_input_missing:{item}"
                for item in right_tail_review.required_inputs
            )
            return self._result(
                status="blocked",
                runtime_instance_id=runtime.runtime_instance_id,
                entry_order_id=entry_order.id,
                exit_order_id=exit_order.id,
                review_id=review_id,
                authorization_id=authorization_id,
                symbol=runtime.symbol,
                side=runtime.side,
                blockers=_dedupe(blockers),
                warnings=_dedupe(warnings + right_tail_review.warnings),
                exchange_read_only=reconciliation["exchange_read_only"],
            )

        final_review_outcome = (
            _auto_review_outcome(right_tail_review.classification)
            if review_outcome == "auto"
            else review_outcome
        )
        record = BrcLiveLifecycleReviewRecord(
            review_id=review_id,
            authorization_id=authorization_id,
            carrier_id=runtime.carrier_id or f"{runtime.strategy_family_id}-runtime",
            strategy_family_id=runtime.strategy_family_id,
            runtime_instance_id=runtime.runtime_instance_id,
            trial_binding_id=runtime.trial_binding_id,
            strategy_family_version_id=runtime.strategy_family_version_id,
            signal_evaluation_id=entry_order.signal_evaluation_id,
            order_candidate_id=entry_order.order_candidate_id,
            symbol=runtime.symbol,
            side=runtime.side.lower(),  # type: ignore[arg-type]
            quantity=str(exit_order.filled_qty or entry_order.filled_qty),
            max_notional=_notional(entry_order),
            leverage=_optional_decimal_string(runtime.boundary.max_leverage),
            max_attempts=runtime.boundary.max_attempts,
            protection_mode=_protection_mode(exit_order),
            review_requirement="post_action_review_required",
            lifecycle_status="closed_reviewed",
            review_status="closed_reviewed",
            final_gate_result=str(
                runtime.metadata.get("last_final_gate_result")
                or "passed_before_first_real_submit"
            ),
            protection_status=_protection_status(exit_order),
            execution_intent_id=_optional_metadata(runtime, "last_execution_intent_id"),
            entry_order_id=entry_order.id,
            entry_exchange_order_id=entry_order.exchange_order_id,
            tp_order_ids=[] if exit_order.order_role != OrderRole.TP1 else [exit_order.id],
            tp_exchange_order_ids=(
                []
                if exit_order.order_role != OrderRole.TP1
                else [exit_order.exchange_order_id] if exit_order.exchange_order_id else []
            ),
            sl_order_id=exit_order.id if exit_order.order_role == OrderRole.SL else None,
            sl_exchange_order_id=(
                exit_order.exchange_order_id if exit_order.order_role == OrderRole.SL else None
            ),
            tp_price=(
                _price_string(exit_order)
                if exit_order.order_role in {OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5}
                else None
            ),
            sl_trigger=(
                _price_string(exit_order)
                if exit_order.order_role == OrderRole.SL
                else None
            ),
            owner_risk_acceptance=runtime.owner_risk_acceptance_id,
            hard_gates_passed=True,
            evidence_refs=[
                f"order:{entry_order.id}",
                f"order:{exit_order.id}",
                f"position:{position.id}" if position is not None else "position:missing",
                reconciliation["evidence_ref"],
            ],
            metadata={
                "ledger_write_path": "runtime_closed_trade_lifecycle_review_service",
                "review_outcome": final_review_outcome,
                "strategy_outcome": right_tail_review.classification.value,
                "close_reason": _close_reason(exit_order),
                "cleanup_evidence_ref": reconciliation["evidence_ref"],
                "right_tail_trade_path": right_tail_path,
                "right_tail_review_result": right_tail_review.model_dump(mode="json"),
                "attempt_continuation_quality": (
                    right_tail_review.attempt_continuation_quality.value
                ),
                "terminal_order_facts_only": True,
                "mfe_mae_quality": "terminal_conservative_bounds",
                "small_bounded_losses_are_acceptable": True,
                "no_action_guarantee": True,
            },
            created_by="codex",
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
        )
        artifact = build_runtime_semantic_review_artifact(record)
        if artifact.right_tail_review_status != "reviewed":
            return self._result(
                status="blocked",
                runtime_instance_id=runtime.runtime_instance_id,
                entry_order_id=entry_order.id,
                exit_order_id=exit_order.id,
                review_id=review_id,
                authorization_id=authorization_id,
                symbol=runtime.symbol,
                side=runtime.side,
                blockers=["runtime_semantic_review_artifact_not_reviewed"],
                warnings=_dedupe(warnings + artifact.warnings),
                exchange_read_only=reconciliation["exchange_read_only"],
            )

        if not apply:
            return self._record_result(
                status="ready_to_record",
                runtime=runtime,
                entry_order=entry_order,
                exit_order=exit_order,
                record=record,
                blockers=[],
                warnings=warnings,
                exchange_read_only=reconciliation["exchange_read_only"],
            )

        saved = await self._live_lifecycle_review_repository.append(record)
        return self._record_result(
            status="recorded",
            runtime=runtime,
            entry_order=entry_order,
            exit_order=exit_order,
            record=saved,
            blockers=[],
            warnings=warnings,
            exchange_read_only=reconciliation["exchange_read_only"],
            local_state_mutated=True,
            live_lifecycle_review_written=True,
        )

    async def _existing_review(
        self,
        review_id: str,
        authorization_id: str,
        symbol: str,
    ) -> BrcLiveLifecycleReviewRecord | None:
        try:
            records = await self._live_lifecycle_review_repository.list(
                authorization_id=authorization_id,
                symbol=symbol,
                limit=100,
            )
        except Exception:
            return None
        for record in records:
            if record.review_id == review_id:
                return record
        return None

    async def _reconciliation(self, symbol: str) -> dict[str, Any]:
        if self._reconciliation_service is None:
            return {
                "available": False,
                "exchange_read_only": False,
                "evidence_ref": "reconciliation:unavailable",
                "blockers": ["reconciliation_service_unavailable"],
                "warnings": [],
            }
        try:
            result = await self._reconciliation_service.build_read_model(symbol)
        except Exception as exc:
            return {
                "available": False,
                "exchange_read_only": True,
                "evidence_ref": "reconciliation:read_failed",
                "blockers": [f"reconciliation_read_failed:{type(exc).__name__}"],
                "warnings": [],
            }
        severe = int(getattr(result, "severe_count", 0) or 0)
        warning = int(getattr(result, "warning_count", 0) or 0)
        checked_at = getattr(result, "checked_at", None)
        return {
            "available": True,
            "exchange_read_only": True,
            "evidence_ref": f"reconciliation:{symbol}:{checked_at}",
            "blockers": ["reconciliation_severe_mismatch"] if severe > 0 else [],
            "warnings": ["reconciliation_warning_present"] if warning > 0 else [],
            "severe_count": severe,
            "warning_count": warning,
            "mismatch_count": len(getattr(result, "mismatches", []) or []),
        }

    def _record_result(
        self,
        *,
        status: Literal["ready_to_record", "recorded", "already_recorded"],
        runtime: StrategyRuntimeInstance,
        entry_order: Order,
        exit_order: Order,
        record: BrcLiveLifecycleReviewRecord,
        blockers: list[str],
        warnings: list[str],
        exchange_read_only: bool,
        local_state_mutated: bool = False,
        live_lifecycle_review_written: bool = False,
    ) -> RuntimeClosedTradeLifecycleReviewResult:
        artifact = build_runtime_semantic_review_artifact(record)
        review = artifact.right_tail_review
        return self._result(
            status=status,
            runtime_instance_id=runtime.runtime_instance_id,
            entry_order_id=entry_order.id,
            exit_order_id=exit_order.id,
            review_id=record.review_id,
            authorization_id=record.authorization_id,
            symbol=record.symbol,
            side=record.side,
            review_record=record,
            right_tail_classification=(
                review.classification.value if review is not None else None
            ),
            attempt_continuation_quality=(
                review.attempt_continuation_quality.value if review is not None else None
            ),
            semantic_trace_complete=artifact.semantic_trace_complete,
            blockers=blockers,
            warnings=_dedupe(warnings + artifact.warnings),
            exchange_read_only=exchange_read_only,
            local_state_mutated=local_state_mutated,
            live_lifecycle_review_written=live_lifecycle_review_written,
            metadata={
                "runtime_budget_mutated": False,
                "next_attempt_requires_official_final_gate": True,
                "review_record_is_not_execution_authority": True,
            },
        )

    @staticmethod
    def _result(
        *,
        status: Literal["blocked", "ready_to_record", "recorded", "already_recorded"],
        runtime_instance_id: str,
        entry_order_id: str,
        exit_order_id: str,
        review_id: str,
        authorization_id: str | None = None,
        symbol: str | None = None,
        side: str | None = None,
        review_record: BrcLiveLifecycleReviewRecord | None = None,
        right_tail_classification: str | None = None,
        attempt_continuation_quality: str | None = None,
        semantic_trace_complete: bool = False,
        blockers: list[str] | None = None,
        warnings: list[str] | None = None,
        exchange_read_only: bool = False,
        local_state_mutated: bool = False,
        live_lifecycle_review_written: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeClosedTradeLifecycleReviewResult:
        return RuntimeClosedTradeLifecycleReviewResult(
            status=status,
            runtime_instance_id=runtime_instance_id,
            entry_order_id=entry_order_id,
            exit_order_id=exit_order_id,
            review_id=review_id,
            authorization_id=authorization_id,
            symbol=symbol,
            side=side,
            review_record=review_record,
            right_tail_classification=right_tail_classification,
            attempt_continuation_quality=attempt_continuation_quality,
            semantic_trace_complete=semantic_trace_complete,
            local_state_mutated=local_state_mutated,
            live_lifecycle_review_written=live_lifecycle_review_written,
            exchange_read_only=exchange_read_only,
            blockers=_dedupe(blockers or []),
            warnings=_dedupe(warnings or []),
            metadata=metadata or {},
        )


def _validate_trade_facts(
    *,
    runtime: StrategyRuntimeInstance,
    entry_order: Order,
    exit_order: Order,
    closed_positions: list[Position],
    active_positions: list[Position],
    open_orders: list[Order],
    reconciliation: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if entry_order.order_role != OrderRole.ENTRY:
        blockers.append("entry_order_role_not_entry")
    if exit_order.order_role not in {
        OrderRole.EXIT,
        OrderRole.SL,
        OrderRole.TP1,
        OrderRole.TP2,
        OrderRole.TP3,
        OrderRole.TP4,
        OrderRole.TP5,
    }:
        blockers.append("exit_order_role_not_exit_or_protection")
    if entry_order.status != OrderStatus.FILLED:
        blockers.append("entry_order_not_filled")
    if exit_order.status != OrderStatus.FILLED:
        blockers.append("exit_order_not_filled")
    if runtime.symbol != entry_order.symbol or runtime.symbol != exit_order.symbol:
        blockers.append("runtime_order_symbol_mismatch")
    if entry_order.direction != exit_order.direction:
        blockers.append("entry_exit_direction_mismatch")
    if runtime.side.lower() not in {"long", "short"}:
        blockers.append("runtime_side_not_reviewable")
    if _runtime_direction(runtime) != entry_order.direction:
        blockers.append("runtime_entry_direction_mismatch")
    if entry_order.signal_id != exit_order.signal_id:
        blockers.append("entry_exit_signal_id_mismatch")
    if not closed_positions:
        blockers.append("closed_position_not_found")
    if active_positions:
        blockers.append("active_position_still_present")
    if open_orders:
        blockers.append("local_open_order_still_present")
    if not reconciliation["available"]:
        blockers.extend(reconciliation["blockers"])
    elif reconciliation.get("severe_count", 0) > 0:
        blockers.extend(reconciliation["blockers"])
    if _exec_price(entry_order) is None:
        blockers.append("entry_exec_price_missing")
    if _exec_price(exit_order) is None:
        blockers.append("exit_exec_price_missing")
    if exit_order.filled_qty <= Decimal("0"):
        blockers.append("exit_filled_qty_missing")
    return blockers


def _right_tail_trade_path(
    *,
    runtime: StrategyRuntimeInstance,
    entry_order: Order,
    exit_order: Order,
    position: Position | None,
) -> dict[str, Any]:
    entry_price = _require_decimal(_exec_price(entry_order), "entry_exec_price")
    exit_price = _require_decimal(_exec_price(exit_order), "exit_exec_price")
    qty = exit_order.filled_qty or entry_order.filled_qty
    realized_pnl = (
        position.realized_pnl
        if position is not None
        else _directional_pnl(runtime.side, entry_price, exit_price, qty)
    )
    mfe_price, mae_price = _terminal_mfe_mae(
        side=runtime.side,
        entry_price=entry_price,
        exit_price=exit_price,
        realized_pnl=realized_pnl,
    )
    return {
        "trade_id": f"{runtime.runtime_instance_id}:{entry_order.id}:{exit_order.id}",
        "symbol": runtime.symbol,
        "side": runtime.side.lower(),
        "strategy_family_id": runtime.strategy_family_id,
        "strategy_family_version_id": runtime.strategy_family_version_id,
        "runtime_instance_id": runtime.runtime_instance_id,
        "order_candidate_id": entry_order.order_candidate_id,
        "entry_price": str(entry_price),
        "exit_price": str(exit_price),
        "mfe_price": str(mfe_price),
        "mae_price": str(mae_price),
        "realized_pnl": str(realized_pnl),
        "max_loss_budget": str(_max_loss_budget(runtime, entry_price, exit_price, qty)),
        "opened_at_ms": entry_order.filled_at or entry_order.updated_at or entry_order.created_at,
        "closed_at_ms": exit_order.filled_at or exit_order.updated_at or exit_order.created_at,
        "exit_reason": _close_reason(exit_order),
        "runner_required": True,
        "runner_preserved": _runner_preserved(exit_order, realized_pnl),
        "metadata": {
            "source": "runtime_closed_trade_lifecycle_review_service",
            "price_path_source": "terminal_order_and_position_facts",
            "mfe_mae_quality": "terminal_conservative_bounds",
            "quantity": str(qty),
            "exit_order_role": exit_order.order_role.value,
            "exit_order_id": exit_order.id,
            "entry_order_id": entry_order.id,
        },
    }


def _right_tail_trade_path_facts(payload: dict[str, Any]):
    from src.domain.right_tail_review import RightTailTradePathFacts

    return RightTailTradePathFacts.model_validate(payload)


def _resolve_authorization_id(
    *,
    explicit: str | None,
    runtime: StrategyRuntimeInstance,
) -> str:
    if explicit:
        return explicit
    for key in (
        "last_exchange_submit_action_authorization_id",
        "last_runtime_exchange_submit_action_authorization_id",
        "last_submit_authorization_id",
        "owner_real_submit_authorization_id",
        "owner_live_runtime_enablement_authorization_id",
    ):
        value = runtime.metadata.get(key)
        if value:
            return str(value)
    return f"runtime-review:{runtime.runtime_instance_id}"


def _review_id(
    authorization_id: str | None,
    runtime_instance_id: str,
    exit_order_id: str,
) -> str:
    auth = authorization_id or f"runtime-review:{runtime_instance_id}"
    return f"live-review-{auth}-closed-reviewed-{exit_order_id}"[:128]


def _runtime_direction(runtime: StrategyRuntimeInstance) -> Direction:
    return Direction.LONG if runtime.side.lower() == "long" else Direction.SHORT


def _exec_price(order: Order) -> Decimal | None:
    return order.average_exec_price or order.price or order.trigger_price


def _require_decimal(value: Decimal | None, name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{name}_missing")
    return value


def _directional_pnl(
    side: str,
    entry_price: Decimal,
    exit_price: Decimal,
    qty: Decimal,
) -> Decimal:
    if side.lower() == "short":
        return (entry_price - exit_price) * qty
    return (exit_price - entry_price) * qty


def _terminal_mfe_mae(
    *,
    side: str,
    entry_price: Decimal,
    exit_price: Decimal,
    realized_pnl: Decimal,
) -> tuple[Decimal, Decimal]:
    if realized_pnl > 0:
        return exit_price, entry_price
    if realized_pnl < 0:
        return entry_price, exit_price
    return entry_price, entry_price


def _max_loss_budget(
    runtime: StrategyRuntimeInstance,
    entry_price: Decimal,
    exit_price: Decimal,
    qty: Decimal,
) -> Decimal:
    if runtime.boundary.budget_reserved > Decimal("0"):
        return runtime.boundary.budget_reserved
    fallback = abs(entry_price - exit_price) * qty
    return fallback if fallback > Decimal("0") else Decimal("0.00000001")


def _notional(order: Order) -> str | None:
    price = _exec_price(order)
    if price is None:
        return None
    return str(price * order.filled_qty)


def _optional_decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _optional_metadata(runtime: StrategyRuntimeInstance, key: str) -> str | None:
    value = runtime.metadata.get(key)
    return str(value) if value else None


def _price_string(order: Order) -> str | None:
    value = order.trigger_price or order.price or order.average_exec_price
    return str(value) if value is not None else None


def _protection_mode(exit_order: Order) -> str:
    if exit_order.order_role == OrderRole.SL:
        return "hard_stop_only_or_sl_close"
    if exit_order.order_role in {OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5}:
        return "take_profit_close"
    return "explicit_exit"


def _protection_status(exit_order: Order) -> str:
    if exit_order.order_role == OrderRole.SL:
        return "sl_filled_flat_reconciled"
    if exit_order.order_role in {OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5}:
        return "tp_filled_flat_reconciled"
    return "exit_filled_flat_reconciled"


def _close_reason(exit_order: Order) -> str:
    if exit_order.exit_reason:
        return exit_order.exit_reason
    if exit_order.order_role == OrderRole.SL:
        return "stop_loss_filled"
    if exit_order.order_role in {OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5}:
        return "take_profit_filled"
    return "exit_filled"


def _runner_preserved(exit_order: Order, realized_pnl: Decimal) -> bool:
    if realized_pnl <= Decimal("0"):
        return False
    return exit_order.order_role not in {OrderRole.TP1, OrderRole.TP2}


def _auto_review_outcome(
    classification: RightTailTradeClassification,
) -> Literal["promote", "revise", "park"]:
    if classification == RightTailTradeClassification.RIGHT_TAIL_WIN:
        return "promote"
    if classification == RightTailTradeClassification.LOSS_BOUNDARY_BREACH:
        return "park"
    return "revise"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
