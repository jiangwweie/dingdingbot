"""In-process typed Action-Time coordinator.

The coordinator replaces child-process/stdout semantics on the production
critical path.  It binds one Invocation and carries its deadline through each
direct application call; it never grants submit or exchange-write authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable

import sqlalchemy as sa

from src.application.action_time.finalgate_preflight import (
    materialize_action_time_finalgate_preflight,
)
from src.application.action_time.operation_layer_handoff import (
    materialize_action_time_operation_layer_handoff,
)
from src.application.action_time.runtime_safety_state import (
    materialize_ticket_bound_runtime_safety_state,
)
from src.application.action_time.ticket_materialization_sequence import (
    materialize_action_time_ticket_sequence,
)
from src.domain.action_time_deadline import ActionTimeDeadline


@dataclass(frozen=True)
class TypedActionTimeStep:
    name: str
    status: str
    blockers: tuple[str, ...]
    identity: dict[str, str]


@dataclass(frozen=True)
class TypedActionTimeCoordinatorResult:
    status: str
    action_time_invocation_id: str
    ticket_id: str | None
    finalgate_pass_id: str | None
    operation_layer_handoff_id: str | None
    steps: tuple[TypedActionTimeStep, ...]
    first_blocker: str | None


def coordinate_action_time_invocation(
    engine: sa.Engine,
    *,
    action_time_invocation_id: str,
    deadline: ActionTimeDeadline,
    env_file: Path | None,
    base_url: str,
    account_timeout_seconds: float = 12,
    wall_clock_ms: Callable[[], int] | None = None,
    monotonic_clock_ms: Callable[[], int] | None = None,
) -> TypedActionTimeCoordinatorResult:
    """Advance exactly one Invocation through Ticket-bound no-write readiness."""

    wall_clock = wall_clock_ms or (lambda: int(time.time() * 1000))
    monotonic_clock = monotonic_clock_ms or (lambda: int(time.monotonic() * 1000))
    invocation_id = str(action_time_invocation_id or "").strip()
    if not invocation_id:
        raise ValueError("typed_action_time_invocation_id_required")
    steps: list[TypedActionTimeStep] = []

    def blocked(name: str, blocker: str) -> TypedActionTimeCoordinatorResult:
        steps.append(
            TypedActionTimeStep(
                name=name,
                status="blocked",
                blockers=(blocker,),
                identity={"action_time_invocation_id": invocation_id},
            )
        )
        return TypedActionTimeCoordinatorResult(
            status="business_blocked",
            action_time_invocation_id=invocation_id,
            ticket_id=None,
            finalgate_pass_id=None,
            operation_layer_handoff_id=None,
            steps=tuple(steps),
            first_blocker=blocker,
        )

    def remaining_timeout_seconds() -> float | None:
        remaining_ms = deadline.remaining_ms(monotonic_now_ms=monotonic_clock())
        if remaining_ms <= 0:
            return None
        return min(account_timeout_seconds, max(0.05, remaining_ms / 1000))

    timeout_seconds = remaining_timeout_seconds()
    if timeout_seconds is None:
        return blocked("materialize_account_safe_facts", "action_time_deadline_expired")
    account = _materialize_account_safe_facts(
        engine,
        action_time_invocation_id=invocation_id,
        env_file=env_file,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    account_blocker = str(account.get("business_blocker") or "").strip()
    steps.append(
        _step(
            "materialize_account_safe_facts",
            account,
            {"action_time_invocation_id": invocation_id},
        )
    )
    if account_blocker:
        return blocked("materialize_account_safe_facts", account_blocker)
    if remaining_timeout_seconds() is None:
        return blocked("materialize_action_time_ticket_sequence", "action_time_deadline_expired")

    now_ms = wall_clock()
    with engine.begin() as conn:
        ticket_sequence = materialize_action_time_ticket_sequence(
            conn,
            action_time_invocation_id=invocation_id,
            stage_at_ms=now_ms,
        )
    ticket_id = str(ticket_sequence.get("ticket", {}).get("ticket_id") or "").strip()
    steps.append(
        _step(
            "materialize_action_time_ticket_sequence",
            ticket_sequence,
            {
                "action_time_invocation_id": invocation_id,
                "ticket_id": ticket_id,
            },
        )
    )
    if str(ticket_sequence.get("status") or "") not in {
        "action_time_ticket_sequence_committed",
        "action_time_ticket_sequence_signal_already_processed",
    } or not ticket_id:
        return blocked(
            "materialize_action_time_ticket_sequence",
            _first_blocker(ticket_sequence, "action_time_ticket_not_created"),
        )
    if remaining_timeout_seconds() is None:
        return blocked("materialize_action_time_finalgate_preflight", "action_time_deadline_expired")

    with engine.begin() as conn:
        finalgate = materialize_action_time_finalgate_preflight(
            conn,
            ticket_id=ticket_id,
            now_ms=wall_clock(),
        )
    finalgate_pass_id = str(finalgate.get("finalgate_pass_id") or "").strip()
    steps.append(
        _step(
            "materialize_action_time_finalgate_preflight",
            finalgate,
            {"ticket_id": ticket_id, "finalgate_pass_id": finalgate_pass_id},
        )
    )
    if str(finalgate.get("status") or "") not in {
        "finalgate_ready",
        "finalgate_already_ready",
    } or not finalgate_pass_id:
        return blocked(
            "materialize_action_time_finalgate_preflight",
            _first_blocker(finalgate, "action_time_finalgate_not_ready"),
        )
    if remaining_timeout_seconds() is None:
        return blocked("materialize_action_time_operation_layer_handoff", "action_time_deadline_expired")

    with engine.begin() as conn:
        handoff = materialize_action_time_operation_layer_handoff(
            conn,
            ticket_id=ticket_id,
            finalgate_pass_id=finalgate_pass_id,
            now_ms=wall_clock(),
        )
    handoff_id = str(handoff.get("operation_layer_handoff_id") or "").strip()
    steps.append(
        _step(
            "materialize_action_time_operation_layer_handoff",
            handoff,
            {
                "ticket_id": ticket_id,
                "finalgate_pass_id": finalgate_pass_id,
                "operation_layer_handoff_id": handoff_id,
            },
        )
    )
    if str(handoff.get("status") or "") not in {
        "operation_layer_handoff_ready",
        "operation_layer_handoff_already_exists",
    } or not handoff_id:
        return blocked(
            "materialize_action_time_operation_layer_handoff",
            _first_blocker(handoff, "action_time_operation_layer_handoff_not_ready"),
        )
    if remaining_timeout_seconds() is None:
        return blocked("materialize_ticket_bound_runtime_safety_state", "action_time_deadline_expired")

    with engine.begin() as conn:
        safety = materialize_ticket_bound_runtime_safety_state(
            conn,
            ticket_id=ticket_id,
            operation_layer_handoff_id=handoff_id,
            now_ms=wall_clock(),
        )
    steps.append(
        _step(
            "materialize_ticket_bound_runtime_safety_state",
            safety,
            {
                "ticket_id": ticket_id,
                "operation_layer_handoff_id": handoff_id,
            },
        )
    )
    if str(safety.get("status") or "") != "runtime_safety_state_ready":
        return blocked(
            "materialize_ticket_bound_runtime_safety_state",
            _first_blocker(safety, "ticket_bound_runtime_safety_not_ready"),
        )
    return TypedActionTimeCoordinatorResult(
        status="ready",
        action_time_invocation_id=invocation_id,
        ticket_id=ticket_id,
        finalgate_pass_id=finalgate_pass_id,
        operation_layer_handoff_id=handoff_id,
        steps=tuple(steps),
        first_blocker=None,
    )


def _step(name: str, payload: dict[str, Any], identity: dict[str, str]) -> TypedActionTimeStep:
    return TypedActionTimeStep(
        name=name,
        status=str(payload.get("status") or "missing_status"),
        blockers=tuple(str(item) for item in payload.get("blockers") or [] if str(item)),
        identity={key: value for key, value in identity.items() if value},
    )


def _first_blocker(payload: dict[str, Any], fallback: str) -> str:
    blockers = payload.get("blockers") or []
    return str(blockers[0]) if blockers else fallback


def _materialize_account_safe_facts(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Delay optional streaming-reader import until real readonly collection."""

    from src.application.action_time.account_safe_facts import (
        materialize_account_safe_facts,
    )

    return materialize_account_safe_facts(*args, **kwargs)
