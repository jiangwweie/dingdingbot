"""Certify one claimed Universe instrument from authenticated readonly facts."""

from __future__ import annotations

import asyncio
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import (
    InstrumentCertificationTarget,
    UnitOfWorkFactory,
)
from src.trading_kernel.application.project_owner_state import (
    derive_instrument_certification_monitor,
)
from src.trading_kernel.application.runtime_facts import InstrumentRulesFacts
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionOwnership,
    canonical_digest,
)
from src.trading_kernel.domain.instrument_certification import (
    InstrumentCertification,
    InstrumentCertificationFacts,
    classify_instrument_certification,
)


class InstrumentCertificationReadRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: InstrumentCertificationTarget
    ownership: AdmissionOwnership
    observed_at_ms: int
    valid_for_ms: int


class InstrumentCertificationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    facts: InstrumentCertificationFacts
    instrument_rules: InstrumentRulesFacts | None

    @model_validator(mode="after")
    def _validate_snapshot(self) -> InstrumentCertificationSnapshot:
        rules = self.instrument_rules
        facts = self.facts
        raw_rules = (
            facts.tick_size,
            facts.step_size,
            facts.min_qty,
            facts.min_notional,
        )
        if rules is None:
            if all(
                value is not None and value.is_finite() and value > 0
                for value in raw_rules
            ):
                raise ValueError(
                    "complete certification facts require typed instrument rules"
                )
            return self
        if (
            rules.exchange_instrument_id != facts.exchange_instrument_id
            or rules.observed_at_ms != facts.observed_at_ms
            or rules.price_tick != facts.tick_size
            or rules.quantity_step != facts.step_size
            or rules.min_quantity != facts.min_qty
            or rules.min_notional != facts.min_notional
        ):
            raise ValueError("certification snapshot facts and rules must agree")
        return self


class InstrumentCertificationSource(Protocol):
    async def read_instrument_certification(
        self,
        request: InstrumentCertificationReadRequest,
    ) -> InstrumentCertificationSnapshot: ...


class InstrumentCertificationTransientFailure(RuntimeError):
    """Explicitly retryable readonly Venue/network failure."""


class InstrumentCertificationSnapshotContradiction(RuntimeError):
    """Authenticated Venue quantity contradicts current Kernel ownership."""

    def __init__(
        self,
        reason: Literal[
            "owned_position_projection_missing",
            "projected_position_exceeds_venue",
            "projected_position_domain_unowned",
        ],
    ) -> None:
        super().__init__(reason)
        self.reason = reason


class CertifyUniverseInstrumentRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: InstrumentCertificationTarget
    now_ms: int
    timeout_seconds: float
    required_leverage: int
    required_margin_mode: Literal["cross"]
    valid_for_ms: int
    eligible_check_interval_ms: int
    owner_action_check_interval_ms: int
    transient_retry_interval_ms: int

    @field_validator(
        "now_ms",
        "required_leverage",
        "valid_for_ms",
        "eligible_check_interval_ms",
        "owner_action_check_interval_ms",
        "transient_retry_interval_ms",
    )
    @classmethod
    def _require_positive_integer(cls, value: int) -> int:
        if isinstance(value, bool) or value <= 0:
            raise ValueError("certification windows must be positive integers")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _require_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("certification timeout must be positive")
        return value


class CertifyUniverseInstrumentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    certification: InstrumentCertification
    next_check_at_ms: int


async def certify_universe_instrument(
    uow_factory: UnitOfWorkFactory,
    source: InstrumentCertificationSource,
    request: CertifyUniverseInstrumentRequest,
) -> CertifyUniverseInstrumentResult:
    """Read outside transactions, classify purely, then persist in one short UoW."""

    target = request.target
    async with uow_factory() as uow:
        ownership = await uow.entry_admission.read_admission_ownership(
            venue_id=target.venue_id,
            account_id=target.account_id,
            exchange_instrument_id=target.exchange_instrument_id,
        )

    snapshot: InstrumentCertificationSnapshot | None = None
    try:
        snapshot = await asyncio.wait_for(
            source.read_instrument_certification(
                InstrumentCertificationReadRequest(
                    target=target,
                    ownership=ownership,
                    observed_at_ms=request.now_ms,
                    valid_for_ms=request.valid_for_ms,
                )
            ),
            timeout=request.timeout_seconds,
        )
        if (
            snapshot.facts.runtime_profile_id != target.runtime_profile_id
            or snapshot.facts.exchange_instrument_id
            != target.exchange_instrument_id
            or snapshot.facts.observed_at_ms != request.now_ms
        ):
            raise ValueError("certification snapshot identity mismatch")
        certification = classify_instrument_certification(
            snapshot.facts,
            required_leverage=request.required_leverage,
            required_margin_mode=request.required_margin_mode,
            valid_for_ms=request.valid_for_ms,
        )
    except InstrumentCertificationSnapshotContradiction as exc:
        certification = InstrumentCertification(
            status="temporarily_unavailable",
            blocker_code=exc.reason,
            facts_digest=canonical_digest(
                {
                    "runtime_profile_id": target.runtime_profile_id,
                    "exchange_instrument_id": target.exchange_instrument_id,
                    "status": "temporarily_unavailable",
                    "blocker_code": exc.reason,
                    "observed_at_ms": request.now_ms,
                }
            ),
            observed_at_ms=request.now_ms,
            valid_until_ms=request.now_ms + request.transient_retry_interval_ms,
        )
        snapshot = None
    except (
        TimeoutError,
        ConnectionError,
        InstrumentCertificationTransientFailure,
    ):
        certification = InstrumentCertification(
            status="temporarily_unavailable",
            blocker_code="readonly_facts_unavailable",
            facts_digest=canonical_digest(
                {
                    "runtime_profile_id": target.runtime_profile_id,
                    "exchange_instrument_id": target.exchange_instrument_id,
                    "status": "temporarily_unavailable",
                    "observed_at_ms": request.now_ms,
                }
            ),
            observed_at_ms=request.now_ms,
            valid_until_ms=request.now_ms + request.transient_retry_interval_ms,
        )
        snapshot = None

    next_check_at_ms = request.now_ms + _check_interval_ms(
        certification=certification,
        request=request,
    )
    monitor = derive_instrument_certification_monitor(
        target=target,
        certification=certification,
        updated_at_ms=request.now_ms,
    )
    product_rules_digest = (
        None
        if snapshot is None or snapshot.instrument_rules is None
        else canonical_digest(snapshot.instrument_rules)
    )
    async with uow_factory() as uow:
        if snapshot is not None and snapshot.instrument_rules is not None:
            rules = snapshot.instrument_rules
            await uow.signals.upsert_instrument_rules(
                venue_id=target.venue_id,
                exchange_instrument_id=target.exchange_instrument_id,
                quantity_step=rules.quantity_step,
                price_tick=rules.price_tick,
                min_quantity=rules.min_quantity,
                min_notional=rules.min_notional,
                exchange_max_leverage=rules.exchange_max_leverage,
                maintenance_margin_brackets=rules.maintenance_margin_brackets,
                maintenance_margin_brackets_digest=(
                    rules.maintenance_margin_brackets_digest
                ),
                notional_coefficient=rules.notional_coefficient,
                notional_coefficient_certified=(
                    rules.notional_coefficient_certified
                ),
                observed_at_ms=rules.observed_at_ms,
                valid_until_ms=rules.valid_until_ms,
            )
        await uow.strategy_universes.save_instrument_certification(
            target=target,
            certification=certification,
            product_rules_digest=product_rules_digest,
            configured_leverage=(
                None if snapshot is None else snapshot.facts.configured_leverage
            ),
            margin_mode=None if snapshot is None else snapshot.facts.margin_mode,
            position_mode=None if snapshot is None else snapshot.facts.position_mode,
            next_check_at_ms=next_check_at_ms,
        )
        if monitor is not None and (
            certification.status == "owner_action_required"
            or await uow.monitors.get(monitor.monitor_key) is not None
        ):
            await uow.monitors.save_if_changed(monitor)
    return CertifyUniverseInstrumentResult(
        certification=certification,
        next_check_at_ms=next_check_at_ms,
    )


def _check_interval_ms(
    *,
    certification: InstrumentCertification,
    request: CertifyUniverseInstrumentRequest,
) -> int:
    if certification.status == "eligible":
        return request.eligible_check_interval_ms
    if certification.status == "owner_action_required":
        return request.owner_action_check_interval_ms
    return request.transient_retry_interval_ms
