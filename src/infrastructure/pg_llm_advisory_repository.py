"""PG repository for the event-driven LLM advisory plane."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.llm_advisory import (
    LlmAdvisoryRecommendation,
    LlmConsumableEvent,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGLlmAdvisoryRecommendationORM,
    PGLlmConsumableEventORM,
)


class PgLlmAdvisoryRepository:
    """Persistence for typed LLM advisory events and recommendations."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def save_event(self, event: LlmConsumableEvent) -> LlmConsumableEvent:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(PGLlmConsumableEventORM, event.event_id, with_for_update=True)
                payload = event.model_dump(mode="json")
                if row is None:
                    row = PGLlmConsumableEventORM(event_id=event.event_id)
                    session.add(row)
                row.event_type = event.event_type.value
                row.source_type = event.source_type
                row.source_id = event.source_id
                row.severity = event.severity
                row.symbol = event.symbol
                row.timeframe = event.timeframe
                row.strategy_family_ids = list(payload["strategy_family_ids"])
                row.dedupe_key = event.dedupe_key
                row.occurred_at_ms = event.occurred_at_ms
                row.context_packet = dict(payload["context_packet"])
                row.allowed_llm_actions = list(payload["allowed_llm_actions"])
                row.delivery_policy = list(payload["delivery_policy"])
                row.created_at_ms = event.created_at_ms
                row.not_execution_authority = event.not_execution_authority
                row.owner_action_enabled = event.owner_action_enabled
                row.execution_intent_created = event.execution_intent_created
                row.order_created = event.order_created
                row.exchange_called = event.exchange_called
                row.withdrawal_instruction_created = event.withdrawal_instruction_created
                row.transfer_instruction_created = event.transfer_instruction_created
                row.live_ready = event.live_ready
                await session.flush()
                return self._to_event(row)

    async def get_event(self, event_id: str) -> Optional[LlmConsumableEvent]:
        async with self._session_maker() as session:
            row = await session.get(PGLlmConsumableEventORM, event_id)
            return self._to_event(row) if row is not None else None

    async def list_events(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
    ) -> list[LlmConsumableEvent]:
        async with self._session_maker() as session:
            stmt = select(PGLlmConsumableEventORM)
            if event_type is not None:
                stmt = stmt.where(PGLlmConsumableEventORM.event_type == event_type)
            stmt = stmt.order_by(PGLlmConsumableEventORM.created_at_ms.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._to_event(row) for row in result.scalars().all()]

    async def save_recommendation(
        self,
        recommendation: LlmAdvisoryRecommendation,
    ) -> LlmAdvisoryRecommendation:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGLlmAdvisoryRecommendationORM,
                    recommendation.recommendation_id,
                    with_for_update=True,
                )
                payload = recommendation.model_dump(mode="json")
                if row is None:
                    row = PGLlmAdvisoryRecommendationORM(
                        recommendation_id=recommendation.recommendation_id
                    )
                    session.add(row)
                row.event_id = recommendation.event_id
                row.event_type = recommendation.event_type.value
                row.source_type = recommendation.source_type
                row.source_id = recommendation.source_id
                row.recommendation_type = recommendation.recommendation_type.value
                row.status = recommendation.status.value
                row.summary = recommendation.summary
                row.confidence = recommendation.confidence
                row.recommended_strategy_family_ids = list(payload["recommended_strategy_family_ids"])
                row.observe_only_strategy_family_ids = list(payload["observe_only_strategy_family_ids"])
                row.reason_codes = list(payload["reason_codes"])
                row.risk_notes = list(payload["risk_notes"])
                row.missing_facts = list(payload["missing_facts"])
                row.research_idea_notes = list(payload["research_idea_notes"])
                row.review_notes = list(payload["review_notes"])
                row.feishu_card_type = recommendation.feishu_card_type.value
                row.provider_name = recommendation.provider_name
                row.model_name = recommendation.model_name
                row.prompt_version = recommendation.prompt_version
                row.raw_response_summary = dict(payload["raw_response_summary"])
                row.delivery_channels = list(payload["delivery_channels"])
                row.owner_action_route = recommendation.owner_action_route
                row.owner_action_enabled = recommendation.owner_action_enabled
                row.pushed_to_feishu_at_ms = recommendation.pushed_to_feishu_at_ms
                row.push_error = recommendation.push_error
                row.created_at_ms = recommendation.created_at_ms
                row.updated_at_ms = recommendation.updated_at_ms
                row.not_execution_authority = recommendation.not_execution_authority
                row.strategy_execution_authorized = recommendation.strategy_execution_authorized
                row.execution_intent_created = recommendation.execution_intent_created
                row.order_created = recommendation.order_created
                row.exchange_called = recommendation.exchange_called
                row.withdrawal_instruction_created = recommendation.withdrawal_instruction_created
                row.transfer_instruction_created = recommendation.transfer_instruction_created
                row.live_ready = recommendation.live_ready
                await session.flush()
                return self._to_recommendation(row)

    async def get_recommendation(
        self,
        recommendation_id: str,
    ) -> Optional[LlmAdvisoryRecommendation]:
        async with self._session_maker() as session:
            row = await session.get(PGLlmAdvisoryRecommendationORM, recommendation_id)
            return self._to_recommendation(row) if row is not None else None

    async def list_recommendations(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[LlmAdvisoryRecommendation]:
        async with self._session_maker() as session:
            stmt = select(PGLlmAdvisoryRecommendationORM)
            if event_type is not None:
                stmt = stmt.where(PGLlmAdvisoryRecommendationORM.event_type == event_type)
            if status is not None:
                stmt = stmt.where(PGLlmAdvisoryRecommendationORM.status == status)
            stmt = stmt.order_by(PGLlmAdvisoryRecommendationORM.created_at_ms.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._to_recommendation(row) for row in result.scalars().all()]

    @staticmethod
    def _to_event(row: PGLlmConsumableEventORM) -> LlmConsumableEvent:
        return LlmConsumableEvent.model_validate(
            {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "severity": row.severity,
                "symbol": row.symbol,
                "timeframe": row.timeframe,
                "strategy_family_ids": list(row.strategy_family_ids or []),
                "dedupe_key": row.dedupe_key,
                "occurred_at_ms": row.occurred_at_ms,
                "context_packet": dict(row.context_packet or {}),
                "allowed_llm_actions": list(row.allowed_llm_actions or []),
                "delivery_policy": list(row.delivery_policy or []),
                "created_at_ms": row.created_at_ms,
                "not_execution_authority": row.not_execution_authority,
                "owner_action_enabled": row.owner_action_enabled,
                "execution_intent_created": row.execution_intent_created,
                "order_created": row.order_created,
                "exchange_called": row.exchange_called,
                "withdrawal_instruction_created": row.withdrawal_instruction_created,
                "transfer_instruction_created": row.transfer_instruction_created,
                "live_ready": row.live_ready,
            }
        )
    @staticmethod
    def _to_recommendation(
        row: PGLlmAdvisoryRecommendationORM,
    ) -> LlmAdvisoryRecommendation:
        return LlmAdvisoryRecommendation.model_validate(
            {
                "recommendation_id": row.recommendation_id,
                "event_id": row.event_id,
                "event_type": row.event_type,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "recommendation_type": row.recommendation_type,
                "status": row.status,
                "summary": row.summary,
                "confidence": row.confidence,
                "recommended_strategy_family_ids": list(row.recommended_strategy_family_ids or []),
                "observe_only_strategy_family_ids": list(row.observe_only_strategy_family_ids or []),
                "reason_codes": list(row.reason_codes or []),
                "risk_notes": list(row.risk_notes or []),
                "missing_facts": list(row.missing_facts or []),
                "research_idea_notes": list(row.research_idea_notes or []),
                "review_notes": list(row.review_notes or []),
                "feishu_card_type": row.feishu_card_type,
                "provider_name": row.provider_name,
                "model_name": row.model_name,
                "prompt_version": row.prompt_version,
                "raw_response_summary": dict(row.raw_response_summary or {}),
                "delivery_channels": list(row.delivery_channels or []),
                "owner_action_route": row.owner_action_route,
                "owner_action_enabled": row.owner_action_enabled,
                "pushed_to_feishu_at_ms": row.pushed_to_feishu_at_ms,
                "push_error": row.push_error,
                "created_at_ms": row.created_at_ms,
                "updated_at_ms": row.updated_at_ms,
                "not_execution_authority": row.not_execution_authority,
                "strategy_execution_authorized": row.strategy_execution_authorized,
                "execution_intent_created": row.execution_intent_created,
                "order_created": row.order_created,
                "exchange_called": row.exchange_called,
                "withdrawal_instruction_created": row.withdrawal_instruction_created,
                "transfer_instruction_created": row.transfer_instruction_created,
                "live_ready": row.live_ready,
            }
        )
