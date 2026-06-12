"""Application service for runtime post-submit finalize packets."""

from __future__ import annotations

import time
from typing import Optional, Protocol

from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionResult,
)
from src.domain.runtime_execution_post_submit_budget_settlement import (
    RuntimeExecutionPostSubmitBudgetSettlement,
)
from src.domain.runtime_execution_submit_outcome_review import (
    RuntimeExecutionSubmitOutcomeReview,
)
from src.domain.runtime_post_submit_finalize import (
    RuntimePostSubmitFinalizePacket,
    build_runtime_post_submit_finalize_packet,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


def _now_ms() -> int:
    return int(time.time() * 1000)


class ExchangeSubmitExecutionResultRepositoryPort(Protocol):
    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionExchangeSubmitExecutionResult | None:
        ...


class SubmitOutcomeReviewRepositoryPort(Protocol):
    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitOutcomeReview | None:
        ...


class PostSubmitBudgetSettlementRepositoryPort(Protocol):
    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionPostSubmitBudgetSettlement | None:
        ...


class StrategyRuntimeReaderPort(Protocol):
    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        ...


class RuntimeExecutionIntentAdapterPostSubmitPort(Protocol):
    async def record_submit_outcome_review_for_authorization(
        self,
        authorization_id: str,
        *,
        exchange_submit_execution_result: (
            RuntimeExecutionExchangeSubmitExecutionResult | None
        ) = None,
    ) -> RuntimeExecutionSubmitOutcomeReview:
        ...

    async def settle_first_real_submit_budget_for_authorization(
        self,
        authorization_id: str,
        *,
        reservation_id: str,
    ) -> RuntimeExecutionPostSubmitBudgetSettlement:
        ...


class RuntimePostSubmitFinalizeService:
    def __init__(
        self,
        *,
        adapter_service: RuntimeExecutionIntentAdapterPostSubmitPort,
        exchange_submit_execution_result_repository: (
            ExchangeSubmitExecutionResultRepositoryPort | None
        ) = None,
        submit_outcome_review_repository: (
            SubmitOutcomeReviewRepositoryPort | None
        ) = None,
        post_submit_budget_settlement_repository: (
            PostSubmitBudgetSettlementRepositoryPort | None
        ) = None,
        runtime_service: StrategyRuntimeReaderPort | None = None,
    ) -> None:
        self._adapter_service = adapter_service
        self._exchange_submit_execution_result_repository = (
            exchange_submit_execution_result_repository
        )
        self._submit_outcome_review_repository = submit_outcome_review_repository
        self._post_submit_budget_settlement_repository = (
            post_submit_budget_settlement_repository
        )
        self._runtime_service = runtime_service

    async def finalize_authorization(
        self,
        authorization_id: str,
        *,
        reservation_id: str,
        active_positions_count: int | None,
        closed_review_required: bool = False,
        protection_blockers: list[str] | None = None,
    ) -> RuntimePostSubmitFinalizePacket:
        blockers: list[str] = []
        warnings: list[str] = []
        result = await self._load_exchange_submit_execution_result(
            authorization_id,
            blockers,
        )
        review = await self._load_or_record_submit_outcome_review(
            authorization_id,
            result,
            blockers,
            warnings,
        )
        settlement = await self._load_or_record_budget_settlement(
            authorization_id,
            reservation_id,
            blockers,
            warnings,
        )
        runtime = await self._load_runtime(
            result=result,
            review=review,
            settlement=settlement,
            blockers=blockers,
        )
        return build_runtime_post_submit_finalize_packet(
            authorization_id=authorization_id,
            runtime=runtime,
            exchange_submit_execution_result=result,
            submit_outcome_review=review,
            post_submit_budget_settlement=settlement,
            active_positions_count=active_positions_count,
            closed_review_required=closed_review_required,
            protection_blockers=protection_blockers or [],
            additional_blockers=blockers,
            additional_warnings=warnings,
            now_ms=_now_ms(),
        )

    async def _load_exchange_submit_execution_result(
        self,
        authorization_id: str,
        blockers: list[str],
    ) -> RuntimeExecutionExchangeSubmitExecutionResult | None:
        if self._exchange_submit_execution_result_repository is None:
            blockers.append("exchange_submit_execution_result_repository_unavailable")
            return None
        result = await (
            self._exchange_submit_execution_result_repository
            .get_by_authorization_id(authorization_id)
        )
        if result is None:
            blockers.append("exchange_submit_execution_result_not_found")
        return result

    async def _load_or_record_submit_outcome_review(
        self,
        authorization_id: str,
        result: RuntimeExecutionExchangeSubmitExecutionResult | None,
        blockers: list[str],
        warnings: list[str],
    ) -> RuntimeExecutionSubmitOutcomeReview | None:
        if self._submit_outcome_review_repository is not None:
            review = await (
                self._submit_outcome_review_repository
                .get_by_authorization_id(authorization_id)
            )
            if review is not None:
                warnings.append("submit_outcome_review_existing_reused")
                return review
        if result is None:
            return None
        try:
            return await (
                self._adapter_service
                .record_submit_outcome_review_for_authorization(
                    authorization_id,
                    exchange_submit_execution_result=result,
                )
            )
        except Exception as exc:  # pragma: no cover - repository-specific.
            blockers.append(
                "submit_outcome_review_recording_failed:"
                f"{type(exc).__name__}"
            )
            return None

    async def _load_or_record_budget_settlement(
        self,
        authorization_id: str,
        reservation_id: str,
        blockers: list[str],
        warnings: list[str],
    ) -> RuntimeExecutionPostSubmitBudgetSettlement | None:
        if self._post_submit_budget_settlement_repository is not None:
            settlement = await (
                self._post_submit_budget_settlement_repository
                .get_by_authorization_id(authorization_id)
            )
            if settlement is not None:
                warnings.append("post_submit_budget_settlement_existing_reused")
                return settlement
        try:
            return await (
                self._adapter_service
                .settle_first_real_submit_budget_for_authorization(
                    authorization_id,
                    reservation_id=reservation_id,
                )
            )
        except Exception as exc:  # pragma: no cover - repository-specific.
            blockers.append(
                "post_submit_budget_settlement_recording_failed:"
                f"{type(exc).__name__}"
            )
            return None

    async def _load_runtime(
        self,
        *,
        result: RuntimeExecutionExchangeSubmitExecutionResult | None,
        review: RuntimeExecutionSubmitOutcomeReview | None,
        settlement: RuntimeExecutionPostSubmitBudgetSettlement | None,
        blockers: list[str],
    ) -> StrategyRuntimeInstance | None:
        if self._runtime_service is None:
            blockers.append("runtime_service_unavailable")
            return None
        runtime_instance_id = _first_present(
            getattr(settlement, "runtime_instance_id", None),
            getattr(review, "runtime_instance_id", None),
            getattr(result, "runtime_instance_id", None),
        )
        if not runtime_instance_id:
            blockers.append("runtime_instance_id_unresolved")
            return None
        try:
            return await self._runtime_service.get_runtime(runtime_instance_id)
        except Exception as exc:  # pragma: no cover - repository-specific.
            blockers.append(f"runtime_load_failed:{type(exc).__name__}")
            return None


def _first_present(*values: Optional[str]) -> str | None:
    for value in values:
        if value:
            return str(value)
    return None
