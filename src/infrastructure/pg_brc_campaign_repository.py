"""PG repository for Bounded Risk Campaign state and evidence."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.bounded_risk_campaign import (
    BrcOperatorActionLedger,
    BrcCampaignStatus,
    BoundedRiskCampaign,
    MockPnlEvent,
    PlaybookSwitchDecision,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGBrcCampaignEventORM,
    PGBrcCampaignORM,
    PGBrcMockPnlEventORM,
    PGBrcOperatorActionORM,
    PGBrcPlaybookSwitchDecisionORM,
)


class PgBrcCampaignRepository:
    """PG persistence for BRC campaign snapshots and append-only logs."""

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

    async def get_current_campaign(self) -> Optional[BoundedRiskCampaign]:
        async with self._session_maker() as session:
            stmt = (
                select(PGBrcCampaignORM)
                .where(PGBrcCampaignORM.status != BrcCampaignStatus.ENDED.value)
                .order_by(PGBrcCampaignORM.created_at_ms.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._to_campaign(row) if row is not None else None

    async def get_latest_campaign(self) -> Optional[BoundedRiskCampaign]:
        async with self._session_maker() as session:
            stmt = (
                select(PGBrcCampaignORM)
                .order_by(PGBrcCampaignORM.created_at_ms.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._to_campaign(row) if row is not None else None

    async def save_campaign(self, campaign: BoundedRiskCampaign) -> BoundedRiskCampaign:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(PGBrcCampaignORM, campaign.campaign_id, with_for_update=True)
                payload = campaign.model_dump(mode="json")
                if row is None:
                    row = PGBrcCampaignORM(campaign_id=campaign.campaign_id)
                    session.add(row)
                row.status = campaign.status.value
                row.current_playbook_id = campaign.current_playbook_id
                row.bucket_json = dict(payload["bucket"])
                row.risk_envelope_json = dict(payload["risk_envelope"])
                row.realized_pnl = campaign.realized_pnl
                row.attempt_count = campaign.attempt_count
                row.attempts_json = list(payload["attempts"])
                row.outcome = campaign.outcome.value if campaign.outcome is not None else None
                row.created_at_ms = campaign.created_at_ms
                row.updated_at_ms = campaign.updated_at_ms
                row.finalized_at_ms = campaign.finalized_at_ms
                await session.flush()
                return self._to_campaign(row)

    async def append_switch_decision(
        self,
        decision: PlaybookSwitchDecision,
    ) -> PlaybookSwitchDecision:
        async with self._session_maker() as session:
            async with session.begin():
                sequence_number = await self._next_sequence_number(
                    session=session,
                    orm=PGBrcPlaybookSwitchDecisionORM,
                    campaign_id=decision.campaign_id,
                )
                row = PGBrcPlaybookSwitchDecisionORM(
                    campaign_id=decision.campaign_id,
                    sequence_number=sequence_number,
                    switch_id=decision.switch_id,
                    previous_playbook_id=decision.previous_playbook_id,
                    new_playbook_id=decision.new_playbook_id,
                    decision_result=decision.decision_result.value,
                    reason_category=decision.reason_category,
                    reason_text=decision.reason_text,
                    evidence_refs_json=list(decision.evidence_refs),
                    risk_change_direction=decision.risk_change_direction.value,
                    campaign_pnl_at_switch=decision.campaign_pnl_at_switch,
                    attempt_count_at_switch=decision.attempt_count_at_switch,
                    campaign_status_at_switch=decision.campaign_status_at_switch.value,
                    blocked_reason=decision.blocked_reason,
                    inferred_fields_json=dict(decision.inferred_fields),
                    decided_by=decision.decided_by,
                    switched_at_ms=decision.switched_at_ms,
                    created_at_ms=decision.switched_at_ms,
                )
                session.add(row)
                await session.flush()
                return self._to_switch_decision(row)

    async def append_campaign_event(
        self,
        *,
        campaign_id: str,
        event_type: str,
        occurred_at_ms: int,
        symbol: Optional[str] = None,
        attempt_id: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        async with self._session_maker() as session:
            async with session.begin():
                sequence_number = await self._next_sequence_number(
                    session=session,
                    orm=PGBrcCampaignEventORM,
                    campaign_id=campaign_id,
                )
                row = PGBrcCampaignEventORM(
                    campaign_id=campaign_id,
                    sequence_number=sequence_number,
                    event_type=event_type,
                    symbol=symbol,
                    attempt_id=attempt_id,
                    reason=reason,
                    metadata_json=dict(metadata or {}),
                    occurred_at_ms=occurred_at_ms,
                    created_at_ms=occurred_at_ms,
                )
                session.add(row)
                await session.flush()
                return self._to_event(row)

    async def append_mock_pnl_event(self, event: MockPnlEvent) -> MockPnlEvent:
        async with self._session_maker() as session:
            async with session.begin():
                sequence_number = await self._next_sequence_number(
                    session=session,
                    orm=PGBrcMockPnlEventORM,
                    campaign_id=event.campaign_id,
                )
                row = PGBrcMockPnlEventORM(
                    campaign_id=event.campaign_id,
                    sequence_number=sequence_number,
                    event_id=event.event_id,
                    amount=event.amount,
                    cumulative_pnl=event.cumulative_pnl,
                    source=event.source.value,
                    reason=event.reason,
                    triggered_state=event.triggered_state.value if event.triggered_state else None,
                    occurred_at_ms=event.occurred_at_ms,
                    created_at_ms=event.occurred_at_ms,
                )
                session.add(row)
                await session.flush()
                return self._to_mock_pnl_event(row)

    async def list_switch_decisions(self, campaign_id: str) -> list[PlaybookSwitchDecision]:
        async with self._session_maker() as session:
            stmt = (
                select(PGBrcPlaybookSwitchDecisionORM)
                .where(PGBrcPlaybookSwitchDecisionORM.campaign_id == campaign_id)
                .order_by(PGBrcPlaybookSwitchDecisionORM.sequence_number.asc())
            )
            result = await session.execute(stmt)
            return [self._to_switch_decision(row) for row in result.scalars().all()]

    async def list_campaign_events(self, campaign_id: str) -> list[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = (
                select(PGBrcCampaignEventORM)
                .where(PGBrcCampaignEventORM.campaign_id == campaign_id)
                .order_by(PGBrcCampaignEventORM.sequence_number.asc())
            )
            result = await session.execute(stmt)
            return [self._to_event(row) for row in result.scalars().all()]

    async def list_mock_pnl_events(self, campaign_id: str) -> list[MockPnlEvent]:
        async with self._session_maker() as session:
            stmt = (
                select(PGBrcMockPnlEventORM)
                .where(PGBrcMockPnlEventORM.campaign_id == campaign_id)
                .order_by(PGBrcMockPnlEventORM.sequence_number.asc())
            )
            result = await session.execute(stmt)
            return [self._to_mock_pnl_event(row) for row in result.scalars().all()]

    async def save_operator_action(
        self,
        action: BrcOperatorActionLedger,
    ) -> BrcOperatorActionLedger:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(PGBrcOperatorActionORM, action.action_id, with_for_update=True)
                payload = action.model_dump(mode="json")
                if row is None:
                    row = PGBrcOperatorActionORM(action_id=action.action_id)
                    session.add(row)
                row.campaign_id = action.campaign_id
                row.plan_id = action.plan_id
                row.source_text = action.source_text
                row.draft_action = action.draft_action.value
                row.http_method = action.http_method
                row.endpoint_path = action.endpoint_path
                row.executable = action.executable
                row.confirmation_phrase_id = action.confirmation_phrase_id
                row.confirmation_required = action.confirmation_required
                row.confirmation_matched = action.confirmation_matched
                row.confirmed_by = action.confirmed_by
                row.decision_result = action.decision_result.value
                row.blocked_reason = action.blocked_reason
                row.plan_json = dict(payload["plan_json"])
                row.result_json = dict(payload["result_json"]) if payload.get("result_json") else None
                row.result_summary_json = (
                    dict(payload["result_summary_json"])
                    if payload.get("result_summary_json")
                    else None
                )
                row.mutation_executed = action.mutation_executed
                row.withdrawal_executed = action.withdrawal_executed
                row.live_ready = action.live_ready
                row.created_at_ms = action.created_at_ms
                row.executed_at_ms = action.executed_at_ms
                await session.flush()
                return self._to_operator_action(row)

    async def get_operator_action(self, action_id: str) -> Optional[BrcOperatorActionLedger]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcOperatorActionORM, action_id)
            return self._to_operator_action(row) if row is not None else None

    async def list_operator_actions(
        self,
        *,
        campaign_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[BrcOperatorActionLedger]:
        async with self._session_maker() as session:
            stmt = select(PGBrcOperatorActionORM)
            if campaign_id is not None:
                stmt = stmt.where(PGBrcOperatorActionORM.campaign_id == campaign_id)
            stmt = stmt.order_by(PGBrcOperatorActionORM.created_at_ms.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._to_operator_action(row) for row in result.scalars().all()]

    @staticmethod
    async def _next_sequence_number(
        *,
        session: AsyncSession,
        orm,
        campaign_id: str,
    ) -> int:
        stmt = select(func.max(orm.sequence_number)).where(orm.campaign_id == campaign_id)
        result = await session.execute(stmt)
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    @staticmethod
    def _to_campaign(row: PGBrcCampaignORM) -> BoundedRiskCampaign:
        return BoundedRiskCampaign.model_validate(
            {
                "campaign_id": row.campaign_id,
                "status": row.status,
                "current_playbook_id": row.current_playbook_id,
                "bucket": dict(row.bucket_json or {}),
                "risk_envelope": dict(row.risk_envelope_json or {}),
                "realized_pnl": row.realized_pnl,
                "attempt_count": row.attempt_count,
                "attempts": list(row.attempts_json or []),
                "outcome": row.outcome,
                "created_at_ms": row.created_at_ms,
                "updated_at_ms": row.updated_at_ms,
                "finalized_at_ms": row.finalized_at_ms,
            }
        )

    @staticmethod
    def _to_switch_decision(row: PGBrcPlaybookSwitchDecisionORM) -> PlaybookSwitchDecision:
        return PlaybookSwitchDecision.model_validate(
            {
                "switch_id": row.switch_id,
                "campaign_id": row.campaign_id,
                "previous_playbook_id": row.previous_playbook_id,
                "new_playbook_id": row.new_playbook_id,
                "switched_at_ms": row.switched_at_ms,
                "decided_by": row.decided_by,
                "reason_category": row.reason_category,
                "reason_text": row.reason_text,
                "evidence_refs": list(row.evidence_refs_json or []),
                "risk_change_direction": row.risk_change_direction,
                "campaign_pnl_at_switch": row.campaign_pnl_at_switch,
                "attempt_count_at_switch": row.attempt_count_at_switch,
                "campaign_status_at_switch": row.campaign_status_at_switch,
                "decision_result": row.decision_result,
                "blocked_reason": row.blocked_reason,
                "inferred_fields": dict(row.inferred_fields_json or {}),
            }
        )

    @staticmethod
    def _to_event(row: PGBrcCampaignEventORM) -> dict[str, Any]:
        return {
            "campaign_id": row.campaign_id,
            "sequence_number": int(row.sequence_number),
            "event_type": row.event_type,
            "symbol": row.symbol,
            "attempt_id": row.attempt_id,
            "reason": row.reason,
            "metadata": dict(row.metadata_json or {}),
            "occurred_at_ms": int(row.occurred_at_ms),
        }

    @staticmethod
    def _to_mock_pnl_event(row: PGBrcMockPnlEventORM) -> MockPnlEvent:
        return MockPnlEvent.model_validate(
            {
                "event_id": row.event_id,
                "campaign_id": row.campaign_id,
                "amount": row.amount,
                "cumulative_pnl": row.cumulative_pnl,
                "source": row.source,
                "reason": row.reason,
                "occurred_at_ms": row.occurred_at_ms,
                "triggered_state": row.triggered_state,
            }
        )

    @staticmethod
    def _to_operator_action(row: PGBrcOperatorActionORM) -> BrcOperatorActionLedger:
        return BrcOperatorActionLedger.model_validate(
            {
                "action_id": row.action_id,
                "campaign_id": row.campaign_id,
                "plan_id": row.plan_id,
                "source_text": row.source_text,
                "draft_action": row.draft_action,
                "http_method": row.http_method,
                "endpoint_path": row.endpoint_path,
                "executable": row.executable,
                "confirmation_phrase_id": row.confirmation_phrase_id,
                "confirmation_required": row.confirmation_required,
                "confirmation_matched": row.confirmation_matched,
                "confirmed_by": row.confirmed_by,
                "decision_result": row.decision_result,
                "blocked_reason": row.blocked_reason,
                "plan_json": dict(row.plan_json or {}),
                "result_json": dict(row.result_json) if row.result_json is not None else None,
                "result_summary_json": (
                    dict(row.result_summary_json)
                    if row.result_summary_json is not None
                    else None
                ),
                "mutation_executed": row.mutation_executed,
                "withdrawal_executed": row.withdrawal_executed,
                "live_ready": row.live_ready,
                "created_at_ms": row.created_at_ms,
                "executed_at_ms": row.executed_at_ms,
            }
        )
