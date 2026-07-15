"""Decision-safe compact projection for scheduled runtime observation."""

from __future__ import annotations

import json
from typing import Any

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
