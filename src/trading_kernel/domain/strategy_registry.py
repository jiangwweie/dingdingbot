"""Canonical contracts for the six Owner-accepted strategy Events."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.ticket import EntryOrderType


FactValueType = Literal["boolean", "decimal"]
FactRole = Literal["condition", "protection_reference", "disable"]
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
    inserted_instrument_count: int = 0
    inserted_candidate_scope_count: int = 0

    @property
    def total_inserted_count(self) -> int:
        return (
            self.inserted_strategy_group_count
            + self.inserted_strategy_version_count
            + self.inserted_event_count
            + self.inserted_exit_policy_count
            + self.inserted_fact_definition_count
            + self.inserted_event_fact_count
            + self.inserted_instrument_count
            + self.inserted_candidate_scope_count
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
    def _validate_role_value_type(self) -> "RegisteredFactRequirement":
        if self.role == "protection_reference" and self.value_type != "decimal":
            raise ValueError("protection reference facts must be decimal")
        if self.role in {"condition", "disable"} and self.value_type != "boolean":
            raise ValueError("condition and disable facts must be boolean")
        return self


class InstrumentPriority(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    venue_symbol: str
    priority_rank: int

    @field_validator("exchange_instrument_id", "venue_symbol", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("instrument priority identity must be non-blank")
        return normalized

    @field_validator("priority_rank")
    @classmethod
    def _require_positive_priority(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("instrument priority rank must be positive")
        return value


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
    required_facts: tuple[RegisteredFactRequirement, ...]
    disable_facts: tuple[RegisteredFactRequirement, ...] = ()
    candidate_instruments: tuple[InstrumentPriority, ...]
    exit_policy_id: str

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

    @field_validator("freshness_window_ms")
    @classmethod
    def _require_positive_freshness(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("strategy freshness window must be positive")
        return value

    @model_validator(mode="after")
    def _validate_contract(self) -> "RegisteredStrategyContract":
        expected_version = f"sgv:{self.strategy_group_id}:v2"
        expected_event = (
            f"event_spec:{self.strategy_group_id}:{self.event_id}:v2"
        )
        if self.strategy_version_id != expected_version:
            raise ValueError("strategy version identity must be the accepted v2 identity")
        if self.event_spec_id != expected_event:
            raise ValueError("event spec identity must be the accepted v2 identity")

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
        if any(
            item.freshness_ms != self.freshness_window_ms
            for item in (*self.required_facts, *self.disable_facts)
        ):
            raise ValueError("registered facts must use the Event freshness window")

        if not self.candidate_instruments:
            raise ValueError("registered Event requires candidate instruments")
        instrument_ids = [
            item.exchange_instrument_id for item in self.candidate_instruments
        ]
        venue_symbols = [item.venue_symbol for item in self.candidate_instruments]
        priorities = [item.priority_rank for item in self.candidate_instruments]
        if len(instrument_ids) != len(set(instrument_ids)):
            raise ValueError("candidate instrument identities must be unique")
        if len(venue_symbols) != len(set(venue_symbols)):
            raise ValueError("candidate venue symbols must be unique")
        if priorities != list(range(1, len(priorities) + 1)):
            raise ValueError("candidate priorities must be contiguous from one")
        return self

    @property
    def required_fact_names(self) -> tuple[str, ...]:
        return tuple(item.fact_name for item in self.required_facts)

    @property
    def disable_fact_names(self) -> tuple[str, ...]:
        return tuple(item.fact_name for item in self.disable_facts)

    @property
    def venue_symbols(self) -> tuple[str, ...]:
        return tuple(item.venue_symbol for item in self.candidate_instruments)


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
            venue_symbols=("ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
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
            venue_symbols=("OPUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
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
            venue_symbols=("AVAXUSDT", "ETHUSDT", "SOLUSDT"),
        ),
        _contract(
            strategy_group_id="SOR-001",
            event_id="SOR-LONG",
            position_side="long",
            timeframe="15m",
            facts=(
                ("opening_range_defined", "condition"),
                ("breakout_confirmed", "condition"),
                ("opening_range_low_reference", "protection_reference"),
            ),
            protection_reference_fact="opening_range_low_reference",
            venue_symbols=("ETHUSDT", "SOLUSDT", "AVAXUSDT", "BTCUSDT"),
        ),
        _contract(
            strategy_group_id="SOR-001",
            event_id="SOR-SHORT",
            position_side="short",
            timeframe="15m",
            facts=(
                ("opening_range_defined", "condition"),
                ("breakdown_confirmed", "condition"),
                ("opening_range_high_reference", "protection_reference"),
            ),
            protection_reference_fact="opening_range_high_reference",
            venue_symbols=("ETHUSDT", "SOLUSDT", "AVAXUSDT", "BTCUSDT"),
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
            venue_symbols=("BTCUSDT", "AVAXUSDT", "ETHUSDT"),
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


def _contract(
    *,
    strategy_group_id: str,
    event_id: str,
    position_side: PositionSide,
    timeframe: Timeframe,
    facts: tuple[tuple[str, Literal["condition", "protection_reference"]], ...],
    protection_reference_fact: str,
    venue_symbols: tuple[str, ...],
    disable_fact_names: tuple[str, ...] = (),
) -> RegisteredStrategyContract:
    freshness_window_ms = 900_000 if timeframe == "15m" else 3_600_000
    return RegisteredStrategyContract(
        strategy_group_id=strategy_group_id,
        strategy_version_id=f"sgv:{strategy_group_id}:v2",
        event_spec_id=f"event_spec:{strategy_group_id}:{event_id}:v2",
        event_id=event_id,
        position_side=position_side,
        timeframe=timeframe,
        freshness_window_ms=freshness_window_ms,
        event_time_authority="trigger_candle_close_time_ms",
        entry_order_type=EntryOrderType.MARKET,
        protection_reference_fact=protection_reference_fact,
        required_facts=tuple(
            _fact(fact_name, role, freshness_window_ms)
            for fact_name, role in facts
        ),
        disable_facts=tuple(
            _fact(fact_name, "disable", freshness_window_ms)
            for fact_name in disable_fact_names
        ),
        candidate_instruments=tuple(
            InstrumentPriority(
                exchange_instrument_id=f"binance-usdm:{venue_symbol}:perpetual",
                venue_symbol=venue_symbol,
                priority_rank=rank,
            )
            for rank, venue_symbol in enumerate(venue_symbols, start=1)
        ),
        exit_policy_id=(
            f"exit-policy:{strategy_group_id}:{event_id}:right-tail-v1"
        ),
    )


def _fact(
    fact_name: str,
    role: FactRole,
    freshness_ms: int,
) -> RegisteredFactRequirement:
    return RegisteredFactRequirement(
        fact_definition_id=f"fact:{fact_name}:v1",
        fact_name=fact_name,
        value_type="decimal" if role == "protection_reference" else "boolean",
        role=role,
        freshness_ms=freshness_ms,
    )
