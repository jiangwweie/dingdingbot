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
from src.application.action_time.entry_effect_projection import project_entry_effect
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
from src.domain.exceptions import InsufficientMarginError, InvalidOrderError
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
    validate_tp1_execution_contract,
)


MIN_EXCHANGE_COMMAND_COMMIT_MARGIN_MS = 5_000


async def run_one_ticket_bound_exchange_command(
    engine: sa.Engine,
    *,
    gateway: Any,
    worker_id: str,
    lease_ms: int = 15_000,
    now_ms: int | None = None,
    command_sources: tuple[str, ...],
    dispatch_timeout_seconds: float | None = None,
    drain_initial_protection: bool = False,
) -> dict[str, Any]:
    """Run one durable command and optionally drain Entry -> Initial Stop.

    The default preserves the bounded generic-worker contract.  The official
    protected-submit runtime enables ``drain_initial_protection`` so a confirmed
    Entry does not wait for the next lifecycle timer before its initial stop.
    Each exchange I/O still has its own committed claim/result transaction.
    """

    _validate_lease_timeout_budget(
        lease_ms=lease_ms,
        dispatch_timeout_seconds=dispatch_timeout_seconds,
    )
    primary = await _run_one_ticket_bound_exchange_command(
        engine,
        gateway=gateway,
        worker_id=worker_id,
        lease_ms=lease_ms,
        now_ms=now_ms,
        command_sources=command_sources,
        dispatch_timeout_seconds=dispatch_timeout_seconds,
    )
    if not (
        drain_initial_protection
        and primary.get("status") == "command_confirmed"
        and primary.get("command_source") == "protected_submit"
        and primary.get("order_role") == "ENTRY"
    ):
        return primary

    drained: list[dict[str, Any]] = []
    deadline_at = (
        time.monotonic() + dispatch_timeout_seconds
        if dispatch_timeout_seconds is not None
        else None
    )
    for index in range(2):
        timeout = dispatch_timeout_seconds
        if deadline_at is not None:
            timeout = max(0.001, deadline_at - time.monotonic())
        next_result = await _run_one_ticket_bound_exchange_command(
            engine,
            gateway=gateway,
            worker_id=f"{worker_id}:initial-protection:{index}",
            lease_ms=lease_ms,
            now_ms=(now_ms + index + 1) if now_ms is not None else None,
            command_sources=("protected_submit",),
            dispatch_timeout_seconds=timeout,
        )
        if next_result.get("status") == "no_prepared_command":
            with engine.begin() as conn:
                completion = apply_completed_lifecycle_exchange_sources(
                    conn,
                    now_ms=(now_ms + index + 1) if now_ms is not None else int(
                        time.time() * 1000
                    ),
                    source_command_id=str(primary.get("source_command_id") or ""),
                )
            if completion:
                drained.extend(completion)
            break
        drained.append(next_result)
        if next_result.get("status") != "command_confirmed":
            break
    return {
        **primary,
        "initial_protection_drain": drained,
        "initial_protection_complete": any(
            item.get("order_role") == "SL"
            and item.get("status") == "command_confirmed"
            for item in drained
        ),
    }


async def _run_one_ticket_bound_exchange_command(
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

    requested_now_ms = now_ms
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

    command_blockers = _gateway_identity_blockers(
        command, gateway
    ) + _execution_contract_blockers(command)
    if command_blockers:
        with engine.begin() as conn:
            recorded = record_claimed_exchange_command_outcome(
                conn,
                exchange_command_id=str(command["exchange_command_id"]),
                claim_token=str(command["claim_token"]),
                target_state=ExchangeCommandState.HARD_STOPPED,
                outcome_class=ExchangeCommandOutcomeClass.CONTRADICTORY_TRUTH,
                exchange_result={
                    "error_code": command_blockers[0],
                    "error_message": ",".join(command_blockers),
                },
                now_ms=now_ms,
            )
            upsert_exchange_command_domain_hold(
                conn,
                command=recorded,
                blockers=command_blockers,
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
            blockers=command_blockers,
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
    except (InvalidOrderError, InsufficientMarginError) as exc:
        now_ms = _completion_now_ms(requested_now_ms)
        blocker = str(exc)
        with engine.begin() as conn:
            recorded = record_claimed_exchange_command_outcome(
                conn,
                exchange_command_id=str(command["exchange_command_id"]),
                claim_token=str(command["claim_token"]),
                target_state=ExchangeCommandState.CONFIRMED_REJECTED,
                outcome_class=ExchangeCommandOutcomeClass.AUTHORITATIVE_REJECTION,
                exchange_result={
                    "error_code": getattr(exc, "error_code", None),
                    "error_message": blocker,
                },
                now_ms=now_ms,
            )
            project_entry_effect(conn, command=recorded, now_ms=now_ms)
            upsert_exchange_command_domain_hold(
                conn,
                command=recorded,
                blockers=[blocker],
                now_ms=now_ms,
            )
            failure_completion = _apply_terminal_source_failure(
                conn,
                recorded=recorded,
                now_ms=now_ms,
            )
        result_payload = _result(
            "command_rejected",
            recorded,
            blockers=[blocker],
            exchange_write_called=True,
        )
        if failure_completion:
            result_payload["lifecycle_completion"] = [failure_completion]
        return result_payload
    except Exception as exc:
        now_ms = _completion_now_ms(requested_now_ms)
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
            project_entry_effect(conn, command=recorded, now_ms=now_ms)
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
    placement_facts = _placement_result_facts(exchange_result)
    now_ms = _completion_now_ms(requested_now_ms)
    try:
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
                    **placement_facts,
                },
                now_ms=now_ms,
            )
            project_entry_effect(conn, command=recorded, now_ms=now_ms)
    except ValueError as exc:
        return _record_contradictory_exchange_result(
            engine,
            command=command,
            exchange_order_id=exchange_order_id,
            placement_facts=placement_facts,
            error=exc,
            now_ms=now_ms,
        )
    with engine.begin() as conn:
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


def _record_contradictory_exchange_result(
    engine: sa.Engine,
    *,
    command: dict[str, Any],
    exchange_order_id: str,
    placement_facts: dict[str, Any],
    error: ValueError,
    now_ms: int,
) -> dict[str, Any]:
    """Persist an exchange response that cannot satisfy typed result truth."""

    blocker = str(error)
    with engine.begin() as conn:
        recorded = record_claimed_exchange_command_outcome(
            conn,
            exchange_command_id=str(command["exchange_command_id"]),
            claim_token=str(command["claim_token"]),
            target_state=ExchangeCommandState.OUTCOME_UNKNOWN,
            outcome_class=ExchangeCommandOutcomeClass.INCOMPLETE_RESPONSE,
            exchange_result={
                "exchange_order_id": exchange_order_id,
                "exchange_order_status": placement_facts.get(
                    "exchange_order_status"
                ),
                "error_code": blocker,
                "error_message": blocker,
                "contradictory_exchange_result": placement_facts,
            },
            now_ms=now_ms,
        )
        upsert_exchange_command_domain_hold(
            conn,
            command=recorded,
            blockers=[blocker],
            now_ms=now_ms,
        )
        project_entry_effect(conn, command=recorded, now_ms=now_ms)
    return _result(
        "command_outcome_unknown",
        recorded,
        blockers=[blocker],
        exchange_write_called=True,
    )


def _apply_terminal_source_failure(
    conn: sa.engine.Connection,
    *,
    recorded: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    source = str(recorded.get("command_source") or "")
    source_id = str(recorded.get("source_command_id") or "")
    if source not in {
        "protected_submit",
        "protection_recovery",
        "runner_mutation",
        "orphan_cleanup",
    }:
        return {}
    if source == "protected_submit":
        results = apply_completed_lifecycle_exchange_sources(
            conn,
            now_ms=now_ms,
            source_command_id=source_id,
        )
        return results[0] if results else {}
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
    placement_kwargs = {
        "symbol": str(command["gateway_symbol"]),
        "order_type": str(command["order_type"]),
        "side": str(command["gateway_side"]),
        "amount": Decimal(str(command["amount"])),
        "price": (
            Decimal(str(command["price"]))
            if command.get("price") is not None
            else None
        ),
        "trigger_price": (
            Decimal(str(command["stop_price"]))
            if command.get("stop_price") is not None
            else None
        ),
        "reduce_only": command.get("reduce_intent") == "reduce_position",
        "position_side": command.get("position_side"),
        "desired_leverage": command.get("desired_leverage"),
        "client_order_id": str(command["client_order_id"]),
    }
    if command.get("time_in_force"):
        placement_kwargs["time_in_force"] = str(command["time_in_force"])
    if command.get("post_only") is True:
        placement_kwargs["post_only"] = True
    return await gateway.place_order(**placement_kwargs)


def _execution_contract_blockers(command: dict[str, Any]) -> list[str]:
    if str(command.get("command_kind") or "") != "place_order":
        return []
    if str(command.get("order_role") or "").upper() != "TP1":
        return []
    try:
        validate_tp1_execution_contract(
            order_type=str(command.get("order_type") or ""),
            price=(
                Decimal(str(command["price"]))
                if command.get("price") is not None
                else None
            ),
            execution_style=command.get("execution_style"),
            time_in_force=command.get("time_in_force"),
            post_only=command.get("post_only") is True,
            market_fallback_allowed=(
                command.get("market_fallback_allowed") is True
            ),
        )
    except ValueError as exc:
        return [str(exc)]
    return []


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


def _placement_result_facts(result: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for key in (
        "selected_leverage",
        "exchange_configured_initial_leverage",
        "leverage_verified_at_ms",
        "filled_qty",
        "average_exec_price",
        "exchange_order_status",
    ):
        value = (
            result.get(key)
            if isinstance(result, dict)
            else getattr(result, key, None)
        )
        if value is not None:
            facts[key] = value
    return facts


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
        "order_role": command.get("order_role"),
        "command_source": command.get("command_source"),
        "source_command_id": command.get("source_command_id"),
        "netting_domain_key": command.get("netting_domain_key"),
        "exchange_write_called": exchange_write_called,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
    }


def _validate_lease_timeout_budget(
    *,
    lease_ms: int,
    dispatch_timeout_seconds: float | None,
) -> None:
    if lease_ms <= 0:
        raise ValueError("exchange_command_claim_lease_invalid")
    if dispatch_timeout_seconds is None:
        return
    required_lease_ms = int(dispatch_timeout_seconds * 1000) + (
        MIN_EXCHANGE_COMMAND_COMMIT_MARGIN_MS
    )
    if lease_ms < required_lease_ms:
        raise ValueError("exchange_command_lease_timeout_budget_invalid")


def _completion_now_ms(requested_now_ms: int | None) -> int:
    """Use fresh wall time in production while retaining deterministic tests."""

    return int(requested_now_ms or time.time() * 1000)
