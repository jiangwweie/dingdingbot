"""Pure detector contracts and exact routing for registered Events."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    field_validator,
    model_validator,
)

from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.signal import SignalFactSnapshot
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)


class DetectorStatus(StrEnum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    INVALID = "invalid"


class DetectorResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    status: DetectorStatus
    occurred_at_ms: int | None
    reason_code: str
    facts: tuple[SignalFactSnapshot, ...] = ()

    @field_validator("event_spec_id", "reason_code", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("detector result identity must be non-blank")
        return normalized

    @field_validator("facts")
    @classmethod
    def _order_unique_facts(
        cls,
        facts: tuple[SignalFactSnapshot, ...],
    ) -> tuple[SignalFactSnapshot, ...]:
        ordered = tuple(sorted(facts, key=lambda item: item.fact_definition_id))
        identities = [item.fact_definition_id for item in ordered]
        if len(identities) != len(set(identities)):
            raise ValueError("detector facts must be unique")
        return ordered

    @model_validator(mode="after")
    def _validate_status_shape(self) -> "DetectorResult":
        if self.status is DetectorStatus.TRIGGERED:
            if self.occurred_at_ms is None or self.occurred_at_ms <= 0:
                raise ValueError("triggered detector result requires occurrence time")
            if not self.facts:
                raise ValueError("triggered detector result requires facts")
        elif self.occurred_at_ms is not None:
            raise ValueError("non-triggered detector result forbids occurrence time")
        if self.status is DetectorStatus.INVALID and self.facts:
            raise ValueError("invalid detector result cannot claim computed facts")
        return self

    @property
    def triggered(self) -> bool:
        return self.status is DetectorStatus.TRIGGERED

    @property
    def facts_by_name(self) -> dict[str, SignalFactSnapshot]:
        return {_fact_name(item.fact_definition_id): item for item in self.facts}


class StrategyDetector(Protocol):
    event_spec_id: str

    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult: ...


def detector_for(event_spec_id: str) -> StrategyDetector:
    contracts = {
        item.event_spec_id: item for item in registered_strategy_contracts()
    }
    try:
        contract = contracts[event_spec_id]
    except KeyError as exc:
        raise KeyError(f"unknown Event Spec: {event_spec_id}") from exc

    from src.trading_kernel.domain.detectors.brf2 import BRF2ShortDetector
    from src.trading_kernel.domain.detectors.cpm import CPMLongDetector
    from src.trading_kernel.domain.detectors.mi import MILongDetector
    from src.trading_kernel.domain.detectors.mpg import MPGLongDetector
    from src.trading_kernel.domain.detectors.sor import SORDetector

    if contract.event_id == "CPM-LONG":
        return CPMLongDetector(contract)
    if contract.event_id == "MPG-LONG":
        return MPGLongDetector(contract)
    if contract.event_id == "MI-LONG":
        return MILongDetector(contract)
    if contract.event_id in {"SOR-LONG", "SOR-SHORT"}:
        return SORDetector(contract)
    if contract.event_id == "BRF2-SHORT":
        return BRF2ShortDetector(contract)
    raise KeyError(f"registered Event has no detector: {event_spec_id}")


def invalid_result(
    contract: RegisteredStrategyContract,
    reason_code: str,
) -> DetectorResult:
    return DetectorResult(
        event_spec_id=contract.event_spec_id,
        status=DetectorStatus.INVALID,
        occurred_at_ms=None,
        reason_code=reason_code,
    )


def computed_result(
    contract: RegisteredStrategyContract,
    snapshot: MarketSnapshot,
    *,
    triggered: bool,
    reason_code: str,
    facts: tuple[SignalFactSnapshot, ...],
) -> DetectorResult:
    if triggered:
        expected = {
            item.fact_definition_id
            for item in (*contract.required_facts, *contract.disable_facts)
        }
        actual = {item.fact_definition_id for item in facts}
        if actual != expected:
            raise ValueError("triggered detector facts differ from Registry contract")
    return DetectorResult(
        event_spec_id=contract.event_spec_id,
        status=(
            DetectorStatus.TRIGGERED
            if triggered
            else DetectorStatus.NOT_TRIGGERED
        ),
        occurred_at_ms=(
            snapshot.trigger_candle_close_time_ms if triggered else None
        ),
        reason_code=reason_code,
        facts=facts,
    )


def fact_snapshot(
    contract: RegisteredStrategyContract,
    snapshot: MarketSnapshot,
    *,
    fact_name: str,
    value: JsonValue,
    satisfied: bool,
    observed_at_ms: int | None = None,
    valid_until_ms: int | None = None,
) -> SignalFactSnapshot:
    requirement = next(
        (
            item
            for item in (*contract.required_facts, *contract.disable_facts)
            if item.fact_name == fact_name
        ),
        None,
    )
    if requirement is None:
        raise KeyError(f"unregistered detector fact: {fact_name}")
    observed = (
        snapshot.trigger_candle_close_time_ms
        if observed_at_ms is None
        else observed_at_ms
    )
    valid_until = (
        observed + requirement.freshness_ms
        if valid_until_ms is None
        else valid_until_ms
    )
    return SignalFactSnapshot(
        fact_definition_id=requirement.fact_definition_id,
        role=requirement.role,
        value=value,
        satisfied=satisfied,
        observed_at_ms=observed,
        valid_until_ms=valid_until,
        projection_version=1,
    )


def validate_snapshot_scope(
    contract: RegisteredStrategyContract,
    snapshot: MarketSnapshot,
) -> str | None:
    supported = {
        item.exchange_instrument_id for item in contract.candidate_instruments
    }
    if snapshot.exchange_instrument_id not in supported:
        return "detector_invalid_unsupported_instrument"
    primary = snapshot.candles(contract.timeframe)
    if primary and primary[-1].close_time_ms != snapshot.trigger_candle_close_time_ms:
        return "detector_invalid_trigger_time_mismatch"
    return None


def _fact_name(fact_definition_id: str) -> str:
    parts = fact_definition_id.split(":")
    if len(parts) >= 3 and parts[0] == "fact":
        return ":".join(parts[1:-1])
    return fact_definition_id
