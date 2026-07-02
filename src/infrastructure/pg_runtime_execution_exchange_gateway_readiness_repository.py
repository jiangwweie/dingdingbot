"""PG repository for runtime exchange gateway readiness evidence."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.runtime_execution_exchange_gateway_readiness import (
    RuntimeExecutionExchangeGatewayReadiness,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGRuntimeExecutionExchangeGatewayReadinessORM,
)


class PgRuntimeExecutionExchangeGatewayReadinessRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        readiness: RuntimeExecutionExchangeGatewayReadiness,
    ) -> RuntimeExecutionExchangeGatewayReadiness:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(readiness))
            await session.commit()
        return readiness

    async def get(
        self,
        readiness_id: str,
    ) -> RuntimeExecutionExchangeGatewayReadiness | None:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionExchangeGatewayReadinessORM,
                readiness_id,
            )
            return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        readiness: RuntimeExecutionExchangeGatewayReadiness,
    ) -> PGRuntimeExecutionExchangeGatewayReadinessORM:
        return PGRuntimeExecutionExchangeGatewayReadinessORM(
            readiness_id=readiness.readiness_id,
            status=readiness.status.value,
            exchange_name=readiness.exchange_name,
            trading_env=readiness.trading_env,
            exchange_testnet=readiness.exchange_testnet,
            execution_permission_max=readiness.execution_permission_max,
            runtime_control_api_enabled=readiness.runtime_control_api_enabled,
            runtime_test_signal_injection_enabled=(
                readiness.runtime_test_signal_injection_enabled
            ),
            runtime_exchange_submit_gateway_binding_enabled=(
                readiness.runtime_exchange_submit_gateway_binding_enabled
            ),
            exchange_credentials_present=readiness.exchange_credentials_present,
            owner_confirmed_gateway_readiness_review=(
                readiness.owner_confirmed_gateway_readiness_review
            ),
            owner_operator_id=readiness.owner_operator_id,
            owner_confirmation_reference=(
                readiness.owner_confirmation_reference
            ),
            reason=readiness.reason,
            required_gateway_methods_json=list(readiness.required_gateway_methods),
            blockers_json=list(readiness.blockers),
            warnings_json=list(readiness.warnings),
            gateway_injected=readiness.gateway_injected,
            exchange_called=readiness.exchange_called,
            exchange_order_submitted=readiness.exchange_order_submitted,
            order_lifecycle_submit_called=readiness.order_lifecycle_submit_called,
            execution_intent_status_changed=(
                readiness.execution_intent_status_changed
            ),
            owner_bounded_execution_called=readiness.owner_bounded_execution_called,
            withdrawal_or_transfer_created=readiness.withdrawal_or_transfer_created,
            created_at_ms=readiness.created_at_ms,
            metadata_json=dict(readiness.metadata),
            payload_json=readiness.model_dump(mode="json"),
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionExchangeGatewayReadinessORM,
    ) -> RuntimeExecutionExchangeGatewayReadiness:
        return RuntimeExecutionExchangeGatewayReadiness.model_validate(
            row.payload_json
        )
