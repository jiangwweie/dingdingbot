"""Advance one exact protected Ticket from current venue and market facts."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.events import (
    ExitRequested,
    ManagementReviewRequired,
    OwnerReductionPriceSatisfied,
    RunnerStopRequested,
    TakeProfitCompletedForExit,
    TakeProfitFilled,
    TakeProfitProgressed,
    TradeEvent,
)
from src.trading_kernel.domain.exit_execution import TpFillEvidence
from src.trading_kernel.domain.exit_policy import (
    ExitDecisionKind,
    ExitProfile,
    LifecycleMarketFacts,
    calculate_cost_adjusted_break_even,
    evaluate_profile_pre_tp1_exit,
    evaluate_profile_runner_exit,
)
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.trade_management import ManagementMode


class LifecycleMaintenanceStatus(StrEnum):
    NO_CHANGE = "no_change"
    PARTIAL_TP_RECORDED = "partial_tp_recorded"
    BREAK_EVEN_REQUESTED = "break_even_requested"
    RUNNER_MOVE_REQUESTED = "runner_move_requested"
    EXIT_REQUESTED = "exit_requested"


class TicketLifecycleFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_price_blocker: (
        Literal[
            "timeout",
            "transport_unavailable",
            "invalid_protocol",
            "identity_or_time_invalid",
        ]
        | None
    ) = None
    contract_market_price: Decimal | None = None
    contract_price_observed_at_ms: int | None = None
    contract_price_valid_until_ms: int | None = None
    tp_fill_evidence: TpFillEvidence | None = None
    current_market_price: Decimal | None = None
    active_stop_quantity: Decimal | None = None
    tp1_order_terminal: bool = False
    tp1_terminal_attribution: Literal["own_failure", "unknown", "natural"] = "unknown"
    position_quantity: Decimal
    tp1_filled_quantity: Decimal
    tp1_average_fill_price: Decimal | None
    allocated_entry_fee_quote: Decimal
    exit_taker_fee_rate: Decimal
    price_tick: Decimal
    market_facts: LifecycleMarketFacts | None
    observed_at_ms: int

    @field_validator(
        "position_quantity",
        "tp1_filled_quantity",
        "allocated_entry_fee_quote",
    )
    @classmethod
    def _require_nonnegative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("lifecycle quantities and fees cannot be negative")
        return value

    @field_validator("price_tick")
    @classmethod
    def _require_positive_tick(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("lifecycle price tick must be positive")
        return value

    @model_validator(mode="after")
    def _validate_facts(self) -> TicketLifecycleFacts:
        if self.observed_at_ms <= 0:
            raise ValueError("lifecycle observation time must be positive")
        if self.contract_price_blocker is not None and any(
            value is not None
            for value in (
                self.contract_market_price,
                self.contract_price_observed_at_ms,
                self.contract_price_valid_until_ms,
            )
        ):
            raise ValueError(
                "unavailable condition price cannot carry usable price facts"
            )
        if not Decimal(0) <= self.exit_taker_fee_rate < Decimal(1):
            raise ValueError("exit taker fee rate must be in [0, 1)")
        if self.tp1_filled_quantity > 0:
            if self.tp1_average_fill_price is None or self.tp1_average_fill_price <= 0:
                raise ValueError("TP1 fill requires a positive average price")
        elif self.tp1_average_fill_price is not None:
            raise ValueError("zero TP1 fill forbids an average price")
        return self


class LifecycleMaintenanceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    facts: TicketLifecycleFacts
    now_ms: int

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _require_ticket_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("lifecycle maintenance requires Ticket identity")
        return normalized

    @model_validator(mode="after")
    def _validate_time(self) -> LifecycleMaintenanceRequest:
        if self.now_ms < self.facts.observed_at_ms:
            raise ValueError("lifecycle maintenance cannot precede its facts")
        return self


class LifecycleMaintenanceResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: LifecycleMaintenanceStatus
    event_id: str | None = None


class _EventFields(TypedDict):
    event_id: str
    ticket_id: str
    sequence: int
    occurred_at_ms: int


async def maintain_ticket_lifecycle(
    uow: KernelUnitOfWork,
    request: LifecycleMaintenanceRequest,
) -> LifecycleMaintenanceResult:
    aggregate = await uow.aggregates.get_for_update(request.ticket_id)
    if aggregate is None:
        raise ValueError("lifecycle Ticket does not exist")
    if aggregate.management_mode is not ManagementMode.AUTO:
        return LifecycleMaintenanceResult(status=LifecycleMaintenanceStatus.NO_CHANGE)
    profile_record = await uow.exit_profiles.get_profile(
        exit_profile_id=aggregate.ticket.exit_policy_id,
        semantic_hash=aggregate.ticket.exit_policy_semantic_hash,
    )
    if profile_record is None:
        raise ValueError("Ticket has no exact frozen ExitProfile")
    profile = profile_record.profile
    if profile.position_side != aggregate.identity.netting_domain.position_side:
        raise ValueError("ExitProfile side differs from Ticket Netting Domain")

    if aggregate.status is AggregateStatus.POSITION_PROTECTED and aggregate.owner_reduction_context is not None:
        return await _maintain_owner_reduced_position(uow, aggregate, profile, request)

    if aggregate.status is AggregateStatus.POSITION_PROTECTED:
        target = aggregate.tp1_target_qty
        filled = request.facts.tp1_filled_quantity
        if filled < aggregate.tp1_filled_qty:
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.NO_CHANGE
            )
        if filled > target:
            raise ValueError("TP1 cumulative fill exceeds frozen target")
        if (filled < target and request.facts.tp1_order_terminal and request.facts.tp1_terminal_attribution == "natural"
            and request.facts.active_stop_quantity != aggregate.position_qty-(filled-aggregate.tp1_filled_qty)):
            # A known natural terminal update may race a position snapshot.
            # Reconciliation proves full exit before any budget release or new write.
            await uow.aggregates.expedite_reconciliation(aggregate.identity.ticket_id,due_at_ms=request.now_ms)
            return LifecycleMaintenanceResult(status=LifecycleMaintenanceStatus.NO_CHANGE)
        if (
            filled < target
            and request.facts.tp1_order_terminal
            and request.facts.tp1_terminal_attribution == "unknown"
        ):
            review = ManagementReviewRequired(
                **_event_fields(aggregate, request.now_ms),
                evidence_id=f"tp-terminal:{aggregate.identity.ticket_id}:{request.facts.observed_at_ms}",
                reason="tp1_terminal_attribution_unknown",
            )
            await uow.commit_reduction(
                event=review,
                reduction=reduce_event(aggregate, review),
                expected_version=aggregate.version,
            )
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.NO_CHANGE, event_id=review.event_id
            )
        remaining = aggregate.position_qty - (filled - aggregate.tp1_filled_qty)
        if remaining <= 0 or request.facts.position_quantity != remaining:
            raise ValueError(
                "TP1 venue quantity differs from exact cumulative projection"
            )
        market = request.facts.market_facts
        exit_reason = None
        if market is not None:
            if filled == target:
                # Only ABSOLUTE expiry survives full TP; pre-TP guards end here.
                if (
                    profile.time_stop is not None
                    and profile.time_stop.mode.value == "absolute"
                    and market.is_final_closed_candle
                    and market.holding_bars >= profile.time_stop.max_holding_bars
                ):
                    exit_reason = "absolute_time_stop_hit"
            else:
                decision = evaluate_profile_pre_tp1_exit(
                    profile=profile,
                    market_facts=market,
                    observed_at_ms=request.facts.observed_at_ms,
                    pre_tp1_reclaim_price=aggregate.ticket.pre_tp1_reclaim_price,
                    exposure_session_end_ms=aggregate.ticket.exposure_session_end_ms,
                )
                if decision.kind is ExitDecisionKind.EXIT:
                    exit_reason = decision.reason
        if filled < target and request.facts.tp1_order_terminal:
            exit_reason = exit_reason or "tp1_terminal_incomplete"
        if 0 < filled < target and filled > aggregate.tp1_filled_qty:
            assert request.facts.tp1_average_fill_price is not None
            progress = TakeProfitProgressed(
                **_event_fields(aggregate, request.now_ms),
                tp_fill_evidence=request.facts.tp_fill_evidence,
                cumulative_filled_qty=filled,
                average_fill_price=request.facts.tp1_average_fill_price,
                protection_covers_remainder=request.facts.active_stop_quantity
                == remaining,
                exit_reason=exit_reason,
            )
            await uow.commit_reduction(
                event=progress,
                reduction=reduce_event(aggregate, progress),
                expected_version=aggregate.version,
            )
            aggregate = await uow.aggregates.get_for_update(request.ticket_id)
            assert aggregate is not None
            if aggregate.status is AggregateStatus.EXIT_PENDING:
                return LifecycleMaintenanceResult(
                    status=LifecycleMaintenanceStatus.EXIT_REQUESTED,
                    event_id=progress.event_id,
                )
            if aggregate.status is not AggregateStatus.POSITION_PROTECTED:
                return LifecycleMaintenanceResult(
                    status=LifecycleMaintenanceStatus.PARTIAL_TP_RECORDED,
                    event_id=progress.event_id,
                )
        if exit_reason is not None:
            if filled == target:
                assert request.facts.tp1_average_fill_price is not None
                completed = TakeProfitCompletedForExit(
                    **_event_fields(aggregate, request.now_ms),
                    filled_qty=filled,
                    average_fill_price=request.facts.tp1_average_fill_price,
                    tp_fill_evidence=request.facts.tp_fill_evidence,
                )
                await uow.commit_reduction(
                    event=completed,
                    reduction=reduce_event(aggregate, completed),
                    expected_version=aggregate.version,
                )
                aggregate = await uow.aggregates.get_for_update(request.ticket_id)
                assert aggregate is not None
            exit_event = ExitRequested(
                **_event_fields(aggregate, request.now_ms), reason=exit_reason
            )
            await uow.commit_reduction(
                event=exit_event,
                reduction=reduce_event(aggregate, exit_event),
                expected_version=aggregate.version,
            )
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.EXIT_REQUESTED,
                event_id=exit_event.event_id,
            )
        if filled < target:
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.NO_CHANGE
            )
        runner_quantity = remaining
        if (
            aggregate.average_fill_price is None
            or request.facts.tp1_average_fill_price is None
        ):
            raise ValueError("TP1 venue facts lack exact entry or fill price")
        floor = calculate_cost_adjusted_break_even(
            side=profile.position_side,
            entry_average_price=aggregate.post_fill_exit_plan.entry_price
            if aggregate.post_fill_exit_plan
            else aggregate.average_fill_price,
            runner_quantity=runner_quantity,
            allocated_entry_fee_quote=request.facts.allocated_entry_fee_quote,
            exit_taker_fee_rate=request.facts.exit_taker_fee_rate,
            price_tick=request.facts.price_tick,
            slippage_buffer_ticks=(
                profile.break_even_floor.slippage_buffer_ticks
            ),
        )
        if aggregate.active_stop_price is not None:
            floor = (
                max(floor, aggregate.active_stop_price)
                if profile.position_side == "long"
                else min(floor, aggregate.active_stop_price)
            )
        current_price = request.facts.current_market_price
        if current_price is None and market is not None:
            current_price = market.latest_close
        if current_price is not None and (
            (profile.position_side == "long" and current_price <= floor)
            or (profile.position_side == "short" and current_price >= floor)
        ):
            exit_event = ExitRequested(
                **_event_fields(aggregate, request.now_ms), reason="break_even_crossed"
            )
            # Record full executed quantity without creating a replacement before exit.

            completed = TakeProfitCompletedForExit(
                **_event_fields(aggregate, request.now_ms),
                filled_qty=filled,
                average_fill_price=request.facts.tp1_average_fill_price,
                tp_fill_evidence=request.facts.tp_fill_evidence,
            )
            await uow.commit_reduction(
                event=completed,
                reduction=reduce_event(aggregate, completed),
                expected_version=aggregate.version,
            )
            aggregate = await uow.aggregates.get_for_update(request.ticket_id)
            assert aggregate is not None
            exit_event = ExitRequested(
                **_event_fields(aggregate, request.now_ms), reason="break_even_crossed"
            )
            await uow.commit_reduction(
                event=exit_event,
                reduction=reduce_event(aggregate, exit_event),
                expected_version=aggregate.version,
            )
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.EXIT_REQUESTED,
                event_id=exit_event.event_id,
            )
        tp1_event = TakeProfitFilled(
            **_event_fields(aggregate, request.now_ms),
            tp_fill_evidence=request.facts.tp_fill_evidence,
            filled_qty=target,
            average_fill_price=request.facts.tp1_average_fill_price,
            runner_floor_price=floor,
        )
        await uow.commit_reduction(
            event=tp1_event,
            reduction=reduce_event(aggregate, tp1_event),
            expected_version=aggregate.version,
        )
        return LifecycleMaintenanceResult(
            status=LifecycleMaintenanceStatus.BREAK_EVEN_REQUESTED,
            event_id=tp1_event.event_id,
        )

    if aggregate.status is AggregateStatus.RUNNER_PROTECTED:
        if request.facts.position_quantity != aggregate.position_qty:
            raise ValueError("runner venue quantity differs from Ticket projection")
        if request.facts.market_facts is None:
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.NO_CHANGE
            )
        if (
            aggregate.active_stop_price is None
            or aggregate.break_even_floor_price is None
        ):
            raise ValueError("runner protection lacks its active and floor prices")
        decision = evaluate_profile_runner_exit(
            profile=profile,
            current_stop=aggregate.active_stop_price,
            break_even_floor=aggregate.break_even_floor_price,
            price_tick=request.facts.price_tick,
            last_runner_watermark_ms=aggregate.runner_stop_watermark_ms or 0,
            market_facts=request.facts.market_facts,
        )
        if decision.kind is ExitDecisionKind.NO_CHANGE:
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.NO_CHANGE
            )
        if decision.kind is ExitDecisionKind.MOVE_STOP:
            if decision.proposed_stop is None:
                raise RuntimeError("runner move decision lacks a stop price")
            event: TradeEvent = RunnerStopRequested(
                **_event_fields(aggregate, request.now_ms),
                stop_price=decision.proposed_stop,
                source_watermark_ms=decision.source_watermark_ms,
            )
            status = LifecycleMaintenanceStatus.RUNNER_MOVE_REQUESTED
        else:
            event = ExitRequested(
                **_event_fields(aggregate, request.now_ms),
                reason=decision.reason,
            )
            status = LifecycleMaintenanceStatus.EXIT_REQUESTED
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )
        return LifecycleMaintenanceResult(status=status, event_id=event.event_id)

    return LifecycleMaintenanceResult(status=LifecycleMaintenanceStatus.NO_CHANGE)


def _event_fields(
    aggregate: TradeAggregate,
    occurred_at_ms: int,
) -> _EventFields:
    sequence = aggregate.last_event_sequence + 1
    return {
        "event_id": f"event:{aggregate.identity.ticket_id}:{sequence}",
        "ticket_id": aggregate.identity.ticket_id,
        "sequence": sequence,
        "occurred_at_ms": occurred_at_ms,
    }


async def _maintain_owner_reduced_position(
    uow: KernelUnitOfWork,
    aggregate: TradeAggregate,
    profile: ExitProfile,
    request: LifecycleMaintenanceRequest,
) -> LifecycleMaintenanceResult:
    """Continue original guards then price-only BE, without reading a retired TP."""
    facts, ctx = request.facts, aggregate.owner_reduction_context
    assert ctx is not None
    no_change = LifecycleMaintenanceResult(status=LifecycleMaintenanceStatus.NO_CHANGE)
    if (
        facts.position_quantity != aggregate.position_qty
        or facts.position_quantity <= 0
        or facts.tp1_filled_quantity != aggregate.tp1_filled_qty
    ):
        await uow.aggregates.expedite_reconciliation(
            aggregate.identity.ticket_id, due_at_ms=request.now_ms
        )
        return no_change
    if facts.market_facts is not None:
        decision = evaluate_profile_pre_tp1_exit(
            profile=profile,
            market_facts=facts.market_facts,
            observed_at_ms=facts.observed_at_ms,
            pre_tp1_reclaim_price=aggregate.ticket.pre_tp1_reclaim_price,
            exposure_session_end_ms=aggregate.ticket.exposure_session_end_ms,
        )
        if decision.kind is ExitDecisionKind.EXIT:
            event = ExitRequested(
                **_event_fields(aggregate, request.now_ms), reason=decision.reason
            )
            await uow.commit_reduction(
                event=event,
                reduction=reduce_event(aggregate, event),
                expected_version=aggregate.version,
            )
            return LifecycleMaintenanceResult(
                status=LifecycleMaintenanceStatus.EXIT_REQUESTED,
                event_id=event.event_id,
            )
    price, observed, valid = (
        facts.contract_market_price,
        facts.contract_price_observed_at_ms,
        facts.contract_price_valid_until_ms,
    )
    if (
        facts.contract_price_blocker is not None
        or price is None
        or not price.is_finite()
        or price <= 0
        or observed is None
        or valid is None
        or not ctx.last_reduction_observed_at_ms < observed <= request.now_ms < valid
        or not 0 < valid - observed <= 30000
        or ctx.price_condition_satisfied
        or ctx.original_tp_price is None
        or aggregate.tp1_exchange_order_id is not None
        or aggregate.active_stop_price is None
        or aggregate.average_fill_price is None
        or facts.active_stop_quantity != aggregate.position_qty
    ):
        return no_change
    long = profile.position_side == "long"
    if price < ctx.original_tp_price if long else price > ctx.original_tp_price:
        return no_change
    floor = calculate_cost_adjusted_break_even(
        side=profile.position_side,
        entry_average_price=aggregate.post_fill_exit_plan.entry_price
        if aggregate.post_fill_exit_plan
        else aggregate.average_fill_price,
        runner_quantity=aggregate.position_qty,
        allocated_entry_fee_quote=facts.allocated_entry_fee_quote,
        exit_taker_fee_rate=facts.exit_taker_fee_rate,
        price_tick=facts.price_tick,
        slippage_buffer_ticks=profile.break_even_floor.slippage_buffer_ticks,
    )
    floor = (
        max(floor, aggregate.active_stop_price)
        if long
        else min(floor, aggregate.active_stop_price)
    )
    mark = facts.current_market_price
    if mark is None or not mark.is_finite() or mark <= 0:
        return no_change
    if min(price, mark) <= floor if long else max(price, mark) >= floor:
        exit_event = ExitRequested(
            **_event_fields(aggregate, request.now_ms), reason="break_even_crossed"
        )
        await uow.commit_reduction(
            event=exit_event,
            reduction=reduce_event(aggregate, exit_event),
            expected_version=aggregate.version,
        )
        return LifecycleMaintenanceResult(
            status=LifecycleMaintenanceStatus.EXIT_REQUESTED,
            event_id=exit_event.event_id,
        )
    condition = OwnerReductionPriceSatisfied(
        **_event_fields(aggregate, request.now_ms),
        operation_id=ctx.operation_id,
        observed_price=price,
        observed_at_ms=observed,
        valid_until_ms=valid,
        proposed_stop=floor,
        source_digest=canonical_digest(
            {
                "domain": aggregate.identity.netting_domain.model_dump(mode="json"),
                "source": "binance_futures_contract_ticker_v2",
                "price": str(price),
                "observed_at_ms": observed,
                "valid_until_ms": valid,
                "operation_id": ctx.operation_id,
            }
        ),
    )
    await uow.commit_reduction(
        event=condition,
        reduction=reduce_event(aggregate, condition),
        expected_version=aggregate.version,
    )
    return LifecycleMaintenanceResult(status=LifecycleMaintenanceStatus.BREAK_EVEN_REQUESTED,event_id=condition.event_id)
