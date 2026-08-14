from __future__ import annotations

import pytest

from src.trading_kernel.domain.detector import DetectorStatus, detector_for
from tests.trading_kernel.support.us_equity_sor import (
    BAR_MS,
    REGULAR_CLOSE_MS,
    REGULAR_OPEN_MS,
)
from tests.trading_kernel.support.us_equity_sor import (
    make_us_equity_sor_snapshot as _snapshot,
)


@pytest.mark.parametrize(
    ("side", "event_id", "protection_fact"),
    [
        ("long", "SOR-US-LONG-15M", "initial_stop_reference_us_v1"),
        ("short", "SOR-US-SHORT-15M", "initial_stop_reference_us_v1"),
    ],
)
def test_us_equity_sor_triggers_inside_regular_session(
    side: str,
    event_id: str,
    protection_fact: str,
) -> None:
    result = detector_for(
        f"event_spec:SOR-US-EQ-PERP-001:{event_id}:v1"
    ).evaluate(_snapshot(side=side))

    assert result.status is DetectorStatus.TRIGGERED
    assert result.facts_by_name[protection_fact].role == "protection_reference"
    assert result.facts_by_name["regular_session_open_ms_us_v1"].role == "identity_reference"
    assert result.facts_by_name["session_exit_deadline_ms_us_v1"].value == str(
        REGULAR_CLOSE_MS - BAR_MS
    )


@pytest.mark.parametrize(
    ("session_state", "valid_until_ms", "wide_stop", "expected"),
    [
        ("pre_market", None, False, DetectorStatus.NOT_TRIGGERED),
        ("regular", REGULAR_OPEN_MS + 3 * BAR_MS, False, DetectorStatus.INVALID),
        ("regular", None, True, DetectorStatus.NOT_TRIGGERED),
    ],
)
def test_us_equity_sor_blocks_nonregular_stale_or_overwide_stop(
    session_state: str,
    valid_until_ms: int | None,
    wide_stop: bool,
    expected: DetectorStatus,
) -> None:
    result = detector_for(
        "event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1"
    ).evaluate(
        _snapshot(
            side="long",
            session_state=session_state,
            valid_until_ms=valid_until_ms,
            wide_stop=wide_stop,
        )
    )

    assert result.status is expected
