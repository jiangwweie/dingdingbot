import hashlib
import zipfile
from pathlib import Path

import pytest

from scripts.trading_kernel.verify_generic_selection_numeric_parity import (
    Brf2NumericParityError,
    compare_brf2_top16_member_sets,
    read_verified_archive,
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


def test_raw_source_authenticates_prices_not_just_manifest(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "source.csv", "open_time,close\n1000,0.12345678901234567890123456789\n"
        )
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        read_verified_archive(path, digest)[0][1] == "0.12345678901234567890123456789"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("source.csv", "open_time,close\n1000,999\n")
    with pytest.raises(Brf2NumericParityError, match="raw source digest"):
        read_verified_archive(path, digest)
