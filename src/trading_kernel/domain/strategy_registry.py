"""Canonical contracts for the six Owner-accepted strategy Events."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.ticket import EntryOrderType

FactValueType = Literal["boolean", "decimal"]
FactRole = Literal[
    "condition",
    "protection_reference",
    "identity_reference",
    "lifecycle_reference",
    "disable",
]
Timeframe = Literal["15m", "1h"]
PositionSide = Literal["long", "short"]


class RegistrySeedConflict(RuntimeError):
    """Existing PostgreSQL Registry semantics differ from the canonical seed."""


class RegistrySeedResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registry_semantic_hash: str
    inserted_strategy_group_count: int = 0
    inserted_strategy_version_count: int = 0
    inserted_event_count: int = 0
    inserted_exit_policy_count: int = 0
    inserted_fact_definition_count: int = 0
    inserted_event_fact_count: int = 0

    @property
    def total_inserted_count(self) -> int:
        return (
            self.inserted_strategy_group_count
            + self.inserted_strategy_version_count
            + self.inserted_event_count
            + self.inserted_exit_policy_count
            + self.inserted_fact_definition_count
            + self.inserted_event_fact_count
        )


class RegisteredFactRequirement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_definition_id: str
    fact_name: str
    value_type: FactValueType
    role: FactRole
    freshness_ms: int

    @field_validator("fact_definition_id", "fact_name", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("registered fact identity must be non-blank")
        return normalized

    @field_validator("freshness_ms")
    @classmethod
    def _require_positive_freshness(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("registered fact freshness must be positive")
        return value

    @model_validator(mode="after")
    def _validate_role_value_type(self) -> RegisteredFactRequirement:
        if (
            self.role
            in {
                "protection_reference",
                "identity_reference",
                "lifecycle_reference",
            }
            and self.value_type != "decimal"
        ):
            raise ValueError("reference facts must be decimal")
        if self.role in {"condition", "disable"} and self.value_type != "boolean":
            raise ValueError("condition and disable facts must be boolean")
        return self


class RegisteredStrategyContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    event_id: str
    position_side: PositionSide
    timeframe: Timeframe
    freshness_window_ms: int
    event_time_authority: Literal["trigger_candle_close_time_ms"]
    entry_order_type: EntryOrderType
    protection_reference_fact: str
    pre_tp1_reclaim_reference_fact: str | None = None
    exposure_session_end_reference_fact: str | None = None
    required_facts: tuple[RegisteredFactRequirement, ...]
    disable_facts: tuple[RegisteredFactRequirement, ...] = ()
    exit_policy_id: str
    status: Literal["active", "disabled"] = "active"

    @field_validator(
        "strategy_group_id",
        "strategy_version_id",
        "event_spec_id",
        "event_id",
        "protection_reference_fact",
        "exit_policy_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("registered strategy identity must be non-blank")
        return normalized

    @field_validator(
        "pre_tp1_reclaim_reference_fact",
        "exposure_session_end_reference_fact",
        mode="before",
    )
    @classmethod
    def _normalize_optional_fact_identity(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("freshness_window_ms")
    @classmethod
    def _require_positive_freshness(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("strategy freshness window must be positive")
        return value

    @model_validator(mode="after")
    def _validate_contract(self) -> RegisteredStrategyContract:
        version_match = re.fullmatch(
            rf"sgv:{re.escape(self.strategy_group_id)}:v([1-9][0-9]*)",
            self.strategy_version_id,
        )
        if version_match is None:
            raise ValueError("strategy version identity must be canonical")
        version = version_match.group(1)
        expected_event = (
            f"event_spec:{self.strategy_group_id}:{self.event_id}:v{version}"
        )
        if self.event_spec_id != expected_event:
            raise ValueError("event spec identity must match the strategy version")

        required_names = [item.fact_name for item in self.required_facts]
        disable_names = [item.fact_name for item in self.disable_facts]
        if not required_names or len(required_names) != len(set(required_names)):
            raise ValueError("required fact names must be non-empty and unique")
        if len(disable_names) != len(set(disable_names)):
            raise ValueError("disable fact names must be unique")
        if set(required_names) & set(disable_names):
            raise ValueError("required and disable facts must be disjoint")
        if any(item.role == "disable" for item in self.required_facts):
            raise ValueError("required facts cannot use the disable role")
        if any(item.role != "disable" for item in self.disable_facts):
            raise ValueError("disable facts must use the disable role")

        reference_facts = [
            item.fact_name
            for item in self.required_facts
            if item.role == "protection_reference"
        ]
        if reference_facts != [self.protection_reference_fact]:
            raise ValueError("contract requires exactly one protection reference fact")
        pre_tp1_names = (
            self.pre_tp1_reclaim_reference_fact,
            self.exposure_session_end_reference_fact,
        )
        if (pre_tp1_names[0] is None) != (pre_tp1_names[1] is None):
            raise ValueError("pre-TP1 reclaim and Session references must be paired")
        if pre_tp1_names[0] is not None:
            requirements_by_name = {
                item.fact_name: item for item in self.required_facts
            }
            if any(
                fact_name not in requirements_by_name
                or requirements_by_name[fact_name].role != "lifecycle_reference"
                for fact_name in pre_tp1_names
            ):
                raise ValueError(
                    "pre-TP1 plan must use lifecycle reference facts"
                )
        if any(
            item.freshness_ms != self.freshness_window_ms
            for item in (*self.required_facts, *self.disable_facts)
        ):
            raise ValueError("registered facts must use the Event freshness window")

        return self

    @property
    def required_fact_names(self) -> tuple[str, ...]:
        return tuple(item.fact_name for item in self.required_facts)

    @property
    def disable_fact_names(self) -> tuple[str, ...]:
        return tuple(item.fact_name for item in self.disable_facts)

def registered_strategy_contracts() -> tuple[RegisteredStrategyContract, ...]:
    """Return the exact six Event contracts recovered from committed runtime code."""

    return (
        _contract(
            strategy_group_id="CPM-RO-001",
            event_id="CPM-LONG",
            position_side="long",
            timeframe="1h",
            facts=(
                ("htf_trend_intact", "condition"),
                ("reclaim_confirmed", "condition"),
                ("pullback_low_reference", "protection_reference"),
            ),
            protection_reference_fact="pullback_low_reference",
        ),
        _contract(
            strategy_group_id="MPG-001",
            event_id="MPG-LONG",
            position_side="long",
            timeframe="1h",
            facts=(
                ("momentum_persistence_confirmed", "condition"),
                ("leader_strength_confirmed", "condition"),
                ("momentum_floor_reference", "protection_reference"),
            ),
            protection_reference_fact="momentum_floor_reference",
        ),
        _contract(
            strategy_group_id="MI-001",
            event_id="MI-LONG",
            position_side="long",
            timeframe="1h",
            facts=(
                ("impulse_confirmed", "condition"),
                ("relative_strength_confirmed", "condition"),
                ("impulse_invalidation_reference", "protection_reference"),
            ),
            protection_reference_fact="impulse_invalidation_reference",
        ),
        _contract(
            strategy_group_id="SOR-001",
            event_id="SOR-LONG",
            position_side="long",
            timeframe="15m",
            facts=(
                ("opening_range_defined_v3", "condition"),
                ("breakout_edge_crossed_v3", "condition"),
                ("opening_range_high_reference_v3", "lifecycle_reference"),
                ("opening_range_low_reference_v3", "protection_reference"),
                ("session_start_ms_v3", "identity_reference"),
                ("session_end_ms_v3", "lifecycle_reference"),
            ),
            protection_reference_fact="opening_range_low_reference_v3",
            pre_tp1_reclaim_reference_fact="opening_range_high_reference_v3",
            exposure_session_end_reference_fact="session_end_ms_v3",
            semantic_version=3,
            fact_version=3,
            exit_policy_variant="sor-v3-right-tail-v1",
        ),
        _contract(
            strategy_group_id="SOR-001",
            event_id="SOR-SHORT",
            position_side="short",
            timeframe="15m",
            facts=(
                ("opening_range_defined_v3", "condition"),
                ("breakdown_edge_crossed_v3", "condition"),
                ("opening_range_low_reference_v3", "lifecycle_reference"),
                ("opening_range_high_reference_v3", "protection_reference"),
                ("session_start_ms_v3", "identity_reference"),
                ("session_end_ms_v3", "lifecycle_reference"),
            ),
            protection_reference_fact="opening_range_high_reference_v3",
            pre_tp1_reclaim_reference_fact="opening_range_low_reference_v3",
            exposure_session_end_reference_fact="session_end_ms_v3",
            semantic_version=3,
            fact_version=3,
            exit_policy_variant="sor-v3-right-tail-v1",
        ),
        _contract(
            strategy_group_id="BRF2-001",
            event_id="BRF2-SHORT",
            position_side="short",
            timeframe="1h",
            facts=(
                ("rally_failure_confirmed", "condition"),
                ("short_side_not_disabled", "condition"),
                ("rally_high_reference", "protection_reference"),
            ),
            protection_reference_fact="rally_high_reference",
            disable_fact_names=("strong_uptrend_disable",),
        ),
    )


def build_registry_semantic_hash(
    contracts: tuple[RegisteredStrategyContract, ...],
) -> str:
    """Build one deterministic identity for the complete registered semantics."""

    event_ids = [item.event_spec_id for item in contracts]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("registry semantic hash input contains duplicate Events")
    canonical = json.dumps(
        [
            item.model_dump(mode="json")
            for item in sorted(contracts, key=lambda value: value.event_spec_id)
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def strategy_contract_for(event_spec_id: str) -> RegisteredStrategyContract:
    normalized = str(event_spec_id or "").strip()
    matches = [
        contract
        for contract in registered_strategy_contracts()
        if contract.event_spec_id == normalized
    ]
    if len(matches) != 1:
        raise ValueError("registered Event must resolve exactly one contract")
    return matches[0]


def _contract(
    *,
    strategy_group_id: str,
    event_id: str,
    position_side: PositionSide,
    timeframe: Timeframe,
    facts: tuple[
        tuple[
            str,
            Literal[
                "condition",
                "protection_reference",
                "identity_reference",
                "lifecycle_reference",
            ],
        ],
        ...,
    ],
    protection_reference_fact: str,
    pre_tp1_reclaim_reference_fact: str | None = None,
    exposure_session_end_reference_fact: str | None = None,
    disable_fact_names: tuple[str, ...] = (),
    status: Literal["active", "disabled"] = "active",
    semantic_version: int = 2,
    fact_version: int = 1,
    exit_policy_variant: str = "right-tail-v1",
) -> RegisteredStrategyContract:
    freshness_window_ms = 900_000 if timeframe == "15m" else 3_600_000
    return RegisteredStrategyContract(
        strategy_group_id=strategy_group_id,
        strategy_version_id=f"sgv:{strategy_group_id}:v{semantic_version}",
        event_spec_id=(
            f"event_spec:{strategy_group_id}:{event_id}:v{semantic_version}"
        ),
        event_id=event_id,
        position_side=position_side,
        timeframe=timeframe,
        freshness_window_ms=freshness_window_ms,
        event_time_authority="trigger_candle_close_time_ms",
        entry_order_type=EntryOrderType.MARKET,
        protection_reference_fact=protection_reference_fact,
        pre_tp1_reclaim_reference_fact=pre_tp1_reclaim_reference_fact,
        exposure_session_end_reference_fact=(
            exposure_session_end_reference_fact
        ),
        required_facts=tuple(
            _fact(fact_name, role, freshness_window_ms, fact_version)
            for fact_name, role in facts
        ),
        disable_facts=tuple(
            _fact(fact_name, "disable", freshness_window_ms, fact_version)
            for fact_name in disable_fact_names
        ),
        exit_policy_id=(
            f"exit-policy:{strategy_group_id}:{event_id}:{exit_policy_variant}"
        ),
        status=status,
    )


def _fact(
    fact_name: str,
    role: FactRole,
    freshness_ms: int,
    fact_version: int,
) -> RegisteredFactRequirement:
    return RegisteredFactRequirement(
        fact_definition_id=f"fact:{fact_name}:v{fact_version}",
        fact_name=fact_name,
        value_type=(
            "boolean"
            if role in {"condition", "disable"}
            else "decimal"
        ),
        role=role,
        freshness_ms=freshness_ms,
    )
