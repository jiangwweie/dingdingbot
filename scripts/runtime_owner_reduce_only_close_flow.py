#!/usr/bin/env python3
"""Owner-authorized runtime reduce-only close flow.

Default mode is dry-run. Real close requires both ``--execute-real-close`` and
an exact ``OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE`` env value derived from the
current runtime exit-plan facts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path
import sys
import time
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


APPROVAL_ENV = "OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE"


def _parse_bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path).expanduser()
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and not os.environ.get(key):
            os.environ[key] = value


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class _CloseCapitalProjectionRecorder:
    def __init__(self) -> None:
        self.exit_projection_records: list[dict[str, Any]] = []

    async def record_exit_projection(self, **kwargs: Any) -> None:
        self.exit_projection_records.append(dict(kwargs))


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    _load_env_file(args.env_file)

    from src.application.execution_orchestrator import ExecutionOrchestrator
    from src.application.order_lifecycle_service import OrderLifecycleService
    from src.application.position_projection_service import PositionProjectionService
    from src.application.reconciliation import ReconciliationService
    from src.application.runtime_position_exit_plan_service import (
        RuntimePositionExitPlanService,
    )
    from src.domain.runtime_reduce_only_close_authorization import (
        RuntimeReduceOnlyCloseOwnerEvidenceStatus,
        build_runtime_reduce_only_close_owner_evidence,
    )
    from src.infrastructure.connection_pool import close_all_connections
    from src.infrastructure.exchange_gateway import ExchangeGateway
    from src.infrastructure.pg_order_repository import PgOrderRepository
    from src.infrastructure.pg_position_repository import PgPositionRepository
    from src.infrastructure.pg_strategy_runtime_repository import (
        PgStrategyRuntimeRepository,
    )

    runtime_repository = PgStrategyRuntimeRepository()
    position_repository = PgPositionRepository()
    order_repository = PgOrderRepository()
    await runtime_repository.initialize()
    await position_repository.initialize()
    await order_repository.initialize()

    api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
    api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("EXCHANGE_API_KEY and EXCHANGE_API_SECRET are required")

    gateway = ExchangeGateway(
        os.environ.get("EXCHANGE_NAME", "binance"),
        api_key,
        api_secret,
        testnet=_parse_bool_env(os.environ.get("EXCHANGE_TESTNET")),
    )
    capital_projection = _CloseCapitalProjectionRecorder()
    try:
        await gateway.initialize()
        reconciliation_service = ReconciliationService(
            gateway=gateway,
            position_mgr=position_repository,
            order_repository=order_repository,
        )
        exit_plan_service = RuntimePositionExitPlanService(
            runtime_repository=runtime_repository,
            position_repository=position_repository,
            order_repository=order_repository,
            exchange_gateway=gateway,
            reconciliation_service=reconciliation_service,
        )
        exit_plan = await exit_plan_service.build_exit_plan(
            runtime_instance_id=args.runtime_instance_id,
        )
        owner_evidence = build_runtime_reduce_only_close_owner_evidence(
            exit_plan=exit_plan,
            now_ms=int(time.time() * 1000),
        )
        base = {
            "scope": "runtime_owner_reduce_only_close_flow",
            "runtime_instance_id": args.runtime_instance_id,
            "owner_evidence": _json_value(owner_evidence),
            "source_exit_plan": _json_value(exit_plan),
            "safety_invariants": {
                "exchange_read_before_action": True,
                "withdrawal_or_transfer_created": False,
            },
        }
        if owner_evidence.status != RuntimeReduceOnlyCloseOwnerEvidenceStatus.READY_FOR_OWNER_AUTHORIZATION:
            return {
                **base,
                "status": "blocked_before_owner_authorization",
                "executed": False,
                "blockers": list(owner_evidence.blockers),
                "safety_invariants": {
                    **base["safety_invariants"],
                    "exchange_write_called": False,
                    "order_created": False,
                    "position_closed": False,
                    "runtime_state_mutated": False,
                },
            }

        approval_value = os.environ.get(APPROVAL_ENV, "").strip()
        if approval_value != owner_evidence.owner_approval_value:
            return {
                **base,
                "status": "ready_for_owner_authorization",
                "executed": False,
                "required_approval_env": APPROVAL_ENV,
                "required_approval_value": owner_evidence.owner_approval_value,
                "blockers": [f"{APPROVAL_ENV}_missing_or_wrong"],
                "safety_invariants": {
                    **base["safety_invariants"],
                    "exchange_write_called": False,
                    "order_created": False,
                    "position_closed": False,
                    "runtime_state_mutated": False,
                },
            }

        if not args.execute_real_close:
            return {
                **base,
                "status": "owner_authorized_dry_run_ready",
                "executed": False,
                "blockers": ["execute_real_close_flag_missing"],
                "safety_invariants": {
                    **base["safety_invariants"],
                    "exchange_write_called": False,
                    "order_created": False,
                    "position_closed": False,
                    "runtime_state_mutated": False,
                },
            }

        active_positions = await position_repository.list_active(
            symbol=owner_evidence.symbol,
            limit=10,
        )
        if len(active_positions) != 1:
            return {
                **base,
                "status": "blocked_before_exchange_write",
                "executed": False,
                "blockers": ["active_position_count_not_exactly_one"],
                "active_position_count": len(active_positions),
                "safety_invariants": {
                    **base["safety_invariants"],
                    "exchange_write_called": False,
                    "order_created": False,
                    "position_closed": False,
                    "runtime_state_mutated": False,
                },
            }
        position = active_positions[0]
        qty = Decimal(str(getattr(position, "current_qty", "0")))
        if qty != owner_evidence.close_quantity:
            return {
                **base,
                "status": "blocked_before_exchange_write",
                "executed": False,
                "blockers": ["active_position_quantity_changed_after_owner_evidence"],
                "active_position_quantity": str(qty),
                "owner_evidence_quantity": str(owner_evidence.close_quantity),
                "safety_invariants": {
                    **base["safety_invariants"],
                    "exchange_write_called": False,
                    "order_created": False,
                    "position_closed": False,
                    "runtime_state_mutated": False,
                },
            }

        order_lifecycle = OrderLifecycleService(order_repository)
        projection_service = PositionProjectionService(position_repository)
        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_projection,
            order_lifecycle=order_lifecycle,
            gateway=gateway,
            position_projection_service=projection_service,
        )
        result = await orchestrator.execute_controlled_close(
            position=position,
            reason="owner_authorized_runtime_reduce_only_close",
            max_amount=owner_evidence.close_quantity,
            scope="runtime_owner_reduce_only_close",
        )
        close_order = result["close_order"]
        terminalized = result.get("terminalized_protection_orders") or []
        return {
            **base,
            "status": "executed_reduce_only_close",
            "executed": True,
            "close_order": _json_value(close_order),
            "terminalized_protection_orders": [_json_value(item) for item in terminalized],
            "capital_projection_records": _json_value(
                capital_projection.exit_projection_records
            ),
            "safety_invariants": {
                **base["safety_invariants"],
                "exchange_write_called": True,
                "exchange_write_scope": "reduce_only_market_close_and_protection_cancel",
                "order_created": True,
                "position_closed": True,
                "runtime_state_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        }
    finally:
        await gateway.close()
        await close_all_connections()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Owner-authorized runtime reduce-only close flow.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--env-file", help="Optional env file to load.")
    parser.add_argument(
        "--execute-real-close",
        action="store_true",
        help="Execute the reduce-only close. Requires exact Owner approval env.",
    )
    args = parser.parse_args()
    payload = asyncio.run(_run(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["status"] in {
        "ready_for_owner_authorization",
        "owner_authorized_dry_run_ready",
        "executed_reduce_only_close",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
