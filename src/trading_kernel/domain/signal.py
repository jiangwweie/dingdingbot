"""Immutable strategy observation boundary without capital authority."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from hashlib import sha256
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator, model_validator


_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
FactRole = Literal["condition", "protection_reference", "disable"]


class SignalFactSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_definition_id: str
    role: FactRole
    value: JsonValue
    satisfied: bool
    observed_at_ms: int
    valid_until_ms: int
    projection_version: int

    @field_validator("fact_definition_id", mode="before")
    @classmethod
    def _require_fact_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("fact definition identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_fact_window(self) -> "SignalFactSnapshot":
        if (
            self.observed_at_ms <= 0
            or self.valid_until_ms <= self.observed_at_ms
            or self.projection_version <= 0
        ):
            raise ValueError("fact snapshot time and version must be positive")
        return self


def build_signal_fact_digest(facts: Sequence[SignalFactSnapshot]) -> str:
    ordered = sorted(facts, key=lambda fact: fact.fact_definition_id)
    identities = [fact.fact_definition_id for fact in ordered]
    if len(identities) != len(set(identities)):
        raise ValueError("fact digest input contains duplicate definitions")
    canonical = json.dumps(
        [fact.model_dump(mode="json") for fact in ordered],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


class StrategySignal(BaseModel):
    """One detected strategy Event; never a sizing or order instruction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_event_id: str
    runtime_scope_id: str
    runtime_scope_version: int
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    fact_digest: str
    universe_version_id: str | None = None
    universe_digest: str | None = None
    projection_run_id: str | None = None
    armed_structure_id: str | None = None
    session_code: str | None = None
    session_multiplier: Decimal | None = None
    product_policy_version_id: str | None = None
    occurred_at_ms: int
    observed_at_ms: int
    expires_at_ms: int
    facts: tuple[SignalFactSnapshot, ...]

    @field_validator(
        "signal_event_id",
        "runtime_scope_id",
        "strategy_group_id",
        "strategy_version_id",
        "event_spec_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_non_blank_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("signal identity values must be non-blank")
        return normalized

    @field_validator(
        "universe_version_id",
        "universe_digest",
        "projection_run_id",
        "armed_structure_id",
        "session_code",
        "product_policy_version_id",
        mode="before",
    )
    @classmethod
    def _normalize_optional_identity(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("optional signal identities must be non-blank")
        return normalized

    @field_validator("fact_digest", mode="before")
    @classmethod
    def _require_fact_digest(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if _SHA256_DIGEST.fullmatch(normalized) is None:
            raise ValueError("signal fact digest must be an exact sha256 identity")
        return normalized

    @field_validator("runtime_scope_version")
    @classmethod
    def _require_positive_scope_version(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("signal runtime scope version must be positive")
        return value

    @field_validator("facts")
    @classmethod
    def _normalize_fact_order(
        cls,
        values: tuple[SignalFactSnapshot, ...],
    ) -> tuple[SignalFactSnapshot, ...]:
        if not values:
            raise ValueError("strategy signal requires an immutable fact bundle")
        ordered = tuple(sorted(values, key=lambda item: item.fact_definition_id))
        identities = [item.fact_definition_id for item in ordered]
        if len(identities) != len(set(identities)):
            raise ValueError("strategy signal facts must be unique")
        references = [item for item in ordered if item.role == "protection_reference"]
        if len(references) != 1:
            raise ValueError("strategy signal requires one protection reference fact")
        if any(item.role == "disable" and item.satisfied for item in ordered):
            raise ValueError("disable facts must be unsatisfied for an eligible signal")
        if any(
            item.role != "disable" and not item.satisfied
            for item in ordered
        ):
            raise ValueError("condition and protection facts must be satisfied")
        return ordered

    @model_validator(mode="after")
    def _validate_time_and_facts(self) -> "StrategySignal":
        if (
            self.occurred_at_ms <= 0
            or self.observed_at_ms < self.occurred_at_ms
            or self.expires_at_ms <= self.observed_at_ms
        ):
            raise ValueError(
                "signal observation must follow occurrence and precede expiry"
            )
        if any(
            fact.observed_at_ms > self.occurred_at_ms
            or fact.valid_until_ms < self.expires_at_ms
            for fact in self.facts
        ):
            raise ValueError("signal facts must cover the complete occurrence window")
        if build_signal_fact_digest(self.facts) != self.fact_digest:
            raise ValueError("signal fact digest differs from the immutable fact bundle")
        if (self.universe_version_id is None) != (self.universe_digest is None):
            raise ValueError("signal Universe version and digest must be frozen together")
        if self.universe_digest is not None and (
            _SHA256_DIGEST.fullmatch(self.universe_digest) is None
        ):
            raise ValueError("signal Universe digest must be an exact sha256 identity")
        if (self.projection_run_id is None) != (self.armed_structure_id is None):
            raise ValueError("projection and armed lineage must be frozen together")
        if self.strategy_group_id == "RSRVCB-001" and (
            self.universe_version_id is None
            or self.projection_run_id is None
            or self.armed_structure_id is None
        ):
            raise ValueError("RSRVCB signal requires Universe/projection/armed lineage")
        if self.session_multiplier is not None and self.session_multiplier < 0:
            raise ValueError("signal session multiplier cannot be negative")
        return self
