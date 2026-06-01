"""PostgreSQL repository for Owner trial-flow metadata."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.owner_trial_flow import (
    BoundedLiveTrialAuthorizationDraft,
    OwnerRiskAcknowledgement,
    OwnerTrialFlowInfrastructureError,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGBrcBoundedLiveTrialAuthorizationDraftORM,
    PGBrcOwnerRiskAcknowledgementORM,
)


class PgOwnerTrialFlowRepository:
    """Persist Owner trial-flow preparation metadata in PostgreSQL.

    This repository stores audit-critical metadata only. It never creates
    execution intents, orders, runtime state, or permission grants. It also does
    not fall back to SQLite when PostgreSQL is unavailable.
    """

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        try:
            self._session_maker = session_maker or get_pg_session_maker()
        except ValueError as exc:
            raise OwnerTrialFlowInfrastructureError(
                "pg_unavailable",
                f"Owner trial-flow metadata requires PostgreSQL: {exc}",
            ) from exc
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def create_acknowledgement(
        self,
        acknowledgement: OwnerRiskAcknowledgement,
    ) -> OwnerRiskAcknowledgement:
        row = PGBrcOwnerRiskAcknowledgementORM(
            acknowledgement_id=acknowledgement.acknowledgement_id,
            carrier_id=acknowledgement.carrier_id,
            strategy_family_id=acknowledgement.strategy_family_id,
            acknowledged_warning_codes_json=list(acknowledgement.acknowledged_warning_codes),
            owner_id=acknowledgement.owner_id,
            acknowledged_at_ms=acknowledgement.acknowledged_at_ms,
            acknowledgement_scope=acknowledgement.acknowledgement_scope,
            source=acknowledgement.source,
            non_live_metadata_only=acknowledgement.non_live_metadata_only,
            metadata_json=acknowledgement.model_dump(mode="json"),
            created_at_ms=acknowledgement.acknowledged_at_ms,
            updated_at_ms=acknowledgement.acknowledged_at_ms,
        )
        try:
            async with self._session_maker() as session:
                async with session.begin():
                    session.add(row)
                return self._to_acknowledgement(row)
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    async def get_acknowledgement(
        self,
        acknowledgement_id: str,
    ) -> OwnerRiskAcknowledgement | None:
        try:
            async with self._session_maker() as session:
                row = await session.get(PGBrcOwnerRiskAcknowledgementORM, acknowledgement_id)
                return self._to_acknowledgement(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    async def latest_acknowledgement(
        self,
        carrier_id: str,
    ) -> OwnerRiskAcknowledgement | None:
        try:
            async with self._session_maker() as session:
                result = await session.execute(
                    select(PGBrcOwnerRiskAcknowledgementORM)
                    .where(PGBrcOwnerRiskAcknowledgementORM.carrier_id == carrier_id)
                    .order_by(
                        PGBrcOwnerRiskAcknowledgementORM.acknowledged_at_ms.desc(),
                        PGBrcOwnerRiskAcknowledgementORM.acknowledgement_id.desc(),
                    )
                    .limit(1)
                )
                row = result.scalar_one_or_none()
                return self._to_acknowledgement(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    async def upsert_draft(
        self,
        draft: BoundedLiveTrialAuthorizationDraft,
    ) -> BoundedLiveTrialAuthorizationDraft:
        try:
            async with self._session_maker() as session:
                async with session.begin():
                    row = await session.get(
                        PGBrcBoundedLiveTrialAuthorizationDraftORM,
                        draft.draft_id,
                        with_for_update=True,
                    )
                    if row is None:
                        row = PGBrcBoundedLiveTrialAuthorizationDraftORM(draft_id=draft.draft_id)
                        session.add(row)
                    self._apply_draft(row, draft)
                    await session.flush()
                    return self._to_draft(row)
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    async def get_draft(
        self,
        draft_id: str,
    ) -> BoundedLiveTrialAuthorizationDraft | None:
        try:
            async with self._session_maker() as session:
                row = await session.get(PGBrcBoundedLiveTrialAuthorizationDraftORM, draft_id)
                return self._to_draft(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    async def latest_draft(
        self,
        carrier_id: str,
    ) -> BoundedLiveTrialAuthorizationDraft | None:
        try:
            async with self._session_maker() as session:
                result = await session.execute(
                    select(PGBrcBoundedLiveTrialAuthorizationDraftORM)
                    .where(PGBrcBoundedLiveTrialAuthorizationDraftORM.carrier_id == carrier_id)
                    .order_by(
                        PGBrcBoundedLiveTrialAuthorizationDraftORM.updated_at_ms.desc(),
                        PGBrcBoundedLiveTrialAuthorizationDraftORM.draft_id.desc(),
                    )
                    .limit(1)
                )
                row = result.scalar_one_or_none()
                return self._to_draft(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    @staticmethod
    def _apply_draft(
        row: PGBrcBoundedLiveTrialAuthorizationDraftORM,
        draft: BoundedLiveTrialAuthorizationDraft,
    ) -> None:
        payload = draft.model_dump(mode="json")
        row.carrier_id = draft.carrier_id
        row.strategy_family_id = draft.strategy_family_id
        row.symbol = draft.symbol
        row.side = draft.side
        row.max_notional = Decimal(str(draft.max_notional))
        row.quantity = Decimal(str(draft.quantity))
        row.leverage = Decimal(str(draft.leverage))
        row.protection_plan_type = draft.protection_plan_type
        row.single_use = draft.single_use
        row.status = draft.status
        row.live_ready = draft.live_ready
        row.order_permission_granted = draft.order_permission_granted
        row.execution_permission_granted = draft.execution_permission_granted
        row.execution_intent_created = draft.execution_intent_created
        row.order_created = draft.order_created
        row.auto_execution_enabled = draft.auto_execution_enabled
        row.consumed = draft.consumed
        row.expires_at_ms = draft.expires_at_ms
        row.linked_acknowledgement_id = draft.linked_acknowledgement_id
        row.source = draft.source
        row.non_live_metadata_only = draft.non_live_metadata_only
        row.hard_gate_snapshot_json = {
            "live_ready": draft.live_ready,
            "order_permission_granted": draft.order_permission_granted,
            "execution_permission_granted": draft.execution_permission_granted,
            "execution_intent_created": draft.execution_intent_created,
            "order_created": draft.order_created,
            "consumed": draft.consumed,
        }
        row.warning_acknowledgement_snapshot_json = {
            "linked_acknowledgement_id": draft.linked_acknowledgement_id,
        }
        row.metadata_json = payload
        row.created_at_ms = draft.created_at_ms
        row.updated_at_ms = draft.updated_at_ms

    @staticmethod
    def _to_acknowledgement(row: PGBrcOwnerRiskAcknowledgementORM) -> OwnerRiskAcknowledgement:
        return OwnerRiskAcknowledgement(
            acknowledgement_id=row.acknowledgement_id,
            carrier_id=row.carrier_id,
            strategy_family_id=row.strategy_family_id,
            acknowledged_warning_codes=list(row.acknowledged_warning_codes_json or []),
            owner_id=row.owner_id,
            acknowledged_at_ms=row.acknowledged_at_ms,
            acknowledgement_scope=row.acknowledgement_scope,
            source="owner_console",
            non_live_metadata_only=True,
        )

    @staticmethod
    def _to_draft(row: PGBrcBoundedLiveTrialAuthorizationDraftORM) -> BoundedLiveTrialAuthorizationDraft:
        return BoundedLiveTrialAuthorizationDraft(
            draft_id=row.draft_id,
            carrier_id=row.carrier_id,
            strategy_family_id=row.strategy_family_id,
            symbol=row.symbol,
            side=row.side,
            max_notional=row.max_notional,
            quantity=row.quantity,
            leverage=row.leverage,
            protection_plan_type=row.protection_plan_type,
            single_use=True,
            status="pending_owner_live_authorization",
            live_ready=False,
            order_permission_granted=False,
            execution_permission_granted=False,
            execution_intent_created=False,
            order_created=False,
            auto_execution_enabled=False,
            consumed=False,
            expires_at_ms=row.expires_at_ms,
            linked_acknowledgement_id=row.linked_acknowledgement_id,
            created_at_ms=row.created_at_ms,
            updated_at_ms=row.updated_at_ms,
            source="owner_console",
            non_live_metadata_only=True,
        )


def _pg_error(exc: SQLAlchemyError) -> OwnerTrialFlowInfrastructureError:
    return OwnerTrialFlowInfrastructureError(
        "pg_persistence_error",
        f"Owner trial-flow PostgreSQL persistence failed: {exc.__class__.__name__}",
    )
