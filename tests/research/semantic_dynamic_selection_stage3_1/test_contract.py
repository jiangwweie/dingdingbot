from decimal import Decimal

from research.semantic_dynamic_selection.features import (
    positive_impulse_recency_12h,
    residual_extension_z_24h,
)
from research.semantic_dynamic_selection_stage3_1.core import (
    CARDINALITIES,
    absolute_directional_efficiency_24h,
    cohort_for_rank,
    persistent_leadership_score_6h,
)
from research.semantic_dynamic_selection_stage3_1.run_stage3_1 import (
    BASELINE_RELATIVE_PATH,
)


def test_cpm_v1_uses_absolute_not_signed_directional_efficiency() -> None:
    up = tuple(Decimal(100 + index) for index in range(25))
    down = tuple(Decimal(124 - index) for index in range(25))

    assert absolute_directional_efficiency_24h(up) == Decimal(1)
    assert absolute_directional_efficiency_24h(down) == Decimal(1)


def test_mpg_v1_is_continuous_mean_rank_strength() -> None:
    ranks = (3, 2, 4, 2, 3, 1)
    expected = sum(Decimal(25 - rank) / Decimal(24) for rank in ranks) / Decimal(6)

    assert persistent_leadership_score_6h(ranks) == expected
    assert persistent_leadership_score_6h((1, 1, 1, 1, 1, 1)) == Decimal(1)


def test_only_frozen_cardinalities_and_full_excluded_cohort_exist() -> None:
    assert CARDINALITIES == (16, 12, 8)
    assert cohort_for_rank(12, 12) == "SELECTED"
    assert cohort_for_rank(13, 12) == "EXCLUDED"


def test_mi_and_brf2_stage3_features_are_reused_unchanged() -> None:
    returns = tuple(Decimal(index) / Decimal(10_000) for index in range(12))
    assert positive_impulse_recency_12h(returns) >= 0

    market = tuple(0.001 if index % 2 == 0 else 0.002 for index in range(72))
    candidate = tuple(
        market[index] + (0.003 if index >= 48 else -0.001)
        for index in range(72)
    )
    assert residual_extension_z_24h(candidate, market) > 0


def test_stage3_1_reclassifies_the_original_stage2_all24_events() -> None:
    assert BASELINE_RELATIVE_PATH == (
        "research/multi_strategy_selection/artifacts/replayed_events.parquet"
    )
