"""Skeleton auto-publisher for LLM advisory events.

This module converts already-trusted system facts into advisory events. It is a
one-way bridge into the LLM advisory plane and must not feed advisory output
back into strategy execution, OrderCandidate creation, ExecutionIntent creation,
orders, exchange calls, transfers, or withdrawals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.llm_advisory_plane import LlmAdvisoryPlaneService
from src.application.llm_context_packet_builder import (
    build_llm_advisory_event,
    build_llm_context_packet,
    build_trade_review_context_packet,
)
from src.domain.llm_advisory import (
    LlmAdvisoryAllowedAction,
    LlmAdvisoryDeliveryChannel,
    LlmAdvisoryResult,
    LlmConsumableEvent,
    LlmConsumableEventType,
)
from src.domain.right_tail_review import RightTailReviewSummary


@dataclass(frozen=True)
class LlmEventAutoPublishRequest:
    event_type: LlmConsumableEventType
    source_type: str
    source_id: str
    now_ms: int
    severity: str = "info"
    symbol: str | None = None
    timeframe: str | None = None
    strategy_family_ids: list[str] | None = None
    market: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    strategies: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    external_facts: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    source_refs: list[str] | None = None
    delivery_policy: list[LlmAdvisoryDeliveryChannel] | None = None
    dedupe_key: str | None = None


class LlmEventAutoPublisher:
    """Build and optionally submit advisory-only events."""

    def __init__(self, *, service: LlmAdvisoryPlaneService) -> None:
        self._service = service

    async def publish(self, request: LlmEventAutoPublishRequest) -> LlmAdvisoryResult:
        event = build_auto_advisory_event(request)
        return await self._service.consume_event(event)

    async def publish_strategy_candidate_observed(
        self,
        *,
        source_id: str,
        now_ms: int,
        symbol: str,
        timeframe: str,
        strategy_family_ids: list[str],
        market: dict[str, Any],
        runtime: dict[str, Any] | None = None,
        audit: dict[str, Any] | None = None,
        push_to_feishu: bool = False,
    ) -> LlmAdvisoryResult:
        return await self.publish(
            LlmEventAutoPublishRequest(
                event_type=LlmConsumableEventType.STRATEGY_CANDIDATE_OBSERVED,
                source_type="strategy_signal_path",
                source_id=source_id,
                now_ms=now_ms,
                symbol=symbol,
                timeframe=timeframe,
                strategy_family_ids=strategy_family_ids,
                market=market,
                runtime=runtime,
                strategies={"strategy_family_ids": list(strategy_family_ids)},
                audit=audit,
                delivery_policy=_delivery(push_to_feishu),
                dedupe_key=f"strategy-candidate:{source_id}",
            )
        )

    async def publish_final_gate_blocked(
        self,
        *,
        source_id: str,
        now_ms: int,
        symbol: str | None,
        strategy_family_ids: list[str],
        blockers: list[str],
        warnings: list[str] | None = None,
        push_to_feishu: bool = False,
    ) -> LlmAdvisoryResult:
        return await self.publish(
            LlmEventAutoPublishRequest(
                event_type=LlmConsumableEventType.FINAL_GATE_BLOCKED,
                source_type="runtime_final_gate",
                source_id=source_id,
                now_ms=now_ms,
                severity="warning",
                symbol=symbol,
                strategy_family_ids=strategy_family_ids,
                audit={
                    "final_gate_blockers": list(blockers),
                    "final_gate_warnings": list(warnings or []),
                    "llm_must_not_override_final_gate": True,
                },
                delivery_policy=_delivery(push_to_feishu),
                dedupe_key=f"final-gate-blocked:{source_id}",
            )
        )

    async def publish_reconciliation_mismatch(
        self,
        *,
        source_id: str,
        now_ms: int,
        symbol: str | None,
        mismatch_facts: dict[str, Any],
        push_to_feishu: bool = False,
    ) -> LlmAdvisoryResult:
        return await self.publish(
            LlmEventAutoPublishRequest(
                event_type=LlmConsumableEventType.RECONCILIATION_MISMATCH,
                source_type="reconciliation",
                source_id=source_id,
                now_ms=now_ms,
                severity="warning",
                symbol=symbol,
                audit={
                    "mismatch_facts": dict(mismatch_facts),
                    "llm_is_not_reconciliation_source": True,
                },
                delivery_policy=_delivery(push_to_feishu),
                dedupe_key=f"reconciliation-mismatch:{source_id}",
            )
        )

    async def publish_trade_closed_review(
        self,
        *,
        source_id: str,
        now_ms: int,
        summary: RightTailReviewSummary,
        symbol: str | None = None,
        strategy_family_ids: list[str] | None = None,
        push_to_feishu: bool = False,
    ) -> LlmAdvisoryResult:
        packet = build_trade_review_context_packet(
            summary=summary,
            now_ms=now_ms,
            packet_id=f"llm-trade-review-packet-{source_id}",
            audit={"source": "right_tail_review_summary"},
        )
        event = build_llm_advisory_event(
            event_type=LlmConsumableEventType.TRADE_CLOSED,
            source_type="trade_review",
            source_id=source_id,
            now_ms=now_ms,
            context_packet=packet,
            allowed_llm_actions=_default_actions(LlmConsumableEventType.TRADE_CLOSED),
            delivery_policy=_delivery(push_to_feishu),
            severity="info",
            symbol=symbol,
            strategy_family_ids=list(strategy_family_ids or []),
            dedupe_key=f"trade-closed-review:{source_id}",
        )
        return await self._service.consume_event(event)


def build_auto_advisory_event(
    request: LlmEventAutoPublishRequest,
) -> LlmConsumableEvent:
    packet = build_llm_context_packet(
        now_ms=request.now_ms,
        market=request.market,
        runtime=request.runtime,
        strategies=request.strategies,
        audit={
            **dict(request.audit or {}),
            "auto_published_to_llm_advisory": True,
            "llm_not_execution_authority": True,
        },
        external_facts=request.external_facts,
        review=request.review,
        source_refs=request.source_refs,
    )
    return build_llm_advisory_event(
        event_type=request.event_type,
        source_type=request.source_type,
        source_id=request.source_id,
        now_ms=request.now_ms,
        context_packet=packet,
        allowed_llm_actions=_default_actions(request.event_type),
        delivery_policy=request.delivery_policy,
        severity=request.severity,
        symbol=request.symbol,
        timeframe=request.timeframe,
        strategy_family_ids=request.strategy_family_ids,
        dedupe_key=request.dedupe_key,
    )


def _default_actions(
    event_type: LlmConsumableEventType,
) -> list[LlmAdvisoryAllowedAction]:
    if event_type in {
        LlmConsumableEventType.MARKET_REGIME_CHANGED,
        LlmConsumableEventType.STRATEGY_CANDIDATE_OBSERVED,
        LlmConsumableEventType.ORDER_CANDIDATE_CREATED,
    }:
        return [
            LlmAdvisoryAllowedAction.EXPLAIN_MARKET_CONTEXT,
            LlmAdvisoryAllowedAction.RECOMMEND_REGISTERED_STRATEGY_FAMILY,
        ]
    if event_type in {
        LlmConsumableEventType.FINAL_GATE_BLOCKED,
        LlmConsumableEventType.PROTECTION_ANOMALY_DETECTED,
        LlmConsumableEventType.RECONCILIATION_MISMATCH,
    }:
        return [
            LlmAdvisoryAllowedAction.EXPLAIN_BLOCKER,
            LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT,
        ]
    if event_type == LlmConsumableEventType.TRADE_CLOSED:
        return [LlmAdvisoryAllowedAction.REVIEW_CLOSED_TRADE]
    return [LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT]


def _delivery(push_to_feishu: bool) -> list[LlmAdvisoryDeliveryChannel]:
    if push_to_feishu:
        return [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
    return [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
