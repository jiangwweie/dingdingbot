from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.ports import RuntimeScopeSnapshot
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
    produce_strategy_signal,
)
from src.trading_kernel.application.project_shadow_outcome import (
    pending_shadow_spec_for_rejection,
    pending_shadow_spec_for_strategy_observation,
)
from src.trading_kernel.domain.admission_decision import (
    AdmissionDecisionStatus,
    AdmissionPortfolioUsage,
    freeze_admission_decision,
)
from src.trading_kernel.domain.arbitration import EntryCandidate, freeze_candidate_set
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.shadow_outcome import (
    ShadowOutcomeProjection,
    ShadowOutcomeSpec,
    evaluate_fixed_horizon_excursion,
    evaluate_sor_path_observation,
)
from src.trading_kernel.domain.signal import build_signal_fact_digest
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from tests.trading_kernel.integration.test_signal_to_ticket import (
    _admission_snapshot,
)
from tests.trading_kernel.integration.test_signal_to_ticket import (
    _signal as _runtime_signal,
)
from tests.trading_kernel.support.us_equity_sor import (
    make_us_equity_sor_snapshot as _us_sor_snapshot,
)


def test_fixed_horizon_excursion_projects_long_mfe_and_mae_in_r() -> None:
    projection = evaluate_fixed_horizon_excursion(
        _spec(position_side="long", entry_reference_price=Decimal(100), initial_stop_price=Decimal(95)),
        (_candle(close_time_ms=2, high=Decimal(110), low=Decimal(97)),),
    )

    assert projection.evaluation_kind == "fixed_horizon_excursion_v1"
    assert projection.max_favorable_price == Decimal(110)
    assert projection.max_adverse_price == Decimal(97)
    assert projection.mfe_r == Decimal(2)
    assert projection.mae_r == Decimal("0.6")


def test_fixed_horizon_excursion_projects_short_mfe_and_mae_in_r() -> None:
    projection = evaluate_fixed_horizon_excursion(
        _spec(position_side="short", entry_reference_price=Decimal(100), initial_stop_price=Decimal(105)),
        (_candle(close_time_ms=2, high=Decimal(103), low=Decimal(90)),),
    )

    assert projection.evaluation_kind == "fixed_horizon_excursion_v1"
    assert projection.max_favorable_price == Decimal(90)
    assert projection.max_adverse_price == Decimal(103)
    assert projection.mfe_r == Decimal(2)
    assert projection.mae_r == Decimal("0.6")


def test_fixed_horizon_excursion_uses_only_closed_candles_inside_horizon() -> None:
    projection = evaluate_fixed_horizon_excursion(
        _spec(position_side="long", horizon_start_ms=2, horizon_end_ms=3),
        (
            _candle(close_time_ms=2, high=Decimal(140), low=Decimal(60)),
            _candle(close_time_ms=3, high=Decimal(110), low=Decimal(97)),
            _candle(close_time_ms=4, high=Decimal(130), low=Decimal(70)),
        ),
    )

    assert projection.max_favorable_price == Decimal(110)
    assert projection.max_adverse_price == Decimal(97)
    assert projection.observed_through_ms == 3


def test_fixed_horizon_excursion_reports_zero_for_unreached_adverse_move() -> None:
    projection = evaluate_fixed_horizon_excursion(
        _spec(position_side="long"),
        (
            _candle(
                close_time_ms=2,
                high=Decimal(110),
                low=Decimal(101),
                open_price=Decimal(101),
                close_price=Decimal(101),
            ),
        ),
    )

    assert projection.mfe_r == Decimal(2)
    assert projection.mae_r == Decimal(0)


def test_sor_path_observation_classifies_first_path() -> None:
    cases = (
        ((_candle(close_time_ms=2, high=Decimal(106), low=Decimal(99)),), "tp1_first"),
        ((_candle(close_time_ms=2, high=Decimal(104), low=Decimal(94)),), "initial_stop_first"),
        ((_candle(close_time_ms=2, high=Decimal(106), low=Decimal(94)),), "ambiguous_same_bar"),
        ((
            _candle(
                close_time_ms=2,
                high=Decimal(104),
                low=Decimal(98),
                close_price=Decimal(102),
            ),
        ), "opening_range_failure"),
    )

    for candles, expected_path in cases:
        projection = evaluate_sor_path_observation(
            _sor_spec(horizon_end_ms=2),
            candles,
        )

        assert projection.evaluation_kind == "sor_path_observation_v1"
        assert projection.first_path == expected_path
        assert projection.first_path_at_ms == 2
        assert projection.mfe_r is not None
        assert projection.mae_r is not None


def test_sor_path_observation_uses_time_stop_after_eight_closed_bars() -> None:
    spec = _sor_spec(
        opening_range_boundary_price=Decimal(90),
        horizon_start_ms=1,
        horizon_end_ms=9,
    )
    candles = tuple(
        _candle(
            close_time_ms=index,
            high=Decimal(104),
            low=Decimal(98),
            close_price=Decimal(101),
        )
        for index in range(2, 10)
    )

    projection = evaluate_sor_path_observation(spec, candles)

    assert projection.first_path == "time_stop"
    assert projection.first_path_at_ms == 9
    assert projection.observed_bar_count == 8


def test_sor_path_observation_counts_bars_until_the_first_path() -> None:
    spec = _sor_spec(
        opening_range_boundary_price=Decimal(90),
        horizon_start_ms=1,
        horizon_end_ms=9,
    )
    candles = tuple(
        _candle(
            close_time_ms=index,
            high=Decimal(106) if index == 4 else Decimal(104),
            low=Decimal(98),
            close_price=Decimal(101),
        )
        for index in range(2, 10)
    )

    projection = evaluate_sor_path_observation(spec, candles)

    assert projection.first_path == "tp1_first"
    assert projection.first_path_at_ms == 4
    assert projection.observed_bar_count == 3
    assert projection.observed_through_ms == 9


def test_shadow_projection_rejects_incomplete_completed_shape() -> None:
    with pytest.raises(ValidationError, match="projection values"):
        ShadowOutcomeProjection(
            evaluation_kind="fixed_horizon_excursion_v1",
            max_favorable_price=None,
            max_adverse_price=None,
            mfe_r=None,
            mae_r=None,
            observed_through_ms=None,
        )


def test_shadow_spec_preserves_zero_risk_for_explicit_unavailable_projection() -> None:
    spec = _spec(
        position_side="long",
        entry_reference_price=Decimal(100),
        initial_stop_price=Decimal(100),
    )

    assert spec.initial_risk_per_unit == Decimal(0)


@pytest.mark.parametrize(
    ("status", "first_blocker", "expected"),
    (
        (AdmissionDecisionStatus.ADMITTED, None, False),
        (AdmissionDecisionStatus.REJECTED, "observation_unavailable", False),
        (AdmissionDecisionStatus.REJECTED, "exposure_family_capacity_exhausted", True),
    ),
)
def test_pending_shadow_eligibility_is_limited_to_portfolio_rejections(
    status: AdmissionDecisionStatus,
    first_blocker: str | None,
    expected: bool,
) -> None:
    signal = _runtime_signal()
    snapshot = _admission_snapshot()
    decision = _decision_for_shadow(signal, snapshot)
    decision = decision.model_copy(
        update={"decision_status": status, "first_blocker": first_blocker}
    )

    shadow = pending_shadow_spec_for_rejection(
        decision=decision,
        signal=signal,
        admission_snapshot=snapshot,
    )

    assert (shadow is not None) is expected
    if shadow is not None:
        assert shadow.timeframe == "15m"
        assert shadow.horizon_end_ms == 86_401_000


def test_pending_shadow_keeps_zero_risk_for_explicit_unavailable_result() -> None:
    base_signal = _runtime_signal()
    facts = tuple(
        fact.model_copy(update={"value": "10000"})
        if fact.role == "protection_reference"
        else fact
        for fact in base_signal.facts
    )
    signal = base_signal.model_copy(
        update={"facts": facts, "fact_digest": build_signal_fact_digest(facts)}
    )
    snapshot = _admission_snapshot()
    decision = _decision_for_shadow(signal, snapshot)

    shadow = pending_shadow_spec_for_rejection(
        decision=decision,
        signal=signal,
        admission_snapshot=snapshot,
    )

    assert shadow is not None
    assert shadow.initial_risk_per_unit == Decimal(0)


def test_tradfi_signal_freezes_observation_without_admission_identity() -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "SOR-US-LONG-15M"
    )
    market = _us_sor_snapshot(side="long")
    detector = evaluate_strategy_snapshot(contract, market)
    signal = produce_strategy_signal(
        contract=contract,
        scope=RuntimeScopeSnapshot(
            runtime_scope_id="scope:sor-us:aapl:long",
            strategy_group_id=contract.strategy_group_id,
            strategy_version_id=contract.strategy_version_id,
            event_spec_id=contract.event_spec_id,
            runtime_profile_id="tradfi-equity-usdm-v1",
            owner_policy_id="policy-main",
            exchange_instrument_id=market.exchange_instrument_id,
            position_side="long",
            universe_version_id="universe:sor-us:long:v1",
            universe_semantic_digest="sha256:" + "a" * 64,
            lifecycle_state="active",
            observation_enabled=True,
            entry_enabled=True,
            scope_version=1,
            observation_generation=1,
        ),
        detector_result=detector,
        persisted_facts=detector.facts,
    )
    assert market.product_session is not None
    product = market.product_session.model_copy(
        update={
            "mark_price": Decimal("104.05"),
            "index_price": Decimal(104),
            "best_bid": Decimal("103.9"),
            "best_ask": Decimal(104),
            "best_bid_quantity": Decimal(20),
            "best_ask_quantity": Decimal(15),
        }
    )

    shadow = pending_shadow_spec_for_strategy_observation(
        signal=signal,
        product=product,
    )

    assert shadow is not None
    assert shadow.source_kind == "strategy_observation"
    assert shadow.admission_decision_id is None
    assert shadow.signal_event_id == signal.signal_event_id
    assert shadow.entry_reference_price == Decimal(104)
    assert shadow.take_profit_price is not None
    assert shadow.spread_bps is not None


def _spec(
    *,
    position_side: str,
    entry_reference_price: Decimal = Decimal(100),
    initial_stop_price: Decimal = Decimal(95),
    horizon_start_ms: int = 1,
    horizon_end_ms: int = 2,
) -> ShadowOutcomeSpec:
    return ShadowOutcomeSpec(
        shadow_outcome_id="shadow:test",
        signal_event_id="signal:test",
        admission_decision_id="admission:test",
        source_kind="portfolio_rejection",
        evaluation_kind="fixed_horizon_excursion_v1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side=position_side,
        timeframe="1h",
        entry_reference_price=entry_reference_price,
        initial_stop_price=initial_stop_price,
        horizon_start_ms=horizon_start_ms,
        horizon_end_ms=horizon_end_ms,
        created_at_ms=1,
    )


def _sor_spec(
    *,
    opening_range_boundary_price: Decimal = Decimal(103),
    horizon_start_ms: int = 1,
    horizon_end_ms: int = 2,
) -> ShadowOutcomeSpec:
    return ShadowOutcomeSpec(
        shadow_outcome_id="shadow:sor-test",
        signal_event_id="signal:sor-test",
        admission_decision_id=None,
        source_kind="strategy_observation",
        evaluation_kind="sor_path_observation_v1",
        exchange_instrument_id="binance-usdm:AAPLUSDT:perpetual",
        position_side="long",
        timeframe="15m",
        entry_reference_price=Decimal(100),
        initial_stop_price=Decimal(95),
        take_profit_price=Decimal(105),
        opening_range_boundary_price=opening_range_boundary_price,
        session_exit_deadline_ms=9,
        mark_price=Decimal("100.1"),
        index_price=Decimal(100),
        funding_rate=Decimal("0.0001"),
        best_bid_price=Decimal("99.9"),
        best_ask_price=Decimal(100),
        best_bid_quantity=Decimal(10),
        best_ask_quantity=Decimal(12),
        horizon_start_ms=horizon_start_ms,
        horizon_end_ms=horizon_end_ms,
        created_at_ms=1,
    )


def _decision_for_shadow(
    signal,
    snapshot: EntryAdmissionSnapshot,
):
    return freeze_admission_decision(
        signal=signal,
        candidate_set=freeze_candidate_set(
            (EntryCandidate(signal=signal, owner_policy_priority=1),)
        ),
        exposure_family="opening_range",
        runtime_profile_id="profile:test",
        owner_policy_id="policy:test",
        owner_policy_version=4,
        venue_id="binance-usdm",
        account_id="subaccount-main",
        portfolio_usage=AdmissionPortfolioUsage(
            active_ticket_count=1,
            active_family_ticket_count=1,
            gross_risk_at_stop=Decimal(1),
            directional_risk_at_stop=Decimal(1),
            current_reserved_margin=Decimal(1),
            remaining_ticket_slots=1,
            remaining_family_slots=1,
            remaining_gross_stop_risk=Decimal(1),
            remaining_directional_stop_risk=Decimal(1),
            remaining_initial_margin=Decimal(1),
        ),
        decision_status=AdmissionDecisionStatus.REJECTED,
        first_blocker="budget_exhausted",
        binding_constraint="budget_exhausted",
        capacity_claim_id=None,
        ticket_id=None,
        entry_admission_snapshot_digest=snapshot.digest(),
        decided_at_ms=1_002,
    )


def _candle(
    *,
    close_time_ms: int,
    high: Decimal,
    low: Decimal,
    open_price: Decimal = Decimal(100),
    close_price: Decimal = Decimal(100),
) -> ClosedCandle:
    return ClosedCandle(
        open_time_ms=close_time_ms - 1,
        close_time_ms=close_time_ms,
        open=open_price,
        high=high,
        low=low,
        close=close_price,
        volume=Decimal(1),
    )
