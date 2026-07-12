from __future__ import annotations

import pytest

from src.application.readmodels.owner_projection import (
    ticket_bound_lifecycle_owner_feedback,
)


@pytest.mark.parametrize(
    ("status", "blockers", "expected_state", "label", "owner_required"),
    [
        ("position_protected", [], "processing", "处理中", False),
        (
            "protection_missing",
            ["open_position_without_valid_sl"],
            "processing",
            "自动恢复中",
            False,
        ),
        (
            "entry_unknown",
            ["exchange_submit_outcome_unknown"],
            "temporarily_unavailable",
            "暂不可用",
            False,
        ),
        (
            "runner_mutation_failed",
            ["runner_mutation_retry_limit_exhausted"],
            "needs_intervention",
            "需要介入",
            True,
        ),
        ("lifecycle_closed", [], "completed", "已完成", False),
        (
            "venue_new_state",
            ["unsupported_lifecycle_status:venue_new_state"],
            "temporarily_unavailable",
            "暂不可用",
            False,
        ),
    ],
)
def test_ticket_lifecycle_owner_feedback_uses_common_typed_decision(
    status,
    blockers,
    expected_state,
    label,
    owner_required,
):
    feedback = ticket_bound_lifecycle_owner_feedback(
        {
            "ticket_id": "ticket-1",
            "strategy_group_id": "SOR-001",
            "symbol": "AVAXUSDT",
            "side": "short",
            "status": status,
            "first_blocker": blockers[0] if blockers else None,
            "blockers": blockers,
        }
    )

    assert feedback["status"] == expected_state
    assert feedback["label"] == label
    assert feedback["ticket_id"] == "ticket-1"
    assert feedback["lifecycle_status"] == status
    assert feedback["owner_action_required"] is owner_required
    assert feedback["exchange_write_authorized"] is False
    assert feedback["non_authority_checkpoint"]


def test_recoverable_failure_stays_system_owned():
    feedback = ticket_bound_lifecycle_owner_feedback(
        {
            "ticket_id": "ticket-1",
            "status": "protection_missing",
            "blockers": ["open_position_without_valid_sl"],
        }
    )

    assert feedback["control_state"] == "recovery_required"
    assert feedback["status"] == "processing"
    assert feedback["owner_action_required"] is False
    assert feedback["non_authority_checkpoint"] == (
        "run_official_recovery_submit_sl_or_flatten"
    )
