from decimal import Decimal

from research.semantic_dynamic_selection.features import (
    active_selection_cutoff,
    leader_occupancy_6h,
    positive_impulse_recency_12h,
    rank_feature_values,
    residual_extension_z_24h,
    signed_trend_efficiency_24h,
)

HOUR_MS = 3_600_000


def test_cpm_signed_efficiency_distinguishes_clean_direction() -> None:
    clean = tuple(Decimal(100 + index) for index in range(25))
    noisy = tuple(
        Decimal(value)
        for value in (
            100, 105, 99, 106, 101, 107, 102, 108, 103, 109, 104, 110, 105,
            111, 106, 112, 107, 113, 108, 114, 109, 115, 110, 116, 112,
        )
    )

    assert signed_trend_efficiency_24h(clean) == Decimal(1)
    assert Decimal(0) < signed_trend_efficiency_24h(noisy) < Decimal(1)


def test_mpg_leader_occupancy_uses_six_fixed_rank_observations() -> None:
    assert leader_occupancy_6h((3, 2, 4, 2, 3, 1)) == Decimal(1)
    assert leader_occupancy_6h((18, 16, 20, 12, 9, 1)) == Decimal(1) / Decimal(6)


def test_mi_positive_impulse_recency_weights_recent_positive_returns() -> None:
    old = tuple([Decimal("0.02"), Decimal("0.01")] + [Decimal(0)] * 10)
    fresh = tuple([Decimal(0)] * 10 + [Decimal("0.01"), Decimal("0.02")])

    assert positive_impulse_recency_12h(fresh) > positive_impulse_recency_12h(old)
    assert positive_impulse_recency_12h((Decimal(0),) * 12) == Decimal(0)


def test_brf2_residual_extension_prefers_idiosyncratic_positive_move() -> None:
    market = tuple(0.001 if index % 2 == 0 else 0.002 for index in range(72))
    candidate = tuple(
        market[index] + (0.003 if index >= 48 else -0.001)
        for index in range(72)
    )

    assert residual_extension_z_24h(candidate, market) > 0


def test_rank_feature_values_uses_only_value_then_canonical_instrument_id() -> None:
    values = {
        f"binance-usdm:S{index:02d}:perpetual": Decimal(1)
        for index in range(24)
    }

    decisions = rank_feature_values(values)

    assert decisions[0].rank == 1
    assert decisions[0].exchange_instrument_id == "binance-usdm:S00:perpetual"
    assert decisions[15].state == "SELECTED"
    assert decisions[16].state == "NEAR_THRESHOLD"
    assert decisions[20].state == "NOT_SELECTED"


def test_selection_snapshot_becomes_effective_only_at_next_hour() -> None:
    event_at_13 = 13 * HOUR_MS

    assert active_selection_cutoff(event_at_13, cadence_hours=1) == 12 * HOUR_MS
    assert active_selection_cutoff(event_at_13, cadence_hours=4) == 12 * HOUR_MS
    assert active_selection_cutoff(12 * HOUR_MS, cadence_hours=4) == 8 * HOUR_MS
