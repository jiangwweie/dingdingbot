#!/usr/bin/env python3
"""PG-backed probe artifact for runtime post-submit finalize.

The probe is meant for local and Tokyo integration validation. It resolves
durable post-submit evidence by authorization ID, reads trusted local position
projection for the runtime symbol, and embeds the protected post-submit
finalize lifecycle payload as read-only evidence. It never submits, cancels,
amends, closes, withdraws, or transfers funds.
"""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any, Protocol

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.order_lifecycle_service import OrderLifecycleService  # noqa: E402
from src.application.runtime_execution_intent_adapter_service import (  # noqa: E402
    RuntimeExecutionIntentAdapterService,
)
from src.application.runtime_post_submit_finalize_service import (  # noqa: E402
    RuntimePostSubmitFinalizeService,
)
from src.application.strategy_runtime_service import (  # noqa: E402
    StrategyRuntimeInstanceService,
)
from src.domain.models import Position  # noqa: E402
from src.infrastructure.connection_pool import close_all_connections  # noqa: E402
from src.infrastructure.pg_brc_admission_repository import (  # noqa: E402
    PgBrcAdmissionRepository,
)
from src.infrastructure.pg_order_repository import PgOrderRepository  # noqa: E402
from src.infrastructure.pg_position_repository import PgPositionRepository  # noqa: E402
from src.infrastructure.pg_reconciliation_read_model_repository import (  # noqa: E402
    PgReconciliationReadModelRepository,
)
from src.infrastructure.pg_runtime_execution_attempt_mutation_repository import (  # noqa: E402
    PgRuntimeExecutionAttemptMutationRepository,
)
from src.infrastructure.pg_runtime_execution_attempt_outcome_policy_repository import (  # noqa: E402
    PgRuntimeExecutionAttemptOutcomePolicyRepository,
)
from src.infrastructure.pg_runtime_execution_attempt_reservation_repository import (  # noqa: E402
    PgRuntimeExecutionAttemptReservationRepository,
)
from src.infrastructure.pg_runtime_execution_exchange_submit_execution_result_repository import (  # noqa: E402
    PgRuntimeExecutionExchangeSubmitExecutionResultRepository,
)
from src.infrastructure.pg_runtime_execution_intent_draft_repository import (  # noqa: E402
    PgRuntimeExecutionIntentDraftRepository,
)
from src.infrastructure.pg_runtime_execution_post_submit_budget_settlement_repository import (  # noqa: E402
    PgRuntimeExecutionPostSubmitBudgetSettlementRepository,
)
from src.infrastructure.pg_runtime_execution_submit_outcome_review_repository import (  # noqa: E402
    PgRuntimeExecutionSubmitOutcomeReviewRepository,
)
from src.infrastructure.pg_strategy_runtime_repository import (  # noqa: E402
    PgStrategyRuntimeRepository,
)


class PositionRepositoryPort(Protocol):
    async def list_active(
        self,
        *,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[Position]:
        ...


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


async def build_runtime_post_submit_finalize_probe_artifact(
    *,
    authorization_id: str,
    reservation_id: str,
    position_repository: PositionRepositoryPort,
    finalize_service: RuntimePostSubmitFinalizeService,
    execution_result_repository: (
        PgRuntimeExecutionExchangeSubmitExecutionResultRepository
    ),
    closed_review_required: bool = False,
) -> dict[str, Any]:
    result = await execution_result_repository.get_by_authorization_id(
        authorization_id
    )
    if result is None:
        active_position_facts = {
            "source": "pg_position_projection",
            "status": "unresolved_submit_result_missing",
            "active_positions_count": None,
            "runtime_owned_count": 0,
            "unknown_runtime_count": 0,
            "other_runtime_count": 0,
            "positions": [],
        }
        post_submit_finalize_payload = await finalize_service.finalize_authorization(
            authorization_id,
            reservation_id=reservation_id,
            active_positions_count=None,
            closed_review_required=closed_review_required,
        )
    else:
        active_position_facts = await _active_position_facts(
            position_repository,
            runtime_instance_id=result.runtime_instance_id,
            symbol=result.symbol,
        )
        post_submit_finalize_payload = await finalize_service.finalize_authorization(
            authorization_id,
            reservation_id=reservation_id,
            active_positions_count=active_position_facts["active_positions_count"],
            closed_review_required=closed_review_required,
        )

    return {
        "scope": "runtime_post_submit_finalize_probe",
        "authorization_id": authorization_id,
        "reservation_id": reservation_id,
        "active_position_facts": _json_value(active_position_facts),
        "post_submit_finalize_payload": _json_value(post_submit_finalize_payload),
        "status": post_submit_finalize_payload.status.value,
        "next_attempt_gate_status": (
            post_submit_finalize_payload.next_attempt_gate.status.value
        ),
        "blockers": list(post_submit_finalize_payload.blockers),
        "next_attempt_blockers": list(
            post_submit_finalize_payload.next_attempt_gate.blockers
        ),
        "warnings": list(post_submit_finalize_payload.warnings),
        "safety_invariants": {
            "exchange_write_called": False,
            "exchange_order_submitted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_cancelled": False,
            "order_lifecycle_submit_called": False,
            "position_closed": False,
            "withdrawal_or_transfer_created": False,
        },
    }


async def _active_position_facts(
    repository: PositionRepositoryPort,
    *,
    runtime_instance_id: str,
    symbol: str,
) -> dict[str, Any]:
    positions = await repository.list_active(symbol=symbol, limit=200)
    runtime_owned = [
        item for item in positions
        if getattr(item, "runtime_instance_id", None) == runtime_instance_id
    ]
    unknown_runtime = [
        item for item in positions
        if not getattr(item, "runtime_instance_id", None)
    ]
    other_runtime = [
        item for item in positions
        if getattr(item, "runtime_instance_id", None)
        and getattr(item, "runtime_instance_id", None) != runtime_instance_id
    ]
    return {
        "source": "pg_position_projection",
        "status": "resolved",
        "symbol": symbol,
        "runtime_instance_id": runtime_instance_id,
        "active_positions_count": len(positions),
        "runtime_owned_count": len(runtime_owned),
        "unknown_runtime_count": len(unknown_runtime),
        "other_runtime_count": len(other_runtime),
        "positions": [
            {
                "position_id": item.id,
                "runtime_instance_id": item.runtime_instance_id,
                "symbol": item.symbol,
                "direction": item.direction.value,
                "current_qty": str(item.current_qty),
                "is_closed": item.is_closed,
            }
            for item in positions[:20]
        ],
    }


def _build_runtime_service() -> StrategyRuntimeInstanceService:
    return StrategyRuntimeInstanceService(
        runtime_repository=PgStrategyRuntimeRepository(),
        admission_repository=PgBrcAdmissionRepository(),
    )


async def _build_services() -> tuple[
    RuntimePostSubmitFinalizeService,
    PgRuntimeExecutionExchangeSubmitExecutionResultRepository,
    PgPositionRepository,
]:
    exchange_result_repo = PgRuntimeExecutionExchangeSubmitExecutionResultRepository()
    submit_review_repo = PgRuntimeExecutionSubmitOutcomeReviewRepository()
    settlement_repo = PgRuntimeExecutionPostSubmitBudgetSettlementRepository()
    runtime_service = _build_runtime_service()
    await runtime_service.initialize()
    order_repo = PgOrderRepository()
    position_repo = PgPositionRepository()
    adapter = RuntimeExecutionIntentAdapterService(
        draft_repository=PgRuntimeExecutionIntentDraftRepository(),
        exchange_submit_execution_result_repository=exchange_result_repo,
        order_lifecycle_service=OrderLifecycleService(repository=order_repo),
        submit_outcome_review_repository=submit_review_repo,
        attempt_reservation_repository=PgRuntimeExecutionAttemptReservationRepository(),
        attempt_mutation_repository=PgRuntimeExecutionAttemptMutationRepository(),
        attempt_outcome_policy_repository=(
            PgRuntimeExecutionAttemptOutcomePolicyRepository()
        ),
        post_submit_budget_settlement_repository=settlement_repo,
        runtime_service=runtime_service,
        reconciliation_read_model_repository=PgReconciliationReadModelRepository(),
    )
    finalize_service = RuntimePostSubmitFinalizeService(
        adapter_service=adapter,
        exchange_submit_execution_result_repository=exchange_result_repo,
        submit_outcome_review_repository=submit_review_repo,
        post_submit_budget_settlement_repository=settlement_repo,
        runtime_service=runtime_service,
    )
    return finalize_service, exchange_result_repo, position_repo


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    finalize_service, execution_result_repo, position_repo = await _build_services()
    try:
        return await build_runtime_post_submit_finalize_probe_artifact(
            authorization_id=args.authorization_id,
            reservation_id=args.reservation_id,
            position_repository=position_repo,
            finalize_service=finalize_service,
            execution_result_repository=execution_result_repo,
            closed_review_required=args.closed_review_required,
        )
    finally:
        await close_all_connections()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a PG-backed runtime post-submit finalize probe artifact.",
    )
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--reservation-id", required=True)
    parser.add_argument("--closed-review-required", action="store_true")
    args = parser.parse_args()
    artifact = asyncio.run(_run(args))
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0 if artifact["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
