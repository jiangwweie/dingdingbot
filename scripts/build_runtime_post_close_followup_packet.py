#!/usr/bin/env python3
"""Build a non-executing post-close follow-up packet for a runtime."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


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


def _with_env_file(args: list[str], env_file: str | None) -> list[str]:
    if not env_file:
        return args
    return [*args, "--env-file", env_file]


def _operator_command_plan(
    *,
    runtime_instance_id: str,
    env_file: str | None,
    packet: Any,
) -> dict[str, Any]:
    followup_args = _with_env_file(
        [
            "scripts/build_runtime_post_close_followup_packet.py",
            "--runtime-instance-id",
            runtime_instance_id,
        ],
        env_file,
    )
    close_args = _with_env_file(
        [
            "scripts/runtime_owner_reduce_only_close_flow.py",
            "--runtime-instance-id",
            runtime_instance_id,
        ],
        env_file,
    )
    review_facts_args = _with_env_file(
        [
            "scripts/build_runtime_closed_trade_review_facts_packet.py",
            "--runtime-instance-id",
            runtime_instance_id,
        ],
        env_file,
    )
    approval_env = getattr(packet, "owner_close_approval_env", None)
    approval_value = getattr(packet, "owner_close_approval_value", None)
    close_execute_args = [*close_args, "--execute-real-close"] if approval_value else []
    packet_status = getattr(packet, "status", "")
    post_close_complete = (
        str(getattr(packet_status, "value", packet_status)) == "post_close_complete"
    )
    return {
        "scope": "runtime_post_close_operator_command_plan",
        "not_executed": True,
        "requires_explicit_owner_approval_before_execute": True,
        "owner_close_approval_env": approval_env,
        "owner_close_approval_value": approval_value,
        "refresh_followup_command_args": followup_args,
        "owner_close_dry_run_command_args": close_args if approval_value else [],
        "owner_close_execute_command_args": close_execute_args,
        "closed_review_facts_refresh_command_args": review_facts_args,
        "closed_review_command_args": (
            []
            if post_close_complete
            else list(getattr(packet, "closed_review_command_args", []) or [])
        ),
        "post_close_required_sequence": (
            list(getattr(packet, "required_steps", []) or [])
            if post_close_complete
            else [
                "refresh_followup",
                "owner_authorize_exact_reduce_only_close_value",
                "run_owner_close_execute_command",
                "refresh_followup_until_flat",
                "run_closed_review_dry_run",
                "run_closed_review_apply_if_ready",
                "verify_next_attempt_gate",
            ]
        ),
        "safety_invariants": {
            "packet_only": True,
            "command_plan_only": True,
            "exchange_write_called": False,
            "review_record_created": False,
            "order_created": False,
            "position_closed": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


async def _build_packet(args: argparse.Namespace) -> dict[str, Any]:
    _load_env_file(args.env_file)

    from src.application.reconciliation import ReconciliationService
    from src.application.runtime_live_position_monitor_service import (
        RuntimeLivePositionMonitorService,
    )
    from src.application.runtime_closed_trade_review_facts_service import (
        RuntimeClosedTradeReviewFactsService,
    )
    from src.application.runtime_position_exit_plan_service import (
        RuntimePositionExitPlanService,
    )
    from src.domain.runtime_post_close_followup import (
        build_runtime_post_close_followup_packet,
    )
    from src.domain.runtime_reduce_only_close_authorization import (
        build_runtime_reduce_only_close_owner_packet,
    )
    from src.infrastructure.connection_pool import close_all_connections
    from src.infrastructure.exchange_gateway import ExchangeGateway
    from src.infrastructure.pg_order_repository import PgOrderRepository
    from src.infrastructure.pg_position_repository import PgPositionRepository
    from src.infrastructure.pg_live_lifecycle_review_repository import (
        PgLiveLifecycleReviewRepository,
    )
    from src.infrastructure.pg_strategy_runtime_repository import (
        PgStrategyRuntimeRepository,
    )

    runtime_repository = PgStrategyRuntimeRepository()
    position_repository = PgPositionRepository()
    order_repository = PgOrderRepository()
    review_repository = PgLiveLifecycleReviewRepository()
    await runtime_repository.initialize()
    await position_repository.initialize()
    await order_repository.initialize()
    await review_repository.initialize()

    gateway = None
    if not args.skip_exchange:
        api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
        api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
        if not api_key or not api_secret:
            raise RuntimeError(
                "EXCHANGE_API_KEY and EXCHANGE_API_SECRET are required unless "
                "--skip-exchange is set"
            )
        gateway = ExchangeGateway(
            os.environ.get("EXCHANGE_NAME", "binance"),
            api_key,
            api_secret,
            testnet=_parse_bool_env(os.environ.get("EXCHANGE_TESTNET")),
        )

    reconciliation_service = None
    if not args.skip_reconciliation and gateway is not None:
        reconciliation_service = ReconciliationService(
            gateway=gateway,
            position_mgr=position_repository,
            order_repository=order_repository,
        )

    try:
        monitor_service = RuntimeLivePositionMonitorService(
            runtime_repository=runtime_repository,
            position_repository=position_repository,
            order_repository=order_repository,
            exchange_gateway=gateway,
            reconciliation_service=reconciliation_service,
        )
        monitor = await monitor_service.build_monitor_packet(
            runtime_instance_id=args.runtime_instance_id,
        )
        closed_review_facts_service = RuntimeClosedTradeReviewFactsService(
            runtime_repository=runtime_repository,
            order_repository=order_repository,
            position_repository=position_repository,
        )
        closed_review_facts_packet = await closed_review_facts_service.build_packet(
            runtime_instance_id=args.runtime_instance_id,
        )
        owner_close_packet = None
        if monitor.active_position_present:
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
            owner_close_packet = build_runtime_reduce_only_close_owner_packet(
                exit_plan=exit_plan,
                now_ms=int(time.time() * 1000),
            )
        closed_review = None
        if not monitor.active_position_present:
            closed_review = await review_repository.get_latest(
                authorization_id=f"runtime-review:{args.runtime_instance_id}",
                symbol=monitor.symbol,
            )
        closed_review_recorded = _closed_reviewed(closed_review)
        packet = build_runtime_post_close_followup_packet(
            monitor=monitor,
            owner_close_packet=owner_close_packet,
            closed_review_facts_packet=closed_review_facts_packet,
            closed_review_recorded=closed_review_recorded,
            closed_review_id=(
                getattr(closed_review, "review_id", None)
                if closed_review_recorded
                else None
            ),
            now_ms=int(time.time() * 1000),
        )
        operator_command_plan = _operator_command_plan(
            runtime_instance_id=args.runtime_instance_id,
            env_file=args.env_file,
            packet=packet,
        )
        return {
            "scope": "runtime_post_close_followup_packet",
            "status": packet.status.value,
            "packet": _json_value(packet),
            "source_monitor": _json_value(monitor),
            "owner_close_packet": _json_value(owner_close_packet)
            if owner_close_packet is not None
            else None,
            "closed_review_facts_packet": _json_value(closed_review_facts_packet),
            "closed_lifecycle_review": _json_value(closed_review)
            if closed_review is not None
            else None,
            "operator_command_plan": operator_command_plan,
            "safety_invariants": {
                "packet_only": True,
                "exchange_read_only": gateway is not None,
                "closed_review_facts_pg_read_only": True,
                "exchange_write_called": False,
                "review_record_created": False,
                "order_created": False,
                "order_cancelled": False,
                "order_amended": False,
                "position_closed": False,
                "runtime_state_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        }
    finally:
        if gateway is not None:
            await gateway.close()
        await close_all_connections()


def _closed_reviewed(review: Any | None) -> bool:
    if review is None:
        return False
    return (
        str(getattr(review, "review_status", "") or "").lower() == "closed_reviewed"
        and str(getattr(review, "lifecycle_status", "") or "").lower()
        == "closed_reviewed"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a non-executing runtime post-close follow-up packet.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--env-file", help="Optional env file to load.")
    parser.add_argument("--skip-exchange", action="store_true")
    parser.add_argument("--skip-reconciliation", action="store_true")
    args = parser.parse_args()
    with redirect_stdout(sys.stderr):
        payload = asyncio.run(_build_packet(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
