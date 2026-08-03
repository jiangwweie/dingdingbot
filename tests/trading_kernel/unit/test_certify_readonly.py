from __future__ import annotations

import pytest

from scripts.trading_kernel.certify_readonly import (
    _certification_batch_policy_stage_matches,
    _universe_manifest_matches,
)
from src.trading_kernel.domain.strategy_universe import build_strategy_universe


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
        (2, 3, True, True),
        (7, 8, True, True),
        (1, 2, False, False),
        (1, 3, True, False),
        (3, 2, True, False),
        (0, 1, True, False),
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


def test_portfolio_admission_universe_manifest_requires_canonical_digest() -> None:
    event_spec_id = "event_spec:CPM-RO-001:CPM-LONG:v3"
    members = (
        "binance-usdm:BTCUSDT:perpetual",
        "binance-usdm:ETHUSDT:perpetual",
    )
    canonical_digest = build_strategy_universe(
        universe_version_id="universe:test",
        strategy_group_id="CPM-RO-001",
        event_spec_id=event_spec_id,
        universe_version=1,
        exchange_instrument_ids=members,
        installed_at_ms=1,
    ).semantic_digest
    manifest = [
        {
            "event_spec_id": event_spec_id,
            "semantic_digest": canonical_digest,
            "member_ids": list(members),
        }
    ]

    assert _universe_manifest_matches(
        manifest,
        expected_event_specs=(("CPM-RO-001", event_spec_id),),
        expected_member_ids=members,
    )
    assert not _universe_manifest_matches(
        [
            {
                **manifest[0],
                "semantic_digest": "sha256:" + "0" * 64,
            }
        ],
        expected_event_specs=(("CPM-RO-001", event_spec_id),),
        expected_member_ids=members,
    )
