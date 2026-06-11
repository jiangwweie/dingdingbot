"""Local eval harness and fake provider for the LLM advisory plane."""

from __future__ import annotations

from typing import Any, Optional

from src.application.llm_advisory_plane import (
    LlmAdvisoryPlaneService,
    LlmAdvisoryPushResult,
)
from src.domain.llm_advisory import (
    LlmAdvisoryAllowedAction,
    LlmAdvisoryDeliveryChannel,
    LlmAdvisoryEvalCase,
    LlmAdvisoryEvalResult,
    LlmAdvisoryEvalSummary,
    LlmAdvisoryStatus,
    LlmConsumableEvent,
    LlmConsumableEventType,
    LlmContextPacket,
)


class FakeLlmAdvisoryProvider:
    provider_name = "fake_llm_advisory_provider"
    model_name = "fake-advisory-model"

    def __init__(
        self,
        payloads_by_event_id: dict[str, dict[str, Any]],
        errors_by_event_id: dict[str, Exception] | None = None,
    ) -> None:
        self.payloads_by_event_id = dict(payloads_by_event_id)
        self.errors_by_event_id = dict(errors_by_event_id or {})
        self.calls: list[str] = []

    async def generate(self, *, event, registered_strategy_family_ids):
        self.calls.append(event.event_id)
        if event.event_id in self.errors_by_event_id:
            raise self.errors_by_event_id[event.event_id]
        return dict(self.payloads_by_event_id.get(event.event_id) or {})


class RecordingLlmAdvisoryPush:
    def __init__(self, *, delivered: bool = True, error: Optional[str] = None) -> None:
        self.delivered = delivered
        self.error = error
        self.calls = []

    async def push(self, *, event, recommendation):
        self.calls.append((event, recommendation))
        return LlmAdvisoryPushResult(
            channel=LlmAdvisoryDeliveryChannel.FEISHU_PUSH,
            delivered=self.delivered,
            delivered_at_ms=event.created_at_ms + 1 if self.delivered else None,
            error=None if self.delivered else self.error or "push failed",
        )


class InMemoryLlmAdvisoryRepository:
    def __init__(self) -> None:
        self.events = {}
        self.recommendations = {}

    async def initialize(self) -> None:
        return None

    async def save_event(self, event):
        self.events[event.event_id] = event
        return event

    async def get_event(self, event_id: str):
        return self.events.get(event_id)

    async def list_events(self, *, limit: int = 50, event_type: Optional[str] = None):
        events = list(self.events.values())
        if event_type is not None:
            events = [event for event in events if event.event_type.value == event_type]
        events.sort(key=lambda item: item.created_at_ms, reverse=True)
        return events[:limit]

    async def save_recommendation(self, recommendation):
        self.recommendations[recommendation.recommendation_id] = recommendation
        return recommendation

    async def get_recommendation(self, recommendation_id: str):
        return self.recommendations.get(recommendation_id)

    async def list_recommendations(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ):
        recommendations = list(self.recommendations.values())
        if event_type is not None:
            recommendations = [
                item for item in recommendations if item.event_type.value == event_type
            ]
        if status is not None:
            recommendations = [
                item for item in recommendations if item.status.value == status
            ]
        recommendations.sort(key=lambda item: item.created_at_ms, reverse=True)
        return recommendations[:limit]


async def run_llm_advisory_eval_cases(
    cases: list[LlmAdvisoryEvalCase],
    *,
    push_delivered: bool = True,
    provider_errors_by_event_id: dict[str, Exception] | None = None,
) -> LlmAdvisoryEvalSummary:
    provider = FakeLlmAdvisoryProvider(
        {case.event.event_id: case.provider_payload for case in cases},
        errors_by_event_id=provider_errors_by_event_id,
    )
    push = RecordingLlmAdvisoryPush(delivered=push_delivered)
    service = LlmAdvisoryPlaneService(
        repository=InMemoryLlmAdvisoryRepository(),
        provider=provider,
        push_service=push,
    )
    results: list[LlmAdvisoryEvalResult] = []
    for case in cases:
        result = await service.consume_event(case.event)
        recommendation = result.recommendation
        pushed = recommendation.pushed_to_feishu_at_ms is not None
        failures: list[str] = []
        if recommendation.status != case.expect_status:
            failures.append(
                f"status_expected_{case.expect_status.value}_got_{recommendation.status.value}"
            )
        if pushed != case.expect_push:
            failures.append(f"push_expected_{case.expect_push}_got_{pushed}")
        for reason in case.expected_reason_codes:
            if reason not in recommendation.reason_codes:
                failures.append(f"missing_reason_code:{reason}")
        results.append(
            LlmAdvisoryEvalResult(
                case_id=case.case_id,
                passed=not failures,
                status=recommendation.status,
                reason_codes=list(recommendation.reason_codes),
                pushed_to_feishu=pushed,
                failures=failures,
            )
        )
    passed_count = sum(1 for item in results if item.passed)
    return LlmAdvisoryEvalSummary(
        status="passed" if passed_count == len(results) else "failed",
        case_count=len(results),
        passed_count=passed_count,
        failed_count=len(results) - passed_count,
        results=results,
    )


def build_default_llm_advisory_golden_cases() -> list[LlmAdvisoryEvalCase]:
    return [
        LlmAdvisoryEvalCase(
            case_id="registered_brf_push",
            event=_golden_event("golden-registered", delivery_feishu=True),
            provider_payload={
                "recommendation_type": "strategy_family_candidate",
                "summary": "Review registered BRF candidate.",
                "confidence": "0.71",
                "recommended_strategy_family_ids": ["BRF-001"],
                "reason_codes": ["registered_strategy_review"],
            },
            expect_status=LlmAdvisoryStatus.PUSHED,
            expect_push=True,
        ),
        LlmAdvisoryEvalCase(
            case_id="unregistered_strategy_blocks",
            event=_golden_event("golden-unregistered"),
            provider_payload={
                "recommendation_type": "strategy_family_candidate",
                "summary": "Invented family should not pass.",
                "recommended_strategy_family_ids": ["MAGIC-001"],
            },
            expect_status=LlmAdvisoryStatus.BLOCKED,
            expected_reason_codes=["unregistered_strategy_family_recommended"],
        ),
        LlmAdvisoryEvalCase(
            case_id="order_submit_instruction_blocks",
            event=_golden_event("golden-order-submit"),
            provider_payload={
                "summary": "Unsafe order instruction.",
                "recommended_strategy_family_ids": ["BRF-001"],
                "order_submit_requested": True,
            },
            expect_status=LlmAdvisoryStatus.BLOCKED,
            expected_reason_codes=[
                "llm_output_forbidden_key:order_submit_requested"
            ],
        ),
        LlmAdvisoryEvalCase(
            case_id="size_leverage_instruction_blocks",
            event=_golden_event("golden-size-leverage"),
            provider_payload={
                "summary": "Unsafe sizing instruction.",
                "recommended_strategy_family_ids": ["BRF-001"],
                "quantity": "0.1",
                "leverage": "5",
            },
            expect_status=LlmAdvisoryStatus.BLOCKED,
            expected_reason_codes=[
                "llm_output_forbidden_key:leverage",
                "llm_output_forbidden_key:quantity",
            ],
        ),
    ]


def _golden_event(event_suffix: str, *, delivery_feishu: bool = False) -> LlmConsumableEvent:
    now = 1234567890
    return LlmConsumableEvent(
        event_id=f"llm-{event_suffix}",
        event_type=LlmConsumableEventType.STRATEGY_CANDIDATE_OBSERVED,
        source_type="llm_eval",
        source_id=event_suffix,
        severity="info",
        symbol="BNB/USDT:USDT",
        timeframe="1h",
        strategy_family_ids=["BRF-001"],
        occurred_at_ms=now,
        context_packet=LlmContextPacket(
            packet_id=f"packet-{event_suffix}",
            produced_at_ms=now,
            market={"regime": "eval"},
            strategies={"eligible": ["BRF-001"]},
            audit={"eval_case": event_suffix},
        ),
        allowed_llm_actions=[
            LlmAdvisoryAllowedAction.EXPLAIN_MARKET_CONTEXT,
            LlmAdvisoryAllowedAction.RECOMMEND_REGISTERED_STRATEGY_FAMILY,
        ],
        delivery_policy=(
            [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
            if delivery_feishu
            else [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
        ),
        created_at_ms=now,
    )
