"""Create and project bounded read-only outcomes for rejected admission."""

from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.domain.admission_decision import (
    AdmissionDecision,
    AdmissionDecisionStatus,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.shadow_outcome import (
    ShadowOutcomeClaim,
    ShadowOutcomeSpec,
    ShadowOutcomeUnavailable,
    evaluate_fixed_horizon_excursion,
    has_complete_closed_candle_sequence,
)
from src.trading_kernel.domain.signal import StrategySignal
from src.trading_kernel.domain.strategy_registry import strategy_contract_for

_ELIGIBLE_REJECTION_BLOCKERS = frozenset(
    {
        "budget_exhausted",
        "exposure_family_capacity_exhausted",
        "directional_risk_exhausted",
        "active_netting_domain",
    }
)
_TIMEFRAME_MS = {"1h": 3_600_000, "15m": 900_000}


def pending_shadow_spec_for_rejection(
    *,
    decision: AdmissionDecision,
    signal: StrategySignal,
    admission_snapshot: EntryAdmissionSnapshot,
) -> ShadowOutcomeSpec | None:
    """Return immutable Shadow inputs only for a valid portfolio rejection."""

    if (
        decision.decision_status is not AdmissionDecisionStatus.REJECTED
        or decision.first_blocker not in _ELIGIBLE_REJECTION_BLOCKERS
        or decision.capacity_claim_id is not None
        or decision.ticket_id is not None
        or decision.signal_event_id != signal.signal_event_id
        or decision.entry_admission_snapshot_digest != admission_snapshot.digest()
    ):
        return None
    contract = strategy_contract_for(signal.event_spec_id)
    if (
        contract.timeframe not in _TIMEFRAME_MS
        or contract.position_side != signal.position_side
        or contract.event_spec_id != decision.event_spec_id
    ):
        return None
    entry_reference_price = (
        admission_snapshot.best_ask_price
        if signal.position_side == "long"
        else admission_snapshot.best_bid_price
    )
    stop_reference = _protection_reference(signal)
    if stop_reference is None or not _valid_stop_direction(
        position_side=signal.position_side,
        entry_reference_price=entry_reference_price,
        initial_stop_price=stop_reference,
    ):
        return None
    horizon_end_ms = _horizon_end_ms(signal, contract.shadow_horizon_bars)
    if horizon_end_ms is None:
        return None
    shadow_digest = canonical_digest(
        {
            "admission_decision_id": decision.admission_decision_id,
            "evaluation_kind": "fixed_horizon_excursion_v1",
        }
    )
    return ShadowOutcomeSpec(
        shadow_outcome_id=(
            f"shadow:{shadow_digest.removeprefix('sha256:')[:32]}"
        ),
        admission_decision_id=decision.admission_decision_id,
        exchange_instrument_id=signal.exchange_instrument_id,
        position_side=signal.position_side,
        timeframe=contract.timeframe,
        entry_reference_price=entry_reference_price,
        initial_stop_price=stop_reference,
        horizon_start_ms=signal.occurred_at_ms,
        horizon_end_ms=horizon_end_ms,
        created_at_ms=decision.decided_at_ms,
    )


async def project_claimed_shadow_outcome(
    uow_factory: UnitOfWorkFactory,
    claim: ShadowOutcomeClaim,
    candles: tuple[ClosedCandle, ...],
    *,
    completed_at_ms: int,
) -> bool:
    """Persist a terminal read-only projection after market I/O already ended."""

    if not has_complete_closed_candle_sequence(claim.spec, candles):
        async with uow_factory() as uow:
            await uow.shadow_outcomes.release_expired_claim(claim=claim)
        return False
    try:
        projection = evaluate_fixed_horizon_excursion(claim.spec, candles)
    except ShadowOutcomeUnavailable as exc:
        async with uow_factory() as uow:
            await uow.shadow_outcomes.mark_unavailable(
                claim=claim,
                reason=str(exc),
                completed_at_ms=completed_at_ms,
            )
        return True
    async with uow_factory() as uow:
        await uow.shadow_outcomes.complete(
            claim=claim,
            projection=projection,
            completed_at_ms=completed_at_ms,
        )
    return True


def _protection_reference(signal: StrategySignal) -> Decimal | None:
    references = [fact for fact in signal.facts if fact.role == "protection_reference"]
    if len(references) != 1:
        return None
    try:
        value = Decimal(str(references[0].value))
    except Exception:  # noqa: BLE001 - invalid frozen evidence is ineligible.
        return None
    return value if value.is_finite() and value > 0 else None


def _valid_stop_direction(
    *,
    position_side: str,
    entry_reference_price: Decimal,
    initial_stop_price: Decimal,
) -> bool:
    return (
        initial_stop_price <= entry_reference_price
        if position_side == "long"
        else initial_stop_price >= entry_reference_price
    )


def _horizon_end_ms(signal: StrategySignal, horizon_bars: int) -> int | None:
    contract = strategy_contract_for(signal.event_spec_id)
    maximum = signal.occurred_at_ms + (
        horizon_bars * _TIMEFRAME_MS[contract.timeframe]
    )
    if contract.timeframe != "15m":
        return maximum
    reference_name = contract.exposure_session_end_reference_fact
    if reference_name is None:
        return None
    expected_id = next(
        (
            item.fact_definition_id
            for item in contract.required_facts
            if item.fact_name == reference_name
        ),
        None,
    )
    session_fact = next(
        (
            fact for fact in signal.facts if fact.fact_definition_id == expected_id
        ),
        None,
    )
    if session_fact is None:
        return None
    try:
        session_end = Decimal(str(session_fact.value))
    except Exception:  # noqa: BLE001 - invalid frozen evidence is ineligible.
        return None
    if (
        not session_end.is_finite()
        or session_end != session_end.to_integral_value()
        or session_end <= signal.occurred_at_ms
        or session_end > maximum
    ):
        return None
    return int(session_end)
