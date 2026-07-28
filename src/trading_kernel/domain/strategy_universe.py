"""Versioned, unordered candidate eligibility for one Strategy Event."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)


MAX_UNIVERSE_MEMBERS = 10


class StrategyUniverseVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    universe_version_id: str
    strategy_group_id: str
    event_spec_id: str
    universe_version: int
    exchange_instrument_ids: tuple[str, ...]
    semantic_digest: str
    installed_at_ms: int

    @field_validator(
        "universe_version_id",
        "strategy_group_id",
        "event_spec_id",
        "semantic_digest",
        mode="before",
    )
    @classmethod
    def _require_nonblank_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("universe identity must be non-blank")
        return normalized

    @field_validator("universe_version", "installed_at_ms")
    @classmethod
    def _require_positive_number(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("universe version and installed time must be positive")
        return value

    @model_validator(mode="after")
    def _validate_members_and_digest(self) -> "StrategyUniverseVersion":
        members = self.exchange_instrument_ids
        if not 1 <= len(members) <= MAX_UNIVERSE_MEMBERS:
            raise ValueError("universe requires between one and ten members")
        if tuple(sorted(members)) != members:
            raise ValueError("universe members must be canonical sorted")
        if len(set(members)) != len(members):
            raise ValueError("universe members must be unique")
        for member in members:
            parse_binance_usdm_instrument_id(member)
        expected_digest = _semantic_digest(
            strategy_group_id=self.strategy_group_id,
            event_spec_id=self.event_spec_id,
            exchange_instrument_ids=members,
        )
        if self.semantic_digest != expected_digest:
            raise ValueError("universe semantic digest differs from canonical members")
        return self


def build_strategy_universe(
    *,
    universe_version_id: str,
    strategy_group_id: str,
    event_spec_id: str,
    universe_version: int,
    exchange_instrument_ids: Sequence[str],
    installed_at_ms: int,
) -> StrategyUniverseVersion:
    """Build one immutable Universe; submission order is deliberately discarded."""

    canonical_members = tuple(sorted(exchange_instrument_ids))
    for member in canonical_members:
        parse_binance_usdm_instrument_id(member)
    return StrategyUniverseVersion(
        universe_version_id=universe_version_id,
        strategy_group_id=strategy_group_id,
        event_spec_id=event_spec_id,
        universe_version=universe_version,
        exchange_instrument_ids=canonical_members,
        semantic_digest=_semantic_digest(
            strategy_group_id=strategy_group_id,
            event_spec_id=event_spec_id,
            exchange_instrument_ids=canonical_members,
        ),
        installed_at_ms=installed_at_ms,
    )


def _semantic_digest(
    *,
    strategy_group_id: str,
    event_spec_id: str,
    exchange_instrument_ids: tuple[str, ...],
) -> str:
    canonical = json.dumps(
        {
            "event_spec_id": event_spec_id,
            "exchange_instrument_ids": exchange_instrument_ids,
            "strategy_group_id": strategy_group_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"
