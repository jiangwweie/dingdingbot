from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.bounded_risk_campaign_service import BrcRuleViolation
from src.application.llm_advisory_plane import (
    LlmAdvisoryPlaneService,
    LlmAdvisoryPushResult,
    format_feishu_advisory_message,
)
from src.application.llm_advisory_cards import build_feishu_advisory_card
from src.application.llm_advisory_safety import evaluate_llm_advisory_output_safety
from src.application.llm_context_packet_builder import (
    build_llm_context_packet,
    build_trade_review_context_packet,
)
from src.domain.llm_advisory import (
    LlmAdvisoryAllowedAction,
    LlmAdvisoryDeliveryChannel,
    LlmAdvisoryRecommendation,
    LlmAdvisoryRecommendationType,
    LlmAdvisoryStatus,
    LlmConsumableEvent,
    LlmConsumableEventType,
    LlmContextPacket,
    LlmFeishuCardType,
)
from src.domain.right_tail_review import (
    RightTailTradePathFacts,
    summarize_right_tail_reviews,
)
from src.interfaces.api_brc_console import advisory_router
from src.interfaces.operator_auth import OperatorSession, require_operator_session


class InMemoryLlmAdvisoryRepo:
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
            recommendations = [item for item in recommendations if item.status.value == status]
        recommendations.sort(key=lambda item: item.created_at_ms, reverse=True)
        return recommendations[:limit]


class FakeProvider:
    provider_name = "fake_llm"
    model_name = "fake-model"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def generate(self, *, event, registered_strategy_family_ids):
        return dict(self.payload)


class FakePush:
    def __init__(self, *, delivered: bool = True) -> None:
        self.delivered = delivered
        self.calls = []

    async def push(self, *, event, recommendation):
        self.calls.append((event, recommendation))
        return LlmAdvisoryPushResult(
            channel=LlmAdvisoryDeliveryChannel.FEISHU_PUSH,
            delivered=self.delivered,
            delivered_at_ms=event.created_at_ms + 1 if self.delivered else None,
            error=None if self.delivered else "push failed",
        )


def _event(*, strategy_family_ids: list[str] | None = None) -> LlmConsumableEvent:
    now = 1234567890
    return LlmConsumableEvent(
        event_id="llm-event-test",
        event_type=LlmConsumableEventType.STRATEGY_CANDIDATE_OBSERVED,
        source_type="unit_test",
        source_id="candidate-1",
        severity="info",
        symbol="BNB/USDT:USDT",
        timeframe="1h",
        strategy_family_ids=strategy_family_ids or ["BRF-001"],
        occurred_at_ms=now,
        context_packet=LlmContextPacket(
            packet_id="packet-1",
            produced_at_ms=now,
            market={"ema60_relation": "below"},
            strategies={"eligible": strategy_family_ids or ["BRF-001"]},
            audit={"final_gate": "preview_only"},
        ),
        allowed_llm_actions=[
            LlmAdvisoryAllowedAction.EXPLAIN_MARKET_CONTEXT,
            LlmAdvisoryAllowedAction.RECOMMEND_REGISTERED_STRATEGY_FAMILY,
        ],
        delivery_policy=[LlmAdvisoryDeliveryChannel.FEISHU_PUSH],
        created_at_ms=now,
    )


@pytest.mark.asyncio
async def test_llm_advisory_recommends_registered_strategy_and_pushes_feishu():
    repo = InMemoryLlmAdvisoryRepo()
    push = FakePush()
    service = LlmAdvisoryPlaneService(
        repository=repo,
        provider=FakeProvider(
            {
                "recommendation_type": "strategy_family_candidate",
                "summary": "BRF is the registered short-side candidate to review.",
                "confidence": "0.73",
                "recommended_strategy_family_ids": ["BRF-001"],
                "observe_only_strategy_family_ids": ["CPM-001"],
                "reason_codes": ["bear_rally_failure_context"],
                "risk_notes": ["Short squeeze risk must remain bounded."],
                "missing_facts": [],
                "research_idea_notes": [],
                "feishu_card_type": "candidate_review",
            }
        ),
        push_service=push,
    )

    result = await service.consume_event(_event())

    recommendation = result.recommendation
    assert recommendation.status == LlmAdvisoryStatus.PUSHED
    assert recommendation.recommendation_type == LlmAdvisoryRecommendationType.STRATEGY_FAMILY_CANDIDATE
    assert recommendation.confidence == Decimal("0.73")
    assert recommendation.recommended_strategy_family_ids == ["BRF-001"]
    assert recommendation.feishu_card_type == LlmFeishuCardType.CANDIDATE_REVIEW
    assert recommendation.owner_action_enabled is False
    assert recommendation.execution_intent_created is False
    assert recommendation.order_created is False
    assert recommendation.exchange_called is False
    assert len(push.calls) == 1
    assert recommendation.recommendation_id in repo.recommendations


@pytest.mark.asyncio
async def test_llm_advisory_blocks_unregistered_strategy_recommendation_without_push():
    repo = InMemoryLlmAdvisoryRepo()
    push = FakePush()
    service = LlmAdvisoryPlaneService(
        repository=repo,
        provider=FakeProvider(
            {
                "recommendation_type": "strategy_family_candidate",
                "summary": "Try an invented strategy.",
                "confidence": "0.9",
                "recommended_strategy_family_ids": ["MAGIC-001"],
            }
        ),
        push_service=push,
    )

    result = await service.consume_event(_event())

    assert result.recommendation.status == LlmAdvisoryStatus.BLOCKED
    assert "unregistered_strategy_family_recommended" in result.recommendation.reason_codes
    assert result.recommendation.recommended_strategy_family_ids == []
    assert push.calls == []


@pytest.mark.asyncio
async def test_llm_advisory_rejects_event_with_unregistered_strategy_id():
    service = LlmAdvisoryPlaneService(
        repository=InMemoryLlmAdvisoryRepo(),
        provider=FakeProvider({"summary": "x"}),
        push_service=FakePush(),
    )

    with pytest.raises(BrcRuleViolation, match="unregistered strategy families"):
        await service.consume_event(_event(strategy_family_ids=["UNKNOWN-001"]))


def test_llm_advisory_recommendation_rejects_execution_authority_flags():
    with pytest.raises(ValueError, match="trading authority"):
        LlmAdvisoryRecommendation(
            recommendation_id="llm-adv-test",
            event_id="llm-event-test",
            event_type=LlmConsumableEventType.OWNER_REQUESTED_ANALYSIS,
            source_type="unit_test",
            source_id="owner",
            recommendation_type=LlmAdvisoryRecommendationType.UNKNOWN,
            status=LlmAdvisoryStatus.GENERATED,
            summary="unsafe",
            confidence=Decimal("0.1"),
            provider_name="fake",
            raw_response_summary={"order_submit_requested": True},
            created_at_ms=1,
            updated_at_ms=1,
        )


def test_llm_context_packet_builder_marks_push_only_safety_boundary():
    packet = build_llm_context_packet(
        raw_packet={"market": {"state": "trend_down"}},
        now_ms=123,
        fallback_packet_id="packet-builder-test",
        runtime={"budget_remaining": "12"},
        strategies={"eligible": ["BRF-001"]},
        audit={"final_gate": "pass"},
    )

    assert packet.packet_id == "packet-builder-test"
    assert packet.market == {"state": "trend_down"}
    assert packet.runtime["budget_remaining"] == "12"
    assert packet.safety["llm_not_execution_authority"] is True
    assert packet.safety["feishu_push_only"] is True


def test_llm_advisory_api_records_push_only_event_without_execution_side_effects():
    app = FastAPI()
    app.include_router(advisory_router)
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=9999999999,
    )
    app.state.llm_advisory_repository = InMemoryLlmAdvisoryRepo()

    with TestClient(app) as client:
        response = client.post(
            "/api/brc/llm/advisory/events",
            json={
                "event_type": "owner_requested_analysis",
                "source_type": "unit_test",
                "source_id": "owner-note-1",
                "context_packet": {
                    "audit": {"question": "summarize blockers"},
                },
                "allowed_llm_actions": ["summarize_audit"],
            },
        )
        inbox_response = client.get("/api/brc/llm/advisory/inbox")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_ready"] is False
    assert payload["event"]["not_execution_authority"] is True
    assert payload["event"]["execution_intent_created"] is False
    assert payload["event"]["order_created"] is False
    assert payload["event"]["exchange_called"] is False
    assert payload["recommendation"]["status"] == "blocked"
    assert payload["recommendation"]["owner_action_enabled"] is False
    assert payload["recommendation"]["strategy_execution_authorized"] is False
    assert payload["recommendation"]["execution_intent_created"] is False
    assert payload["recommendation"]["order_created"] is False
    assert payload["recommendation"]["exchange_called"] is False
    assert inbox_response.status_code == 200
    assert inbox_response.json()["inbox"]["push_only"] is True


def test_llm_output_safety_blocks_order_like_payload():
    report = evaluate_llm_advisory_output_safety(
        {
            "summary": "Unsafe output",
            "recommended_strategy_family_ids": ["BRF-001"],
            "side": "short",
            "leverage": "3",
            "order_submit_requested": True,
        }
    )

    assert report.status == "blocked"
    assert "side" in report.blocked_keys
    assert "leverage" in report.blocked_keys
    assert "order_submit_requested" in report.blocked_keys
    assert report.order_created is False
    assert report.exchange_called is False


@pytest.mark.asyncio
async def test_llm_advisory_blocks_provider_payload_with_execution_instructions():
    service = LlmAdvisoryPlaneService(
        repository=InMemoryLlmAdvisoryRepo(),
        provider=FakeProvider(
            {
                "recommendation_type": "strategy_family_candidate",
                "summary": "Unsafe",
                "recommended_strategy_family_ids": ["BRF-001"],
                "quantity": "0.01",
                "order_submit_requested": True,
            }
        ),
        push_service=FakePush(),
    )

    result = await service.consume_event(_event())

    assert result.recommendation.status == LlmAdvisoryStatus.BLOCKED
    assert result.recommendation.recommended_strategy_family_ids == []
    assert any(
        item.startswith("llm_output_forbidden_key")
        for item in result.recommendation.reason_codes
    )
    assert result.recommendation.order_created is False
    assert result.recommendation.exchange_called is False


def test_feishu_card_template_is_push_only_and_review_oriented():
    recommendation = LlmAdvisoryRecommendation(
        recommendation_id="llm-adv-card",
        event_id="llm-event-test",
        event_type=LlmConsumableEventType.FINAL_GATE_BLOCKED,
        source_type="unit_test",
        source_id="candidate-1",
        recommendation_type=LlmAdvisoryRecommendationType.BLOCKER_EXPLANATION,
        status=LlmAdvisoryStatus.GENERATED,
        summary="Missing trusted active position facts.",
        confidence=Decimal("0.4"),
        missing_facts=["active_positions_count"],
        risk_notes=["Do not rely on manual preview facts for submit."],
        provider_name="fake",
        feishu_card_type=LlmFeishuCardType.FINAL_GATE_BLOCKED,
        created_at_ms=1,
        updated_at_ms=1,
    )

    card = build_feishu_advisory_card(event=_event(), recommendation=recommendation)
    message = format_feishu_advisory_message(event=_event(), recommendation=recommendation)

    assert card.card_type == LlmFeishuCardType.FINAL_GATE_BLOCKED
    assert card.language == "zh_cn"
    assert card.push_only is True
    assert card.owner_action_enabled is False
    assert card.order_created is False
    assert "缺失事实" in card.markdown
    assert "Feishu is push-only" in card.markdown
    assert "No ExecutionIntent" in message


def test_trade_review_context_packet_includes_right_tail_summary():
    summary = summarize_right_tail_reviews(
        [
            RightTailTradePathFacts(
                trade_id="trade-tail",
                symbol="BNB/USDT:USDT",
                side="short",
                entry_price=Decimal("600"),
                exit_price=Decimal("540"),
                mfe_price=Decimal("535"),
                mae_price=Decimal("612"),
                realized_pnl=Decimal("9"),
                max_loss_budget=Decimal("2"),
                opened_at_ms=1,
                closed_at_ms=10,
                runner_preserved=True,
            ),
            RightTailTradePathFacts(
                trade_id="trade-small-loss",
                symbol="BNB/USDT:USDT",
                side="short",
                entry_price=Decimal("600"),
                exit_price=Decimal("606"),
                mfe_price=Decimal("594"),
                mae_price=Decimal("608"),
                realized_pnl=Decimal("-1"),
                max_loss_budget=Decimal("2"),
                opened_at_ms=11,
                closed_at_ms=20,
                runner_preserved=False,
            ),
        ]
    )

    packet = build_trade_review_context_packet(
        summary=summary,
        now_ms=456,
        packet_id="trade-review-packet",
    )

    right_tail = packet.review["right_tail_review"]
    assert right_tail["right_tail_win_count"] == 1
    assert right_tail["small_loss_count"] == 1
    assert right_tail["payoff_asymmetry_present"] is True
    assert packet.review["manual_owner_withdrawal_outside_system"] is True


@pytest.mark.asyncio
async def test_llm_advisory_inbox_summary_counts_status_and_push_failures():
    repo = InMemoryLlmAdvisoryRepo()
    service = LlmAdvisoryPlaneService(
        repository=repo,
        provider=FakeProvider(
            {
                "summary": "Push candidate.",
                "recommended_strategy_family_ids": ["BRF-001"],
                "recommendation_type": "strategy_family_candidate",
            }
        ),
        push_service=FakePush(delivered=False),
    )

    await service.consume_event(_event())
    inbox = await service.inbox_summary()

    assert inbox.push_only is True
    assert inbox.owner_action_enabled is False
    assert inbox.pending_push_failure_count == 1
    assert inbox.status_counts["push_failed"] == 1
    assert inbox.items[0].live_ready is False
