import pytest

from scripts.trading_kernel.verify_generic_selection_numeric_parity import (
    Brf2NumericParityError,
    compare_brf2_top16_member_sets,
)


def test_brf2_parity_accepts_exact_complete_top16_sets() -> None:
    expected = {
        1: tuple(f"instrument:{index:02}" for index in range(16)),
        2: tuple(f"instrument:{index:02}" for index in range(16)),
    }

    result = compare_brf2_top16_member_sets(
        expected_top16_by_cutoff=expected,
        actual_top16_by_cutoff=expected,
    )

    assert result.checked_cutoff_count == 2
    assert result.mismatch_count == 0
    assert result.status == "PASS"


def test_brf2_parity_rejects_one_rank_boundary_member_change() -> None:
    expected = {1: tuple(f"instrument:{index:02}" for index in range(16))}
    actual = {
        1: tuple(f"instrument:{index:02}" for index in range(15))
        + ("instrument:replacement",)
    }

    with pytest.raises(Brf2NumericParityError, match="Top16 mismatch"):
        compare_brf2_top16_member_sets(
            expected_top16_by_cutoff=expected,
            actual_top16_by_cutoff=actual,
        )


def test_brf2_parity_rejects_missing_or_extra_frozen_cutoff() -> None:
    expected = {1: tuple(f"instrument:{index:02}" for index in range(16))}

    with pytest.raises(Brf2NumericParityError, match="cutoff set"):
        compare_brf2_top16_member_sets(
            expected_top16_by_cutoff=expected,
            actual_top16_by_cutoff={},
        )
