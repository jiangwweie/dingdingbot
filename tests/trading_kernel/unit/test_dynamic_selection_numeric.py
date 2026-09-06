from decimal import Decimal

import pytest

from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)


def test_cpm_absolute_directional_efficiency_preserves_up_and_down_paths() -> None:
    from src.trading_kernel.domain.dynamic_selection_numeric import (
        absolute_directional_efficiency_24h,
    )

    assert absolute_directional_efficiency_24h(
        tuple(Decimal(100 + index) for index in range(25))
    ) == Decimal(1)
    assert absolute_directional_efficiency_24h(
        tuple(Decimal(124 - index) for index in range(25))
    ) == Decimal(1)


def test_mpg_persistent_leadership_uses_all_six_rank_boundaries() -> None:
    from src.trading_kernel.domain.dynamic_selection_numeric import (
        persistent_leadership_score_6h,
    )

    ranks = (3, 2, 4, 2, 3, 1)
    expected = sum(Decimal(25 - rank) / Decimal(24) for rank in ranks) / Decimal(6)

    assert persistent_leadership_score_6h(ranks) == expected
    assert persistent_leadership_score_6h((1, 1, 1, 1, 1, 1)) == Decimal(1)


def test_mi_positive_impulse_recency_uses_zero_for_no_positive_return() -> None:
    from src.trading_kernel.domain.dynamic_selection_numeric import (
        positive_impulse_recency_12h,
    )

    assert positive_impulse_recency_12h((Decimal("-0.01"),) * 12) == Decimal(0)
    assert positive_impulse_recency_12h(
        tuple(Decimal(index) / Decimal(10_000) for index in range(12))
    ) > Decimal("0.5")


def test_feature_rank_is_descending_and_uses_canonical_instrument_tie_break() -> None:
    from src.trading_kernel.domain.dynamic_selection_numeric import (
        rank_dynamic_selection_features,
    )

    values = {
        instrument_id: Decimal(0)
        for instrument_id in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
    }
    first, second = CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[:2]
    values[first] = Decimal(2)
    values[second] = Decimal(2)

    ranked = rank_dynamic_selection_features(values)

    assert tuple(item.exchange_instrument_id for item in ranked[:2]) == (
        first,
        second,
    )
    assert tuple(item.rank for item in ranked) == tuple(range(1, 25))


def test_brf2_decimal_residual_extension_ranks_candidate_specific_recent_extension() -> None:
    from src.trading_kernel.domain.dynamic_selection_numeric import (
        rank_brf2_residual_extension_v0_decimal,
    )

    closes_by_instrument: dict[str, tuple[Decimal, ...]] = {}
    for member_index, instrument_id in enumerate(
        CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
    ):
        close = Decimal(100 + member_index)
        closes = [close]
        for hour in range(72):
            base_return = Decimal("0.001") if hour % 2 == 0 else Decimal("-0.0004")
            idiosyncratic = Decimal(member_index % 5 - 2) / Decimal(100_000)
            if member_index == 0 and hour >= 48:
                idiosyncratic += Decimal("0.003")
            close *= Decimal(1) + base_return + idiosyncratic
            closes.append(close)
        closes_by_instrument[instrument_id] = tuple(closes)

    ranked = rank_brf2_residual_extension_v0_decimal(closes_by_instrument)

    assert ranked[0].exchange_instrument_id == (
        CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[0]
    )
    assert ranked[0].feature_value > ranked[-1].feature_value


def test_brf2_decimal_requires_exact_candidate_panel() -> None:
    from src.trading_kernel.domain.dynamic_selection_numeric import (
        DynamicSelectionNumericError,
        rank_brf2_residual_extension_v0_decimal,
    )

    with pytest.raises(DynamicSelectionNumericError, match="exact 24"):
        rank_brf2_residual_extension_v0_decimal(
            {
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[0]: (
                    Decimal(100),
                )
                * 73
            }
        )
