from __future__ import annotations

import pytest

from src.application.readmodels.canary_mutation_sentinel import (
    CANARY_SENTINEL_SPECS_V1,
    CanaryMutationSentinelProjection,
)


def _row(columns: tuple[str, ...], seed: str) -> dict[str, object]:
    return {name: f"{seed}:{name}" for name in columns}


def test_canary_sentinel_schema_contract_has_unique_explicit_columns():
    assert len(CANARY_SENTINEL_SPECS_V1) == 18
    for spec in CANARY_SENTINEL_SPECS_V1:
        assert spec.columns
        assert len(spec.columns) == len(set(spec.columns))
        assert spec.row_limit > 0


def test_canary_sentinel_digest_is_order_stable_and_semantic():
    spec = CANARY_SENTINEL_SPECS_V1[0]
    first = _row(spec.columns, "a")
    second = _row(spec.columns, "b")
    left = CanaryMutationSentinelProjection.freeze(
        canary_db_now_ms=1000,
        canary_window_floor_ms=0,
        slices={spec.slice_id: [second, first]},
    )
    right = CanaryMutationSentinelProjection.freeze(
        canary_db_now_ms=1000,
        canary_window_floor_ms=0,
        slices={spec.slice_id: [first, second]},
    )
    changed = dict(first)
    changed[spec.columns[-1]] = "changed"
    different = CanaryMutationSentinelProjection.freeze(
        canary_db_now_ms=1000,
        canary_window_floor_ms=0,
        slices={spec.slice_id: [changed, second]},
    )

    assert left.digest == right.digest
    assert left.digest != different.digest


def test_canary_sentinel_rejects_unknown_column_and_overflow():
    spec = CANARY_SENTINEL_SPECS_V1[0]
    row = _row(spec.columns, "a")
    with pytest.raises(ValueError, match="schema_mismatch"):
        CanaryMutationSentinelProjection.freeze(
            canary_db_now_ms=1000,
            canary_window_floor_ms=0,
            slices={spec.slice_id: [{**row, "unknown": 1}]},
        )
    with pytest.raises(ValueError, match="row_limit_exceeded"):
        CanaryMutationSentinelProjection.freeze(
            canary_db_now_ms=1000,
            canary_window_floor_ms=0,
            slices={
                spec.slice_id: [
                    _row(spec.columns, str(index))
                    for index in range(spec.row_limit + 1)
                ]
            },
        )
