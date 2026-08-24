from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.instrument_selection import (
    SelectionMemberReason,
    SelectionMemberState,
    SorDynamicSelectionSpecV0,
    build_selection_member_decision,
    build_sor_dynamic_selection_period,
    build_sor_dynamic_selection_spec_v0,
)

SESSION_START_MS = 1_704_067_200_000


def test_sor_selection_period_separates_session_and_decision_boundaries() -> None:
    period = build_sor_dynamic_selection_period(session_start_ms=SESSION_START_MS)

    assert period.session_start_ms == SESSION_START_MS
    assert period.decision_boundary_ms == SESSION_START_MS + 60 * 60 * 1000
    assert period.feature_cutoff_at_ms == period.decision_boundary_ms
    assert period.eligibility_not_before_ms == SESSION_START_MS + 75 * 60 * 1000
    assert period.expires_at_ms == SESSION_START_MS + 25 * 60 * 60 * 1000


def test_sor_selection_period_rejects_non_midnight_session_identity() -> None:
    with pytest.raises(ValueError, match="00:00 UTC"):
        build_sor_dynamic_selection_period(
            session_start_ms=SESSION_START_MS + 15 * 60 * 1000
        )


def test_selection_spec_freezes_decimal_contract_and_canonical_digest() -> None:
    first = _selection_spec(tuple(reversed(_candidate_ids())))
    second = _selection_spec(_candidate_ids())

    assert first.candidate_exchange_instrument_ids == _candidate_ids()
    assert first.algorithm_semantic_digest == second.algorithm_semantic_digest
    assert (
        first.algorithm_semantic_digest
        == "sha256:a2c0d5d809a54b90564086f4eab230726a16fdb5524a1ce8f29f48ad659cfb10"
    )
    assert first.activity_floor_quote_usdt == Decimal(20_000_000)
    assert first.decimal_precision == 38
    assert first.decimal_rounding == "ROUND_HALF_EVEN"
    with pytest.raises(ValidationError):
        SorDynamicSelectionSpecV0.model_validate(
            {**first.model_dump(), "score_weights": {"or_atr": 1}}
        )


def test_selection_spec_rejects_candidate_or_event_cardinality_drift() -> None:
    with pytest.raises(ValueError, match="24 canonical candidates"):
        _selection_spec(_candidate_ids()[:-1])
    with pytest.raises(ValueError, match="LONG and SHORT EventSpecs"):
        build_sor_dynamic_selection_spec_v0(
            selection_spec_id="sor-dynamic-selection-v0",
            strategy_group_id="SOR-001",
            strategy_version_id="sgv:SOR-001:v4",
            event_spec_ids=("event_spec:SOR-001:SOR-LONG:v4",),
            candidate_exchange_instrument_ids=_candidate_ids(),
            installed_at_ms=SESSION_START_MS,
        )


def test_member_decision_enforces_decimal_rank_state_and_reason_contract() -> None:
    selected = build_selection_member_decision(
        selection_snapshot_id="selection:sor-dynamic-selection-v0:1704067200000",
        selection_spec_id="sor-dynamic-selection-v0",
        session_start_ms=SESSION_START_MS,
        feature_cutoff_at_ms=SESSION_START_MS + 60 * 60 * 1000,
        input_window_start_ms=SESSION_START_MS - 23 * 60 * 60 * 1000,
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        input_window_digest="sha256:" + "1" * 64,
        or_high=Decimal("43000.1"),
        or_low=Decimal("42000.1"),
        pre_or_atr14=Decimal(500),
        trailing_24h_quote_volume=Decimal(100_000_000),
        stable_rank=1,
        member_state=SelectionMemberState.SELECTED,
        primary_reason=None,
    )

    assert selected.pre_or_width_atr14 == Decimal(2)
    assert selected.selected is True
    assert selected.member_semantic_digest.startswith("sha256:")

    with pytest.raises(ValueError, match="selected member requires rank 1 through 7"):
        build_selection_member_decision(
            **{
                **selected.model_dump(
                    exclude={
                        "or_width",
                        "pre_or_width_atr14",
                        "member_decision_id",
                        "input_window_end_ms",
                        "source_status",
                        "or_geometry_valid",
                        "atr_valid",
                        "activity_valid",
                        "selection_ready",
                        "secondary_reasons",
                        "selected",
                        "member_semantic_digest",
                    }
                ),
                "stable_rank": 8,
            }
        )

    with pytest.raises(ValueError, match="ineligible member requires one reason"):
        build_selection_member_decision(
            **{
                **selected.model_dump(
                    exclude={
                        "or_width",
                        "pre_or_width_atr14",
                        "member_decision_id",
                        "input_window_end_ms",
                        "source_status",
                        "or_geometry_valid",
                        "atr_valid",
                        "activity_valid",
                        "selection_ready",
                        "secondary_reasons",
                        "selected",
                        "member_semantic_digest",
                    }
                ),
                "stable_rank": None,
                "member_state": SelectionMemberState.INELIGIBLE,
                "primary_reason": None,
            }
        )

    low_activity = build_selection_member_decision(
        **{
            **selected.model_dump(
                exclude={
                    "or_width",
                    "pre_or_width_atr14",
                    "member_decision_id",
                    "input_window_end_ms",
                    "source_status",
                    "or_geometry_valid",
                    "atr_valid",
                    "activity_valid",
                    "selection_ready",
                    "secondary_reasons",
                    "selected",
                    "member_semantic_digest",
                }
            ),
            "trailing_24h_quote_volume": Decimal("19999999.99999999"),
            "stable_rank": None,
            "member_state": SelectionMemberState.INELIGIBLE,
            "primary_reason": SelectionMemberReason.LOW_ACTIVITY,
        }
    )
    assert low_activity.selection_ready is False
    assert low_activity.selected is False

    with pytest.raises(TypeError, match="cannot enter through float"):
        build_selection_member_decision(
            **{
                **selected.model_dump(
                    exclude={
                        "or_width",
                        "pre_or_width_atr14",
                        "member_decision_id",
                        "input_window_end_ms",
                        "source_status",
                        "or_geometry_valid",
                        "atr_valid",
                        "activity_valid",
                        "selection_ready",
                        "secondary_reasons",
                        "selected",
                        "member_semantic_digest",
                    }
                ),
                "or_high": 43000.1,
            }
        )


def _selection_spec(
    candidates: tuple[str, ...],
) -> SorDynamicSelectionSpecV0:
    return build_sor_dynamic_selection_spec_v0(
        selection_spec_id="sor-dynamic-selection-v0",
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v4",
        event_spec_ids=(
            "event_spec:SOR-001:SOR-SHORT:v4",
            "event_spec:SOR-001:SOR-LONG:v4",
        ),
        candidate_exchange_instrument_ids=candidates,
        installed_at_ms=SESSION_START_MS,
    )


def _candidate_ids() -> tuple[str, ...]:
    symbols = (
        "ADAUSDT",
        "APTUSDT",
        "ARBUSDT",
        "ATOMUSDT",
        "AVAXUSDT",
        "BCHUSDT",
        "BNBUSDT",
        "BTCUSDT",
        "DOGEUSDT",
        "DOTUSDT",
        "ETCUSDT",
        "ETHUSDT",
        "FILUSDT",
        "INJUSDT",
        "LINKUSDT",
        "LTCUSDT",
        "NEARUSDT",
        "OPUSDT",
        "RUNEUSDT",
        "SOLUSDT",
        "SUIUSDT",
        "TRXUSDT",
        "UNIUSDT",
        "XRPUSDT",
    )
    return tuple(f"binance-usdm:{symbol}:perpetual" for symbol in symbols)
