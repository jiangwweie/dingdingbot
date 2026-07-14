"""Typed Owner readmodel projection helpers."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
from typing import Any

from src.application.action_time.lifecycle_safety_core import (
    LifecycleControlState,
    lifecycle_decision_for_status,
)


@dataclass(frozen=True)
class OwnerConsoleDetailSourceProjection:
    status: str
    owner_label: str
    reason: str
    summary: dict[str, Any] | None = None
    count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "owner_label": self.owner_label,
            "reason": self.reason,
        }
        if self.count is not None:
            payload["count"] = self.count
        if self.summary is not None:
            payload["summary"] = copy.deepcopy(self.summary)
        return payload


@dataclass(frozen=True)
class OwnerConsoleBinaryLabelSourceProjection:
    status: str
    ready_label: str
    not_ready_label: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return owner_console_detail_source(
            status=self.status,
            owner_label=(
                self.ready_label if self.status == "ready" else self.not_ready_label
            ),
            reason=self.reason,
        )


@dataclass(frozen=True)
class OwnerConsoleRealOrderReadinessProjection:
    status: str
    owner_label: str
    owner_detail: str
    ready_for_real_order_action: bool
    pass_count: int
    waiting_count: int
    blocked_count: int
    submit_blocking_keys: list[str]
    submit_blocker_review: dict[str, Any]
    non_authority_checkpoint: str
    matrix: list[dict[str, Any]]
    source_health: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "owner_label": self.owner_label,
            "owner_detail": self.owner_detail,
            "ready_for_real_order_action": self.ready_for_real_order_action,
            "pass_count": self.pass_count,
            "waiting_count": self.waiting_count,
            "blocked_count": self.blocked_count,
            "submit_blocking_keys": list(self.submit_blocking_keys),
            "submit_blocker_review": dict(self.submit_blocker_review),
            "non_authority_checkpoint": self.non_authority_checkpoint,
            "matrix": list(self.matrix),
            "source_health": dict(self.source_health),
        }


@dataclass(frozen=True)
class OwnerConsoleOwnerStateProjection:
    status: str
    label: str
    reason: str
    non_authority_checkpoint: str
    checkpoint_source: str = "owner_console_owner_state_projection"
    needs_owner_action: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "label": self.label,
            "reason": self.reason,
            "non_authority_checkpoint": self.non_authority_checkpoint,
            "checkpoint_source": self.checkpoint_source,
            "needs_owner_action": self.needs_owner_action,
        }


def owner_console_detail_source(
    *,
    status: str,
    owner_label: str,
    reason: str,
    summary: dict[str, Any] | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    return OwnerConsoleDetailSourceProjection(
        status=status,
        owner_label=owner_label,
        reason=reason,
        summary=summary,
        count=count,
    ).to_dict()


def owner_console_owner_state_projection(
    *,
    status: str,
    label: str,
    reason: str,
    non_authority_checkpoint: str,
    checkpoint_source: str = "owner_console_owner_state_projection",
    needs_owner_action: bool = False,
) -> dict[str, Any]:
    return OwnerConsoleOwnerStateProjection(
        status=status,
        label=label,
        reason=reason,
        non_authority_checkpoint=non_authority_checkpoint,
        checkpoint_source=checkpoint_source,
        needs_owner_action=needs_owner_action,
    ).to_dict()


def owner_console_binary_label_source(
    *,
    status: str,
    ready_label: str,
    not_ready_label: str,
    reason: str,
) -> dict[str, Any]:
    return OwnerConsoleBinaryLabelSourceProjection(
        status=status,
        ready_label=ready_label,
        not_ready_label=not_ready_label,
        reason=reason,
    ).to_dict()


def owner_state_with_explicit_action_authority(
    *,
    owner_state: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> dict[str, Any]:
    allowed_actions = [
        str(item)
        for item in action_time_resume.get("allowed_auto_actions") or []
        if item
    ]
    if not allowed_actions:
        return owner_state
    projection = owner_state_without_legacy_input_recovery_action(owner_state)
    return {
        **projection,
        "non_authority_checkpoint": allowed_actions[0],
    }


def owner_non_authority_checkpoint(
    *owner_states: dict[str, Any],
    default: str,
) -> str:
    for owner_state in owner_states:
        if not isinstance(owner_state, dict):
            continue
        value = owner_state.get("non_authority_checkpoint")
        if value:
            return str(value)
    return default


def owner_state_source_checkpoint(
    owner_state: dict[str, Any],
    *,
    default: str,
) -> tuple[str, str]:
    """Resolve projection checkpoints from source evidence, not action authority."""
    if isinstance(owner_state, dict):
        value = owner_state.get("non_authority_checkpoint")
        if value:
            return str(value), str(
                owner_state.get("checkpoint_source") or "non_authority_checkpoint"
            )
    return default, "owner_state_default"


def owner_state_without_legacy_input_recovery_action(
    owner_state: dict[str, Any],
) -> dict[str, Any]:
    projection = dict(owner_state)
    projection.pop("automatic_recovery_action", None)
    return projection


def ticket_bound_lifecycle_owner_feedback(
    lifecycle_row: dict[str, Any],
) -> dict[str, Any]:
    """Project one PG lifecycle row into a non-authority Owner product state."""

    status = str(lifecycle_row.get("status") or "blocked")
    blockers = _lifecycle_blockers(lifecycle_row.get("blockers"))
    first_blocker = str(lifecycle_row.get("first_blocker") or "")
    if first_blocker and first_blocker not in blockers:
        blockers.insert(0, first_blocker)
    owner_action_required = any(
        blocker.endswith("_retry_limit_exhausted")
        or blocker.startswith("owner_intervention_required")
        for blocker in blockers
    )
    decision = lifecycle_decision_for_status(
        status,
        blockers=blockers,
        owner_action_required=owner_action_required,
    )
    label = {
        "processing": "处理中",
        "temporarily_unavailable": "暂不可用",
        "needs_intervention": "需要介入",
        "completed": "已完成",
    }[decision.owner_state.value]
    if decision.control_state is LifecycleControlState.RECOVERY_REQUIRED:
        label = "自动恢复中"
    return {
        "status": decision.owner_state.value,
        "label": label,
        "reason": decision.first_blocker or decision.status,
        "ticket_id": lifecycle_row.get("ticket_id"),
        "strategy_group_id": lifecycle_row.get("strategy_group_id"),
        "symbol": lifecycle_row.get("symbol"),
        "side": lifecycle_row.get("side"),
        "lifecycle_status": decision.status,
        "phase": decision.phase.value,
        "protection_state": decision.protection_state.value,
        "reconciliation_state": decision.reconciliation_state.value,
        "control_state": decision.control_state.value,
        "next_action": decision.next_action,
        "non_authority_checkpoint": decision.next_action,
        "owner_action_required": decision.owner_action_required,
        "exchange_write_authorized": False,
    }


def _lifecycle_blockers(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item)]
        return [str(parsed)]
    return []
