"""Application service for runtime exchange gateway readiness evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from os import environ
from typing import Mapping, Protocol

from src.domain.runtime_execution_exchange_gateway_readiness import (
    RuntimeExecutionExchangeGatewayReadiness,
    build_runtime_execution_exchange_gateway_readiness,
)


class RuntimeExecutionExchangeGatewayReadinessRepositoryPort(Protocol):
    async def create(
        self,
        readiness: RuntimeExecutionExchangeGatewayReadiness,
    ) -> RuntimeExecutionExchangeGatewayReadiness:
        ...


class RuntimeExchangeGatewayReadinessService:
    def __init__(
        self,
        *,
        repository: RuntimeExecutionExchangeGatewayReadinessRepositoryPort,
        env: Mapping[str, str | None] | None = None,
    ) -> None:
        self._repository = repository
        self._env = env

    async def record_readiness(
        self,
        *,
        owner_confirmed_gateway_readiness_review: bool = False,
        owner_operator_id: str = "owner",
        reason: str = "owner reviewed runtime exchange gateway readiness",
        owner_confirmation_reference: str | None = None,
    ) -> RuntimeExecutionExchangeGatewayReadiness:
        readiness = build_runtime_execution_exchange_gateway_readiness(
            env=self._env if self._env is not None else environ,
            owner_confirmed_gateway_readiness_review=(
                owner_confirmed_gateway_readiness_review
            ),
            owner_operator_id=owner_operator_id,
            reason=reason,
            owner_confirmation_reference=owner_confirmation_reference,
            now_ms=_now_ms(),
        )
        return await self._repository.create(readiness)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
