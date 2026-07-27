"""Immutable candidate/reference membership independent from Event semantics."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


AssetClass = Literal["crypto", "us_equity"]


class UniverseMemberRole(StrEnum):
    CANDIDATE = "candidate"
    REFERENCE = "reference"


class UniverseLifecycle(StrEnum):
    DRAFT = "draft"
    INSTALLED = "installed"
    WARMING = "warming"
    ACTIVE = "active"
    RETIRING = "retiring"
    RETIRED = "retired"


class UniverseMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    venue_symbol: str
    role: UniverseMemberRole
    priority_rank: int

    @field_validator("exchange_instrument_id", "venue_symbol", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("universe member identity must be non-blank")
        return normalized

    @field_validator("priority_rank")
    @classmethod
    def _require_positive_rank(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("universe member priority must be positive")
        return value


class StrategyUniverseVersion(BaseModel):
    """One immutable membership generation for exactly one Event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    universe_version_id: str
    universe_version: int
    strategy_group_id: str
    event_spec_id: str
    event_id: str
    asset_class: AssetClass
    members: tuple[UniverseMember, ...]

    @field_validator(
        "universe_version_id",
        "strategy_group_id",
        "event_spec_id",
        "event_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("strategy universe identity must be non-blank")
        return normalized

    @field_validator("universe_version")
    @classmethod
    def _require_positive_version(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("strategy universe version must be positive")
        return value

    @model_validator(mode="after")
    def _validate_membership(self) -> "StrategyUniverseVersion":
        if not self.members:
            raise ValueError("strategy universe requires members")
        expected_identity = (
            f"universe:{self.event_spec_id}:v{self.universe_version}"
        )
        if self.universe_version_id != expected_identity:
            raise ValueError("strategy universe version identity is not canonical")
        instrument_ids = [item.exchange_instrument_id for item in self.members]
        venue_symbols = [item.venue_symbol for item in self.members]
        if len(instrument_ids) != len(set(instrument_ids)):
            raise ValueError("strategy universe instrument identities must be unique")
        if len(venue_symbols) != len(set(venue_symbols)):
            raise ValueError("strategy universe venue symbols must be unique")
        for role in UniverseMemberRole:
            ranks = [
                item.priority_rank
                for item in self.members
                if item.role is role
            ]
            if ranks and ranks != list(range(1, len(ranks) + 1)):
                raise ValueError(
                    "strategy universe role priorities must be contiguous from one"
                )
        if not self.candidate_members:
            raise ValueError("strategy universe requires candidate members")
        if self.asset_class == "crypto" and self.reference_members:
            raise ValueError("crypto strategy universes cannot contain references")
        return self

    @property
    def candidate_members(self) -> tuple[UniverseMember, ...]:
        return tuple(
            item for item in self.members if item.role is UniverseMemberRole.CANDIDATE
        )

    @property
    def reference_members(self) -> tuple[UniverseMember, ...]:
        return tuple(
            item for item in self.members if item.role is UniverseMemberRole.REFERENCE
        )

    @property
    def candidate_venue_symbols(self) -> tuple[str, ...]:
        return tuple(item.venue_symbol for item in self.candidate_members)

    @property
    def reference_venue_symbols(self) -> tuple[str, ...]:
        return tuple(item.venue_symbol for item in self.reference_members)

    def contains_candidate(self, exchange_instrument_id: str) -> bool:
        return any(
            item.exchange_instrument_id == exchange_instrument_id
            for item in self.candidate_members
        )

    def semantic_digest(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"sha256:{sha256(canonical).hexdigest()}"


class UniverseInstallCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    inserted_universe_version_count: int = 0
    inserted_member_count: int = 0
    inserted_instrument_count: int = 0
    inserted_candidate_scope_count: int = 0
    inserted_current_pointer_count: int = 0
    inserted_activation_count: int = 0

    @property
    def total_inserted_count(self) -> int:
        return sum(self.model_dump(mode="python").values())


class UniverseActivationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    activation_id: str
    event_spec_id: str
    old_universe_version_id: str | None
    new_universe_version_id: str
    activation_generation: int
    activated_scope_count: int
    activated_at_ms: int
    activation_digest: str

    @model_validator(mode="after")
    def _validate_activation(self) -> "UniverseActivationRecord":
        if (
            self.activation_generation <= 0
            or self.activated_scope_count <= 0
            or self.activated_at_ms <= 0
        ):
            raise ValueError("universe activation values must be positive")
        if not self.activation_digest.startswith("sha256:"):
            raise ValueError("universe activation digest must be versioned")
        return self


def registered_strategy_universes() -> tuple[StrategyUniverseVersion, ...]:
    """Return the exact Owner-approved initial membership generations."""

    return (
        _crypto_universe(
            strategy_group_id="CPM-RO-001",
            event_id="CPM-LONG",
            symbols=("ETHUSDT", "SOLUSDT", "SUIUSDT", "BNBUSDT", "LINKUSDT", "XRPUSDT"),
        ),
        _crypto_universe(
            strategy_group_id="MPG-001",
            event_id="MPG-LONG",
            symbols=("OPUSDT", "SOLUSDT", "SUIUSDT", "ADAUSDT", "AAVEUSDT", "NEARUSDT"),
        ),
        _crypto_universe(
            strategy_group_id="MI-001",
            event_id="MI-LONG",
            symbols=("ETHUSDT", "SOLUSDT", "DOGEUSDT", "SUIUSDT", "AAVEUSDT", "NEARUSDT"),
        ),
        _crypto_universe(
            strategy_group_id="SOR-001",
            event_id="SOR-LONG",
            symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"),
        ),
        _crypto_universe(
            strategy_group_id="SOR-001",
            event_id="SOR-SHORT",
            symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"),
        ),
        _crypto_universe(
            strategy_group_id="BRF2-001",
            event_id="BRF2-SHORT",
            symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LINKUSDT", "XRPUSDT"),
        ),
        _universe(
            strategy_group_id="RSRVCB-001",
            event_id="RSRVCB-LONG-15M",
            event_version=1,
            asset_class="us_equity",
            candidate_symbols=(
                "MSTRUSDT",
                "COINUSDT",
                "CRCLUSDT",
                "HOODUSDT",
                "PLTRUSDT",
                "MUUSDT",
                "SNDKUSDT",
                "TSLAUSDT",
                "NVDAUSDT",
                "METAUSDT",
                "GOOGLUSDT",
                "AVGOUSDT",
                "SOXLUSDT",
            ),
            reference_symbols=("QQQUSDT", "SPYUSDT"),
        ),
    )


def universe_for_event_spec(event_spec_id: str) -> StrategyUniverseVersion:
    matches = [
        universe
        for universe in registered_strategy_universes()
        if universe.event_spec_id == event_spec_id
    ]
    if len(matches) != 1:
        raise KeyError(f"unknown Event Spec universe: {event_spec_id}")
    return matches[0]


def all_registered_instruments() -> tuple[UniverseMember, ...]:
    by_id: dict[str, UniverseMember] = {}
    for universe in registered_strategy_universes():
        for member in universe.members:
            existing = by_id.get(member.exchange_instrument_id)
            if existing is not None and existing.venue_symbol != member.venue_symbol:
                raise ValueError("contradictory registered instrument mapping")
            by_id[member.exchange_instrument_id] = member
    return tuple(by_id[key] for key in sorted(by_id))


def _crypto_universe(
    *,
    strategy_group_id: str,
    event_id: str,
    symbols: tuple[str, ...],
) -> StrategyUniverseVersion:
    return _universe(
        strategy_group_id=strategy_group_id,
        event_id=event_id,
        event_version=2,
        asset_class="crypto",
        candidate_symbols=symbols,
    )


def _universe(
    *,
    strategy_group_id: str,
    event_id: str,
    event_version: int,
    asset_class: AssetClass,
    candidate_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...] = (),
) -> StrategyUniverseVersion:
    event_spec_id = (
        f"event_spec:{strategy_group_id}:{event_id}:v{event_version}"
    )
    members = tuple(
        UniverseMember(
            exchange_instrument_id=f"binance-usdm:{symbol}:perpetual",
            venue_symbol=symbol,
            role=UniverseMemberRole.CANDIDATE,
            priority_rank=rank,
        )
        for rank, symbol in enumerate(candidate_symbols, start=1)
    ) + tuple(
        UniverseMember(
            exchange_instrument_id=f"binance-usdm:{symbol}:perpetual",
            venue_symbol=symbol,
            role=UniverseMemberRole.REFERENCE,
            priority_rank=rank,
        )
        for rank, symbol in enumerate(reference_symbols, start=1)
    )
    return StrategyUniverseVersion(
        universe_version_id=f"universe:{event_spec_id}:v1",
        universe_version=1,
        strategy_group_id=strategy_group_id,
        event_spec_id=event_spec_id,
        event_id=event_id,
        asset_class=asset_class,
        members=members,
    )
