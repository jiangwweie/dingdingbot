"""Decision-safe compact projection for scheduled runtime observation."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.domain.strategy_family_signal import StrategyFactObservation


WATCHER_SAFETY_BOOLEAN_KEYS = (
    "allow_action_time_ticket_materialization",
    "action_time_ticket_created",
    "runtime_execution_intent_draft_created",
    "recorded_execution_intent_created",
    "submit_authorization_created",
    "protection_plan_created",
    "executable_execution_intent_created",
    "local_registration_armed",
    "exchange_submit_armed",
    "execute_real_submit",
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "attempt_counter_mutated",
    "runtime_budget_mutated",
    "position_opened",
    "position_closed",
    "withdrawal_or_transfer_created",
)


def compact_json_size(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def validate_compact_text_array(field: str, values: Any) -> list[str]:
    if not isinstance(values, list) or len(values) > 64:
        raise ValueError(f"watcher_compact_projection_oversize:{field}")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or len(value.encode("utf-8")) > 256:
            raise ValueError(f"watcher_compact_projection_oversize:{field}")
        result.append(value)
    if compact_json_size(result) > 16 * 1024:
        raise ValueError(f"watcher_compact_projection_oversize:{field}")
    return result


def project_compact_text_array(field: str, values: Any) -> list[str]:
    """Bound transport cardinality while preserving the first decision blocker."""

    if not isinstance(values, list):
        raise ValueError(f"watcher_compact_projection_oversize:{field}")
    for value in values:
        if not isinstance(value, str) or len(value.encode("utf-8")) > 256:
            raise ValueError(f"watcher_compact_projection_oversize:{field}")
    if len(values) <= 64:
        return validate_compact_text_array(field, values)
    retained = list(values[:63])
    retained.append(f"additional_{field}_omitted:{len(values) - len(retained)}")
    return validate_compact_text_array(field, retained)


class WatcherCompactProjectionError(ValueError):
    """A bounded watcher response cannot represent the producer contract."""


class WatcherCompactBlocker(BaseModel):
    """Bounded typed business blocker for the watcher compact response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    stage: str | None = None
    severity: str | None = None
    detail: str | None = None
    recovery_action: str | None = None

    @field_validator("code")
    @classmethod
    def _bounded_code(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 256:
            raise WatcherCompactProjectionError(
                "watcher_compact_projection_oversize:blockers"
            )
        return value

    @field_validator("stage", "severity")
    @classmethod
    def _bounded_short_optional_text(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > 128:
            raise WatcherCompactProjectionError(
                "watcher_compact_projection_oversize:blockers"
            )
        return value

    @field_validator("detail")
    @classmethod
    def _bounded_detail(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > 512:
            raise WatcherCompactProjectionError(
                "watcher_compact_projection_oversize:blockers"
            )
        return value

    @field_validator("recovery_action")
    @classmethod
    def _bounded_recovery_action(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > 256:
            raise WatcherCompactProjectionError(
                "watcher_compact_projection_oversize:blockers"
            )
        return value

    @model_validator(mode="after")
    def _bounded_payload(self) -> "WatcherCompactBlocker":
        if compact_json_size(self.model_dump(mode="json")) > 2 * 1024:
            raise WatcherCompactProjectionError(
                "watcher_compact_projection_oversize:blockers"
            )
        return self


def project_compact_blocker_array(
    field: str,
    values: Any,
) -> list[WatcherCompactBlocker]:
    """Normalize legacy string and structured business blockers without coercion."""

    if not isinstance(values, list):
        raise WatcherCompactProjectionError(
            f"watcher_compact_projection_invalid:{field}"
        )
    projected = [_compact_blocker(field, value) for value in values[:64]]
    if len(values) > 64:
        projected[-1] = WatcherCompactBlocker(
            code=f"additional_{field}_omitted:{len(values) - 63}"
        )
    serialized = [item.model_dump(mode="json") for item in projected]
    if compact_json_size(serialized) > 64 * 1024:
        raise WatcherCompactProjectionError(
            f"watcher_compact_projection_oversize:{field}"
        )
    return projected


def compact_blocker_codes(values: Any) -> list[str]:
    """Derive stable codes from typed compact blockers in one response."""

    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, WatcherCompactBlocker):
            code = value.code
        elif isinstance(value, str):
            code = value
        elif isinstance(value, dict):
            code = str(value.get("code") or value.get("id") or "")
        else:
            continue
        if code:
            result.append(code)
    return result


def _compact_blocker(field: str, value: Any) -> WatcherCompactBlocker:
    if isinstance(value, str):
        return WatcherCompactBlocker(code=value)
    if not isinstance(value, dict):
        raise WatcherCompactProjectionError(
            f"watcher_compact_projection_invalid:{field}"
        )
    code = value.get("id") or value.get("code")
    if not isinstance(code, str) or not code:
        raise WatcherCompactProjectionError(
            f"watcher_compact_projection_invalid:{field}"
        )

    def optional_text(*keys: str) -> str | None:
        for key in keys:
            candidate = value.get(key)
            if candidate is not None:
                return candidate if isinstance(candidate, str) else None
        return None

    return WatcherCompactBlocker(
        code=code,
        stage=optional_text("stage", "blocked_stage"),
        severity=optional_text("severity"),
        detail=optional_text("detail", "evidence", "reason"),
        recovery_action=optional_text("recovery_action", "next_action"),
    )


class WatcherObservationResult(BaseModel):
    """Typed result of one actual non-executing watcher API attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempted: bool
    transport_state: Literal[
        "success", "http_error", "timeout", "deadline_exceeded"
    ]
    projection_state: Literal["valid", "invalid", "unavailable"]
    business_state: Literal[
        "computed", "business_blocked", "waiting_for_signal", "unknown"
    ]
    http_status: int | None = Field(default=None, ge=100, le=599)
    first_blocker_code: str | None = None
    completed_at_ms: int = Field(ge=0)


class ActionTimeDecisionFactProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_snapshot: dict[str, Any] = Field(default_factory=dict)
    evidence_payload: dict[str, Any] = Field(default_factory=dict)
    action_time_fact_values: dict[str, Any] = Field(default_factory=dict)
    fact_observations: tuple[StrategyFactObservation, ...] = ()

    @model_validator(mode="after")
    def validate_sizes(self) -> "ActionTimeDecisionFactProjection":
        payload = self.model_dump(mode="json")
        for field in (
            "signal_snapshot",
            "evidence_payload",
            "action_time_fact_values",
        ):
            if compact_json_size(payload[field]) > 64 * 1024:
                raise ValueError(f"watcher_compact_projection_oversize:{field}")
        if len(self.fact_observations) > 128 or compact_json_size(
            payload["fact_observations"]
        ) > 96 * 1024:
            raise ValueError(
                "watcher_compact_projection_oversize:fact_observations"
            )
        if compact_json_size(payload) > 192 * 1024:
            raise ValueError("watcher_compact_projection_oversize:decision_projection")
        return self


class WatcherRuntimeEffect(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    safety_invariants: dict[str, bool]

    @field_validator("safety_invariants", mode="before")
    @classmethod
    def reject_non_boolean_safety(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            raise ValueError("watcher_safety_projection_invalid:missing_map")
        for key in WATCHER_SAFETY_BOOLEAN_KEYS:
            if key not in value or type(value[key]) is not bool:
                raise ValueError(f"watcher_safety_projection_invalid:{key}")
        return value

    @model_validator(mode="after")
    def validate_safety(self) -> "WatcherRuntimeEffect":
        if set(self.safety_invariants) != set(WATCHER_SAFETY_BOOLEAN_KEYS):
            missing = next(
                (
                    key
                    for key in WATCHER_SAFETY_BOOLEAN_KEYS
                    if key not in self.safety_invariants
                ),
                "unexpected_key",
            )
            raise ValueError(f"watcher_safety_projection_invalid:{missing}")
        for key in WATCHER_SAFETY_BOOLEAN_KEYS:
            if type(self.safety_invariants[key]) is not bool:
                raise ValueError(f"watcher_safety_projection_invalid:{key}")
        return self
