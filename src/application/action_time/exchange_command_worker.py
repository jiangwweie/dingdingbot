"""Short-transaction worker for all ticket-bound exchange side effects."""

from __future__ import annotations

import asyncio
from decimal import Decimal
import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_command import (
    claim_next_exchange_command,
    expire_stale_exchange_command_claims,
    record_claimed_exchange_command_outcome,
)
from src.application.action_time.lifecycle_exchange_command_completion import (
    apply_completed_lifecycle_exchange_sources,
    apply_failed_lifecycle_exchange_source,
)
from src.application.action_time.lifecycle_mutation_capability import (
    lifecycle_mutation_capability_decision,
)
from src.application.action_time.netting_domain_hold import (
    upsert_exchange_command_domain_hold,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
)


async def run_one_ticket_bound_exchange_command(
    engine: sa.Engine,
    *,
    gateway: Any,
    worker_id: str,
    lease_ms: int = 15_000,
    now_ms: int | None = None,
    command_sources: tuple[str, ...],
    dispatch_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Claim -> commit -> exchange I/O -> commit result.

    At most one command is dispatched.  No SQLAlchemy connection or transaction
    remains open while the gateway is awaited.
    """

    now_ms = int(now_ms or time.time() * 1000)
    with engine.begin() as conn:
        expired = expire_stale_exchange_command_claims(conn, now_ms=now_ms)
        for expired_command in expired:
            upsert_exchange_command_domain_hold(
                conn,
                command=expired_command,
                blockers=["exchange_command_outcome_unknown"],
                now_ms=now_ms,
            )
        command = (
            {}
            if expired
            else _claim_if_capable(
                conn,
                claim_owner=worker_id,
                now_ms=now_ms,
                lease_ms=lease_ms,
                command_sources=command_sources,
            )
        )
        capability = lifecycle_mutation_capability_decision(conn)
    if not command:
        capability_blockers = list(capability.get("blockers") or [])
        return {
            "schema": "brc.ticket_bound_exchange_command_worker.v1",
            "status": (
                "outcome_unknown_persisted"
                if expired
                else (
                    "durable_mutation_capability_not_ready"
                    if capability_blockers
                    else "no_prepared_command"
                )
            ),
            "expired_command_ids": [
                str(row.get("exchange_command_id") or "") for row in expired
            ],
            "exchange_write_called": False,
            "blockers": (
                ["exchange_command_outcome_unknown"]
                if expired
                else capability_blockers
            ),
        }

    identity_blockers = _gateway_identity_blockers(command, gateway)
    if identity_blockers:
        with engine.begin() as conn:
            recorded = record_claimed_exchange_command_outcome(
                conn,
                exchange_command_id=str(command["exchange_command_id"]),
                claim_token=str(command["claim_token"]),
                target_state=ExchangeCommandState.HARD_STOPPED,
                outcome_class=ExchangeCommandOutcomeClass.CONTRADICTORY_TRUTH,
                exchange_result={
                    "error_code": identity_blockers[0],
                    "error_message": ",".join(identity_blockers),
                },
                now_ms=now_ms,
            )
            upsert_exchange_command_domain_hold(
                conn,
                command=recorded,
                blockers=identity_blockers,
                now_ms=now_ms,
            )
            failure_completion = _apply_terminal_source_failure(
                conn,
                recorded=recorded,
                now_ms=now_ms,
            )
        result_payload = _result(
            "command_hard_stopped",
            recorded,
            blockers=identity_blockers,
            exchange_write_called=False,
        )
        result_payload["lifecycle_completion"] = failure_completion
        return result_payload

    try:
        exchange_result = (
            await asyncio.wait_for(
                _dispatch(command, gateway),
                timeout=dispatch_timeout_seconds,
            )
            if dispatch_timeout_seconds is not None
            else await _dispatch(command, gateway)
        )
    except Exception as exc:
        with engine.begin() as conn:
            recorded = record_claimed_exchange_command_outcome(
                conn,
                exchange_command_id=str(command["exchange_command_id"]),
                claim_token=str(command["claim_token"]),
                target_state=ExchangeCommandState.OUTCOME_UNKNOWN,
                outcome_class=ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
                exchange_result={
                    "error_code": type(exc).__name__,
                    "error_message": str(exc),
                },
                now_ms=now_ms,
            )
            upsert_exchange_command_domain_hold(
                conn,
                command=recorded,
                blockers=["exchange_command_outcome_unknown"],
                now_ms=now_ms,
            )
        return _result(
            "command_outcome_unknown",
            recorded,
            blockers=["exchange_command_outcome_unknown"],
            exchange_write_called=True,
        )

    accepted, exchange_order_id, error = _accepted_result(
        command,
        exchange_result,
    )
    with engine.begin() as conn:
        recorded = record_claimed_exchange_command_outcome(
            conn,
            exchange_command_id=str(command["exchange_command_id"]),
            claim_token=str(command["claim_token"]),
            target_state=(
                ExchangeCommandState.CONFIRMED_SUBMITTED
                if accepted
                else ExchangeCommandState.CONFIRMED_REJECTED
            ),
            outcome_class=(
                ExchangeCommandOutcomeClass.EXCHANGE_ACCEPTED
                if accepted
                else ExchangeCommandOutcomeClass.AUTHORITATIVE_REJECTION
            ),
            exchange_result={
                "exchange_order_id": exchange_order_id,
                "error_code": None if accepted else "exchange_rejected",
                "error_message": error,
            },
            now_ms=now_ms,
        )
        if not accepted:
            upsert_exchange_command_domain_hold(
                conn,
                command=recorded,
                blockers=[error or "exchange_command_confirmed_rejected"],
                now_ms=now_ms,
            )
            failure_completion = _apply_terminal_source_failure(
                conn,
                recorded=recorded,
                now_ms=now_ms,
            )
        else:
            failure_completion = {}
        completion = (
            apply_completed_lifecycle_exchange_sources(
                conn,
                now_ms=now_ms,
                source_command_id=str(recorded.get("source_command_id") or ""),
            )
            if accepted
            else []
        )
    result_payload = _result(
        "command_confirmed" if accepted else "command_rejected",
        recorded,
        blockers=[] if accepted else [error or "exchange_rejected"],
        exchange_write_called=True,
    )
    result_payload["lifecycle_completion"] = completion
    if failure_completion:
        result_payload["lifecycle_completion"] = [failure_completion]
    return result_payload


def _apply_terminal_source_failure(
    conn: sa.engine.Connection,
    *,
    recorded: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    source = str(recorded.get("command_source") or "")
    source_id = str(recorded.get("source_command_id") or "")
    if source not in {"protection_recovery", "runner_mutation", "orphan_cleanup"}:
        return {}
    return apply_failed_lifecycle_exchange_source(
        conn,
        command_source=source,
        source_command_id=source_id,
        now_ms=now_ms,
    )


def _claim_if_capable(
    conn: sa.engine.Connection,
    *,
    claim_owner: str,
    now_ms: int,
    lease_ms: int,
    command_sources: tuple[str, ...],
) -> dict[str, Any]:
    if lifecycle_mutation_capability_decision(conn)["blockers"]:
        return {}
    return claim_next_exchange_command(
        conn,
        claim_owner=claim_owner,
        now_ms=now_ms,
        lease_ms=lease_ms,
        command_sources=command_sources,
    )


async def _dispatch(command: dict[str, Any], gateway: Any) -> Any:
    if str(command.get("command_kind") or "") == "cancel_order":
        target = str(command.get("target_exchange_order_id") or "").strip()
        if not target:
            raise ValueError("cancel_target_exchange_order_id_missing")
        return await gateway.cancel_order(
            exchange_order_id=target,
            symbol=str(command["gateway_symbol"]),
        )
    return await gateway.place_order(
        symbol=str(command["gateway_symbol"]),
        order_type=str(command["order_type"]),
        side=str(command["gateway_side"]),
        amount=Decimal(str(command["amount"])),
        price=(
            Decimal(str(command["price"]))
            if command.get("price") is not None
            else None
        ),
        trigger_price=(
            Decimal(str(command["stop_price"]))
            if command.get("stop_price") is not None
            else None
        ),
        reduce_only=command.get("reduce_intent") == "reduce_position",
        position_side=command.get("position_side"),
        client_order_id=str(command["client_order_id"]),
    )


def _gateway_identity_blockers(
    command: dict[str, Any],
    gateway: Any,
) -> list[str]:
    blockers: list[str] = []
    if str(getattr(gateway, "runtime_account_id", "") or "") != str(
        command.get("account_id") or ""
    ):
        blockers.append("exchange_command_gateway_account_mismatch")
    if str(getattr(gateway, "runtime_exchange_id", "") or "") != str(
        command.get("exchange_id") or ""
    ):
        blockers.append("exchange_command_gateway_exchange_mismatch")
    return blockers


def _accepted_result(
    command: dict[str, Any],
    result: Any,
) -> tuple[bool, str, str]:
    success = getattr(result, "is_success", None)
    if success is None and isinstance(result, dict):
        success = result.get("is_success")
    exchange_order_id = str(
        getattr(result, "exchange_order_id", None)
        or (result.get("exchange_order_id") if isinstance(result, dict) else "")
        or (result.get("id") if isinstance(result, dict) else "")
        or (
            command.get("target_exchange_order_id")
            if command.get("command_kind") == "cancel_order"
            else ""
        )
        or ""
    )
    error = str(
        getattr(result, "error_message", None)
        or (result.get("error_message") if isinstance(result, dict) else "")
        or ""
    )
    return success is True and bool(exchange_order_id), exchange_order_id, error


def _result(
    status: str,
    command: dict[str, Any],
    *,
    blockers: list[str],
    exchange_write_called: bool,
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_exchange_command_worker.v1",
        "status": status,
        "exchange_command_id": command.get("exchange_command_id"),
        "command_state": command.get("command_state"),
        "command_kind": command.get("command_kind"),
        "command_source": command.get("command_source"),
        "source_command_id": command.get("source_command_id"),
        "netting_domain_key": command.get("netting_domain_key"),
        "exchange_write_called": exchange_write_called,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
    }
