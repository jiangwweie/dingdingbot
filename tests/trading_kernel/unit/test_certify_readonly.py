from __future__ import annotations

import pytest

from scripts.trading_kernel.certify_readonly import (
    _certification_batch_policy_stage_matches,
)


@pytest.mark.parametrize(
    (
        "batch_policy_version",
        "current_policy_version",
        "new_entry_submit_enabled",
        "expected",
    ),
    (
        (1, 1, False, True),
        (1, 2, True, True),
        (2, 2, True, True),
        (1, 2, False, False),
        (1, 3, True, False),
        (2, 3, True, False),
    ),
)
def test_certification_batch_accepts_only_its_exact_policy_or_direct_arm_successor(
    batch_policy_version: int,
    current_policy_version: int,
    new_entry_submit_enabled: bool,
    expected: bool,
) -> None:
    assert (
        _certification_batch_policy_stage_matches(
            batch_policy_version=batch_policy_version,
            current_policy_version=current_policy_version,
            new_entry_submit_enabled=new_entry_submit_enabled,
        )
        is expected
    )
