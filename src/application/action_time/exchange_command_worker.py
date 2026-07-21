"""Short-transaction worker for all ticket-bound exchange side effects."""

from __future__ import annotations

import asyncio
from decimal import Decimal
import math
import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_command import (
    claim_next_exchange_command,
    expire_stale_exchange_command_claims,
    record_claimed_exchange_command_outcome,
)
from src.application.action_time.entry_effect_projection import (
    project_entry_effect,
    project_protection_result,
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
from src.domain.exceptions import InsufficientMarginError, InvalidOrderError
from src.domain.exchange_command_deadline import (
    ExchangeCommandDeadlineBudget,
    ExchangePhaseDeadlineDecision,
    decide_exchange_phase_budget,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandClaimScope,
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
    validate_tp1_execution_contract,
)


MIN_EXCHANGE_COMMAND_COMMIT_MARGIN_MS = 5_000


class _ExchangePhaseDeadlineBlocked(RuntimeError):
    def __init__(
        self,
        *,
        decision: ExchangePhaseDeadlineDecision,
        command: dict[str, Any],
        claim_started_at: float | None,
    ) -> None:
        super().__init__(decision.blocker or "exchange_command_deadline_blocked")
        self.decision = decision
        self.command = command
        self.claim_started_at = claim_started_at


async def run_one_ticket_bound_exchange_command(
    engine: sa.Engine,
    *,
    gateway: Any,
    worker_id: str,
    lease_ms: int = 15_000,
    now_ms: int | None = None,
    command_sources: tuple[str, ...],
    source_command_id: str | None = None,
    protected_submit_attempt_id: str | None = None,
    allowed_roles: tuple[str, ...] | None = None,
    allowed_command_kinds: tuple[str, ...] | None = None,
    netting_domain_key: str | None = None,
    dispatch_timeout_seconds: float | None = None,
    absolute_deadline_at: float | None = None,
    entry_network_timeout_seconds: float = 6.0,
    initial_stop_network_timeout_seconds: float = 6.0,
    tp1_network_timeout_seconds: float = 4.0,
    deadline_commit_margin_seconds: float = 5.0,
    entry_result_commit_reserve_seconds: float = 1.0,
    initial_stop_result_commit_reserve_seconds: float = 1.0,
    shutdown_reserve_seconds: float = 1.0,
    drain_initial_protection: bool = False,
) -> dict[str, Any]:
    """Run one durable command and optionally drain Entry -> Initial Stop.

    The default preserves the bounded generic-worker contract.  The official
    protected-submit runtime enables ``drain_initial_protection`` so a confirmed
    Entry does not wait for the next lifecycle timer before its initial stop.
    Each exchange I/O still has its own committed claim/result transaction.
    """

    deadline_budget = (
        ExchangeCommandDeadlineBudget(
            absolute_deadline_at=absolute_deadline_at,
            entry_network_timeout_seconds=entry_network_timeout_seconds,
            initial_stop_network_timeout_seconds=(
                initial_stop_network_timeout_seconds
            ),
            tp1_network_timeout_seconds=tp1_network_timeout_seconds,
            deadline_commit_margin_seconds=deadline_commit_margin_seconds,
            entry_result_commit_reserve_seconds=(
                entry_result_commit_reserve_seconds
            ),
            initial_stop_result_commit_reserve_seconds=(
                initial_stop_result_commit_reserve_seconds
            ),
            shutdown_reserve_seconds=shutdown_reserve_seconds,
        )
        if absolute_deadline_at is not None
        else None
    )
    if deadline_budget is None:
        _validate_lease_timeout_budget(
            lease_ms=lease_ms,
            dispatch_timeout_seconds=dispatch_timeout_seconds,
        )
    claim_scope = ExchangeCommandClaimScope(
        command_sources=command_sources,
        source_command_id=source_command_id,
        protected_submit_attempt_id=protected_submit_attempt_id,
        allowed_roles=allowed_roles,
        allowed_command_kinds=allowed_command_kinds,
        netting_domain_key=netting_domain_key,
    )
    primary = await _run_one_ticket_bound_exchange_command(
        engine,
        gateway=gateway,
        worker_id=worker_id,
        lease_ms=lease_ms,
        now_ms=now_ms,
        claim_scope=claim_scope,
        dispatch_timeout_seconds=dispatch_timeout_seconds,
        deadline_budget=deadline_budget,
    )
    phases = _phase_telemetry_items(primary)
    if not (
        drain_initial_protection
        and primary.get("status") == "command_confirmed"
        and primary.get("command_source") == "protected_submit"
        and primary.get("order_role") == "ENTRY"
    ):
        return _attach_exchange_telemetry(
            primary,
            phases=phases,
            deadline_budget=deadline_budget,
            entry_to_initial_stop_latency_ms=None,
        )

    drained: list[dict[str, Any]] = []
    entry_committed_at = (
        phases[0].get("result_committed_at_monotonic") if phases else None
    )
    entry_to_initial_stop_latency_ms: int | None = None
    drain_roles = ["SL"]
    if allowed_roles is None or "TP1" in allowed_roles:
        drain_roles.append("TP1")
    if allowed_roles is not None and "SL" not in allowed_roles:
        drain_roles = []
    for index, role in enumerate(drain_roles):
        next_result = await _run_one_ticket_bound_exchange_command(
            engine,
            gateway=gateway,
            worker_id=f"{worker_id}:initial-protection:{index}",
            lease_ms=lease_ms,
            now_ms=(now_ms + index + 1) if now_ms is not None else None,
            claim_scope=ExchangeCommandClaimScope(
                command_sources=("protected_submit",),
                source_command_id=str(primary.get("source_command_id") or ""),
                protected_submit_attempt_id=str(
                    primary.get("protected_submit_attempt_id") or ""
                ),
                allowed_roles=(role,),
                allowed_command_kinds=("place_order",),
                netting_domain_key=str(primary.get("netting_domain_key") or ""),
            ),
            dispatch_timeout_seconds=dispatch_timeout_seconds,
            deadline_budget=deadline_budget,
        )
        next_phases = _phase_telemetry_items(next_result)
        phases.extend(next_phases)
        if (
            role == "SL"
            and next_result.get("status") == "command_confirmed"
            and next_phases
        ):
            stop_committed_at = next_phases[0].get(
                "result_committed_at_monotonic"
            )
            if entry_committed_at is not None and stop_committed_at is not None:
                entry_to_initial_stop_latency_ms = max(
                    0,
                    int(
                        round(
                            (float(stop_committed_at) - float(entry_committed_at))
                            * 1000
                        )
                    ),
                )
        if next_result.get("status") == "no_prepared_command":
            break
        drained.append(next_result)
        if next_result.get("status") != "command_confirmed":
            break
    payload = {
        **primary,
        "initial_protection_drain": drained,
        "initial_protection_complete": any(
            _matches_initial_stop(primary=primary, candidate=item) for item in drained
        ),
    }
    return _attach_exchange_telemetry(
        payload,
        phases=phases,
        deadline_budget=deadline_budget,
        entry_to_initial_stop_latency_ms=entry_to_initial_stop_latency_ms,
    )


async def _run_one_ticket_bound_exchange_command(
    engine: sa.Engine,
    *,
    gateway: Any,
    worker_id: str,
    lease_ms: int = 15_000,
    now_ms: int | None = None,
    claim_scope: ExchangeCommandClaimScope,
    dispatch_timeout_seconds: float | None = None,
    deadline_budget: ExchangeCommandDeadlineBudget | None = None,
) -> dict[str, Any]:
    """Claim -> commit -> exchange I/O -> commit result.

    At most one command is dispatched.  No SQLAlchemy connection or transaction
    remains open while the gateway is awaited.
    """

    requested_now_ms = now_ms
    now_ms = int(now_ms or time.time() * 1000)
    phase_decision: ExchangePhaseDeadlineDecision | None = None
    claim_started_at = time.monotonic() if deadline_budget is not None else None
    dispatch_started_at: float | None = None
    command_blockers: list[str] = []
    try:
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
                    claim_scope=claim_scope,
                )
            )
            capability = lifecycle_mutation_capability_decision(conn)
            if command:
                command_blockers = _gateway_identity_blockers(
                    command, gateway
                ) + _execution_contract_blockers(command)
            if command and deadline_budget is not None:
                role = _deadline_role(str(command.get("order_role") or ""))
                dispatch_started_at = time.monotonic()
                phase_decision = decide_exchange_phase_budget(
                    deadline_budget,
                    role=role,
                    monotonic_now=dispatch_started_at,
                    lease_ms=lease_ms,
                    legacy_timeout_cap_seconds=dispatch_timeout_seconds,
                    require_pre_entry_reserve=(
                        role == "ENTRY"
                        and str(command.get("command_source") or "")
                        == "protected_submit"
                    ),
                )
                if not phase_decision.allowed:
                    if (
                        phase_decision.blocker
                        == "exchange_command_lease_timeout_budget_invalid"
                    ):
                        raise ValueError(phase_decision.blocker)
                    raise _ExchangePhaseDeadlineBlocked(
                        decision=phase_decision,
                        command=command,
                        claim_started_at=claim_started_at,
                    )
    except _ExchangePhaseDeadlineBlocked as blocked:
        return _deadline_blocked_result(blocked)
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
                ["exchange_command_outcome_unknown"] if expired else capability_blockers
            ),
        }

    effective_timeout_seconds = (
        phase_decision.effective_timeout_seconds
        if phase_decision is not None
        else dispatch_timeout_seconds
    )
    if dispatch_started_at is None:
        dispatch_started_at = time.monotonic()
    if command_blockers:
        commit_started_at = time.perf_counter()
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
            project_protection_result(conn, command=recorded, now_ms=now_ms)
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
        result_commit_latency_ms = _elapsed_ms(commit_started_at)
        result_committed_at = time.monotonic()
        result_payload = _result(
            "command_hard_stopped",
            recorded,
            blockers=command_blockers,
            exchange_write_called=False,
        )
        result_payload["lifecycle_completion"] = failure_completion
        return _attach_phase_result(
            result_payload,
            command=recorded,
            phase_decision=phase_decision,
            claim_started_at=claim_started_at,
            effective_timeout_seconds=effective_timeout_seconds,
            dispatch_started_at=dispatch_started_at,
            result_committed_at=result_committed_at,
            exchange_request_count=0,
            result_commit_latency_ms=result_commit_latency_ms,
        )

    try:
        exchange_result = (
            await asyncio.wait_for(
                _dispatch(command, gateway),
                timeout=effective_timeout_seconds,
            )
            if effective_timeout_seconds is not None
            else await _dispatch(command, gateway)
        )
    except (InvalidOrderError, InsufficientMarginError) as exc:
        now_ms = _completion_now_ms(requested_now_ms)
        blocker = str(exc)
        commit_started_at = time.perf_counter()
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
            project_protection_result(conn, command=recorded, now_ms=now_ms)
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
        result_commit_latency_ms = _elapsed_ms(commit_started_at)
        result_committed_at = time.monotonic()
        result_payload = _result(
            "command_rejected",
            recorded,
            blockers=[blocker],
            exchange_write_called=True,
        )
        if failure_completion:
            result_payload["lifecycle_completion"] = [failure_completion]
        return _attach_phase_result(
            result_payload,
            command=recorded,
            phase_decision=phase_decision,
            claim_started_at=claim_started_at,
            effective_timeout_seconds=effective_timeout_seconds,
            dispatch_started_at=dispatch_started_at,
            result_committed_at=result_committed_at,
            exchange_request_count=1,
            result_commit_latency_ms=result_commit_latency_ms,
        )
    except Exception as exc:
        now_ms = _completion_now_ms(requested_now_ms)
        commit_started_at = time.perf_counter()
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
            project_protection_result(conn, command=recorded, now_ms=now_ms)
            upsert_exchange_command_domain_hold(
                conn,
                command=recorded,
                blockers=["exchange_command_outcome_unknown"],
                now_ms=now_ms,
            )
        result_commit_latency_ms = _elapsed_ms(commit_started_at)
        result_committed_at = time.monotonic()
        result_payload = _result(
            "command_outcome_unknown",
            recorded,
            blockers=["exchange_command_outcome_unknown"],
            exchange_write_called=True,
        )
        return _attach_phase_result(
            result_payload,
            command=recorded,
            phase_decision=phase_decision,
            claim_started_at=claim_started_at,
            effective_timeout_seconds=effective_timeout_seconds,
            dispatch_started_at=dispatch_started_at,
            result_committed_at=result_committed_at,
            exchange_request_count=1,
            result_commit_latency_ms=result_commit_latency_ms,
        )

    accepted, exchange_order_id, error = _accepted_result(
        command,
        exchange_result,
    )
    placement_facts = _placement_result_facts(exchange_result)
    now_ms = _completion_now_ms(requested_now_ms)
    commit_started_at = time.perf_counter()
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
            project_protection_result(conn, command=recorded, now_ms=now_ms)
    except ValueError as exc:
        result_payload = _record_contradictory_exchange_result(
            engine,
            command=command,
            exchange_order_id=exchange_order_id,
            placement_facts=placement_facts,
            error=exc,
            now_ms=now_ms,
        )
        result_commit_latency_ms = _elapsed_ms(commit_started_at)
        result_committed_at = time.monotonic()
        return _attach_phase_result(
            result_payload,
            command=command,
            phase_decision=phase_decision,
            claim_started_at=claim_started_at,
            effective_timeout_seconds=effective_timeout_seconds,
            dispatch_started_at=dispatch_started_at,
            result_committed_at=result_committed_at,
            exchange_request_count=1,
            result_commit_latency_ms=result_commit_latency_ms,
        )
    result_commit_latency_ms = _elapsed_ms(commit_started_at)
    result_committed_at = time.monotonic()
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
    return _attach_phase_result(
        result_payload,
        command=recorded,
        phase_decision=phase_decision,
        claim_started_at=claim_started_at,
        effective_timeout_seconds=effective_timeout_seconds,
        dispatch_started_at=dispatch_started_at,
        result_committed_at=result_committed_at,
        exchange_request_count=1,
        result_commit_latency_ms=result_commit_latency_ms,
    )


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
                "exchange_order_status": placement_facts.get("exchange_order_status"),
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
        project_protection_result(conn, command=recorded, now_ms=now_ms)
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
    claim_scope: ExchangeCommandClaimScope,
) -> dict[str, Any]:
    if lifecycle_mutation_capability_decision(conn)["blockers"]:
        return {}
    return claim_next_exchange_command(
        conn,
        claim_owner=claim_owner,
        now_ms=now_ms,
        lease_ms=lease_ms,
        claim_scope=claim_scope,
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
            Decimal(str(command["price"])) if command.get("price") is not None else None
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
            market_fallback_allowed=(command.get("market_fallback_allowed") is True),
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
            result.get(key) if isinstance(result, dict) else getattr(result, key, None)
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
        "protected_submit_attempt_id": command.get("protected_submit_attempt_id"),
        "ticket_id": command.get("ticket_id"),
        "exposure_episode_id": command.get("exposure_episode_id"),
        "command_state": command.get("command_state"),
        "command_kind": command.get("command_kind"),
        "order_role": command.get("order_role"),
        "command_source": command.get("command_source"),
        "source_command_id": command.get("source_command_id"),
        "netting_domain_key": command.get("netting_domain_key"),
        "amount": command.get("amount"),
        "executed_qty": command.get("executed_qty"),
        "reduce_only": command.get("reduce_only"),
        "reduce_intent": command.get("reduce_intent"),
        "exchange_write_called": exchange_write_called,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
    }


def _matches_initial_stop(
    *,
    primary: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    """Prove that one accepted SL is this ENTRY's initial-stop barrier."""

    expected_quantity = primary.get("executed_qty")
    if expected_quantity is None:
        return False
    try:
        quantity_matches = Decimal(str(candidate.get("amount"))) == Decimal(
            str(expected_quantity)
        )
    except (ArithmeticError, TypeError, ValueError):
        return False
    return (
        candidate.get("status") == "command_confirmed"
        and candidate.get("command_state")
        in {"confirmed_submitted", "reconciled_submitted"}
        and candidate.get("order_role") == "SL"
        and candidate.get("command_kind") == "place_order"
        and candidate.get("source_command_id") == primary.get("source_command_id")
        and candidate.get("protected_submit_attempt_id")
        == primary.get("protected_submit_attempt_id")
        and candidate.get("ticket_id") == primary.get("ticket_id")
        and candidate.get("exposure_episode_id") == primary.get("exposure_episode_id")
        and candidate.get("netting_domain_key") == primary.get("netting_domain_key")
        and candidate.get("reduce_only") in {True, 1}
        and candidate.get("reduce_intent") == "reduce_position"
        and quantity_matches
    )


def _deadline_role(order_role: str) -> str:
    role = str(order_role or "").upper()
    if role == "ENTRY":
        return "ENTRY"
    if role == "TP1":
        return "TP1"
    return "SL"


def _deadline_blocked_result(
    blocked: _ExchangePhaseDeadlineBlocked,
) -> dict[str, Any]:
    command = {**blocked.command, "command_state": "prepared"}
    blocker = blocked.decision.blocker or "exchange_command_deadline_blocked"
    payload = _result(
        "hard_safety_stop",
        command,
        blockers=[blocker],
        exchange_write_called=False,
    )
    return _attach_phase_result(
        payload,
        command=command,
        phase_decision=blocked.decision,
        claim_started_at=blocked.claim_started_at,
        effective_timeout_seconds=blocked.decision.effective_timeout_seconds,
        dispatch_started_at=None,
        result_committed_at=None,
        exchange_request_count=0,
        result_commit_latency_ms=0,
    )


def _attach_phase_result(
    payload: dict[str, Any],
    *,
    command: dict[str, Any],
    phase_decision: ExchangePhaseDeadlineDecision | None,
    claim_started_at: float | None,
    effective_timeout_seconds: float | None,
    dispatch_started_at: float | None,
    result_committed_at: float | None,
    exchange_request_count: int,
    result_commit_latency_ms: int,
) -> dict[str, Any]:
    deadline_remaining_before = (
        phase_decision.deadline_remaining_seconds
        if phase_decision is not None
        else None
    )
    deadline_remaining_after = (
        max(0.0, phase_decision.absolute_deadline_at - time.monotonic())
        if phase_decision is not None
        else None
    )
    phase = {
        "schema": "brc.exchange_command_phase_telemetry.v1",
        "order_role": command.get("order_role"),
        "command_source": command.get("command_source"),
        "source_command_id": command.get("source_command_id"),
        "protected_submit_attempt_id": command.get(
            "protected_submit_attempt_id"
        ),
        "exchange_command_id": command.get("exchange_command_id"),
        "effective_timeout_seconds": effective_timeout_seconds,
        "absolute_deadline_at": (
            phase_decision.absolute_deadline_at
            if phase_decision is not None
            else None
        ),
        "deadline_remaining_before_seconds": deadline_remaining_before,
        "deadline_remaining_after_seconds": deadline_remaining_after,
        "claim_started_at_monotonic": claim_started_at,
        "dispatch_started_at_monotonic": dispatch_started_at,
        "result_committed_at_monotonic": result_committed_at,
        "exchange_request_count": int(exchange_request_count),
        "result_status": payload.get("status"),
        "result_commit_latency_ms": max(0, int(result_commit_latency_ms)),
    }
    return {**payload, "exchange_phase_telemetry": phase}


def _phase_telemetry_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    phase = payload.get("exchange_phase_telemetry")
    return [dict(phase)] if isinstance(phase, dict) else []


def _attach_exchange_telemetry(
    payload: dict[str, Any],
    *,
    phases: list[dict[str, Any]],
    deadline_budget: ExchangeCommandDeadlineBudget | None,
    entry_to_initial_stop_latency_ms: int | None,
) -> dict[str, Any]:
    telemetry = {
        "schema": "brc.ticket_bound_exchange_command_telemetry.v1",
        "absolute_deadline_at": (
            deadline_budget.absolute_deadline_at
            if deadline_budget is not None
            else None
        ),
        "exchange_request_count": sum(
            int(item.get("exchange_request_count") or 0) for item in phases
        ),
        "phases": phases,
        "entry_to_initial_stop_latency_ms": entry_to_initial_stop_latency_ms,
        "deadline_budget": (
            deadline_budget.model_dump()
            if deadline_budget is not None
            else None
        ),
    }
    return {**payload, "exchange_telemetry": telemetry}


def _elapsed_ms(started_at: float) -> int:
    return max(0, int(round((time.perf_counter() - started_at) * 1000)))


def _validate_lease_timeout_budget(
    *,
    lease_ms: int,
    dispatch_timeout_seconds: float | None,
) -> None:
    if lease_ms <= 0:
        raise ValueError("exchange_command_claim_lease_invalid")
    if dispatch_timeout_seconds is None:
        return
    if (
        not math.isfinite(dispatch_timeout_seconds)
        or dispatch_timeout_seconds <= 0
    ):
        raise ValueError("exchange_command_dispatch_timeout_invalid")
    required_lease_ms = math.ceil(dispatch_timeout_seconds * 1000) + (
        MIN_EXCHANGE_COMMAND_COMMIT_MARGIN_MS
    )
    if lease_ms < required_lease_ms:
        raise ValueError("exchange_command_lease_timeout_budget_invalid")


def _completion_now_ms(requested_now_ms: int | None) -> int:
    """Use fresh wall time in production while retaining deterministic tests."""

    return int(requested_now_ms or time.time() * 1000)
