"""PostgreSQL repository for multi-carrier budget authorization metadata."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.multi_carrier_budget_authorization import (
    CarrierBudgetScope,
    MultiCarrierBudgetAuthorization,
    MultiCarrierBudgetAuthorizationInfrastructureError,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGBrcMultiCarrierBudgetAuthorizationORM


class PgMultiCarrierBudgetAuthorizationRepository:
    """Persist disabled multi-carrier budget metadata in PostgreSQL only."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        try:
            self._session_maker = session_maker or get_pg_session_maker()
        except ValueError as exc:
            raise MultiCarrierBudgetAuthorizationInfrastructureError(
                "pg_unavailable",
                f"Multi-carrier budget authorization metadata requires PostgreSQL: {exc}",
            ) from exc
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def create(
        self,
        authorization: MultiCarrierBudgetAuthorization,
    ) -> MultiCarrierBudgetAuthorization:
        row = PGBrcMultiCarrierBudgetAuthorizationORM(
            budget_authorization_id=authorization.budget_authorization_id,
            allowed_carriers_json=[
                carrier.model_dump(mode="json")
                for carrier in authorization.allowed_carriers
            ],
            global_budget=Decimal(str(authorization.global_budget)),
            max_attempts=authorization.max_attempts,
            daily_loss_limit=Decimal(str(authorization.daily_loss_limit)),
            max_concurrent_positions=authorization.max_concurrent_positions,
            cooldown_seconds=authorization.cooldown_seconds,
            valid_from_ms=authorization.valid_from_ms,
            valid_until_ms=authorization.valid_until_ms,
            status=authorization.status,
            linked_acknowledgement_id=authorization.linked_acknowledgement_id,
            linked_authorization_id=authorization.linked_authorization_id,
            live_ready=authorization.live_ready,
            auto_execution_enabled=authorization.auto_execution_enabled,
            order_permission_granted=authorization.order_permission_granted,
            execution_permission_granted=authorization.execution_permission_granted,
            execution_intent_created=authorization.execution_intent_created,
            order_created=authorization.order_created,
            source=authorization.source,
            metadata_only=authorization.metadata_only,
            metadata_json=authorization.model_dump(mode="json"),
            created_at_ms=authorization.created_at_ms,
            updated_at_ms=authorization.updated_at_ms,
        )
        try:
            async with self._session_maker() as session:
                async with session.begin():
                    session.add(row)
                return self._to_authorization(row)
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    async def latest(self) -> MultiCarrierBudgetAuthorization | None:
        try:
            async with self._session_maker() as session:
                result = await session.execute(
                    select(PGBrcMultiCarrierBudgetAuthorizationORM)
                    .order_by(
                        PGBrcMultiCarrierBudgetAuthorizationORM.updated_at_ms.desc(),
                        PGBrcMultiCarrierBudgetAuthorizationORM.budget_authorization_id.desc(),
                    )
                    .limit(1)
                )
                row = result.scalar_one_or_none()
                return self._to_authorization(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    async def get(
        self,
        budget_authorization_id: str,
    ) -> MultiCarrierBudgetAuthorization | None:
        try:
            async with self._session_maker() as session:
                row = await session.get(
                    PGBrcMultiCarrierBudgetAuthorizationORM,
                    budget_authorization_id,
                )
                return self._to_authorization(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    async def revoke(
        self,
        *,
        budget_authorization_id: str,
        revoked_at_ms: int,
        revoked_by: str,
        revoke_reason: str | None,
        operation_id: str | None,
    ) -> MultiCarrierBudgetAuthorization:
        try:
            async with self._session_maker() as session:
                async with session.begin():
                    row = await session.get(
                        PGBrcMultiCarrierBudgetAuthorizationORM,
                        budget_authorization_id,
                        with_for_update=True,
                    )
                    if row is None:
                        raise MultiCarrierBudgetAuthorizationInfrastructureError(
                            "budget_authorization_not_found",
                            "Budget authorization metadata row was not found.",
                        )
                    if row.status != "revoked":
                        row.status = "revoked"
                        row.revoked_at_ms = revoked_at_ms
                        row.revoked_by = revoked_by
                        row.revoke_reason = revoke_reason
                        row.last_control_operation_id = operation_id
                        row.updated_at_ms = revoked_at_ms
                        metadata = dict(row.metadata_json or {})
                        metadata["status"] = "revoked"
                        metadata["revoked_at_ms"] = revoked_at_ms
                        metadata["revoked_by"] = revoked_by
                        metadata["revoke_reason"] = revoke_reason
                        metadata["last_control_operation_id"] = operation_id
                        row.metadata_json = metadata
                    await session.flush()
                    return self._to_authorization(row)
        except MultiCarrierBudgetAuthorizationInfrastructureError:
            raise
        except SQLAlchemyError as exc:
            raise _pg_error(exc) from exc

    @staticmethod
    def _to_authorization(
        row: PGBrcMultiCarrierBudgetAuthorizationORM,
    ) -> MultiCarrierBudgetAuthorization:
        return MultiCarrierBudgetAuthorization(
            budget_authorization_id=row.budget_authorization_id,
            allowed_carriers=[
                CarrierBudgetScope.model_validate(carrier)
                for carrier in row.allowed_carriers_json
            ],
            global_budget=Decimal(str(row.global_budget)),
            max_attempts=row.max_attempts,
            daily_loss_limit=Decimal(str(row.daily_loss_limit)),
            max_concurrent_positions=row.max_concurrent_positions,
            cooldown_seconds=row.cooldown_seconds,
            valid_from_ms=row.valid_from_ms,
            valid_until_ms=row.valid_until_ms,
            status=row.status,
            linked_acknowledgement_id=row.linked_acknowledgement_id,
            linked_authorization_id=row.linked_authorization_id,
            revoked_at_ms=row.revoked_at_ms,
            revoked_by=row.revoked_by,
            revoke_reason=row.revoke_reason,
            last_control_operation_id=row.last_control_operation_id,
            live_ready=row.live_ready,
            auto_execution_enabled=row.auto_execution_enabled,
            order_permission_granted=row.order_permission_granted,
            execution_permission_granted=row.execution_permission_granted,
            execution_intent_created=row.execution_intent_created,
            order_created=row.order_created,
            source=row.source,
            metadata_only=row.metadata_only,
            created_at_ms=row.created_at_ms,
            updated_at_ms=row.updated_at_ms,
        )


def _pg_error(exc: SQLAlchemyError) -> MultiCarrierBudgetAuthorizationInfrastructureError:
    return MultiCarrierBudgetAuthorizationInfrastructureError(
        "pg_write_failed",
        f"Failed to persist multi-carrier budget authorization metadata: {exc.__class__.__name__}",
    )
