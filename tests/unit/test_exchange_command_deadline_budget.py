from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.exchange_command_deadline import (
    ExchangeCommandDeadlineBudget,
    decide_exchange_phase_budget,
)


@pytest.mark.parametrize("timeout_seconds", (float("nan"), float("inf"), float("-inf")))
def test_legacy_worker_timeout_cap_rejects_all_non_finite_values(timeout_seconds):
    from src.application.action_time.exchange_command_worker import (
        _validate_lease_timeout_budget,
    )

    with pytest.raises(ValueError, match="exchange_command_dispatch_timeout_invalid"):
        _validate_lease_timeout_budget(
            lease_ms=35_000,
            dispatch_timeout_seconds=timeout_seconds,
        )


def test_production_deadline_budget_defaults_reserve_initial_protection():
    budget = ExchangeCommandDeadlineBudget(absolute_deadline_at=110.0)

    assert budget.entry_network_timeout_seconds == 6.0
    assert budget.initial_stop_network_timeout_seconds == 6.0
    assert budget.tp1_network_timeout_seconds == 4.0
    assert budget.entry_result_commit_reserve_seconds == 1.0
    assert budget.initial_stop_result_commit_reserve_seconds == 1.0
    assert budget.shutdown_reserve_seconds == 1.0
    assert budget.pre_entry_reserve_seconds == 15.0


@pytest.mark.parametrize(
    ("remaining_seconds", "expected_blocker"),
    (
        (4.999, "exchange_command_deadline_budget_exhausted_before_io"),
        (5.0, "exchange_command_deadline_budget_exhausted_before_io"),
    ),
)
def test_phase_budget_rejects_unusable_commit_margin_boundary(
    remaining_seconds,
    expected_blocker,
):
    decision = decide_exchange_phase_budget(
        ExchangeCommandDeadlineBudget(absolute_deadline_at=110.0),
        role="SL",
        monotonic_now=110.0 - remaining_seconds,
        lease_ms=35_000,
        legacy_timeout_cap_seconds=10.0,
        require_pre_entry_reserve=False,
    )

    assert decision.allowed is False
    assert decision.blocker == expected_blocker
    assert decision.effective_timeout_seconds is None


def test_phase_budget_caps_timeout_to_deadline_remaining_after_margin():
    decision = decide_exchange_phase_budget(
        ExchangeCommandDeadlineBudget(absolute_deadline_at=110.0),
        role="SL",
        monotonic_now=104.0,
        lease_ms=6_000,
        legacy_timeout_cap_seconds=10.0,
        require_pre_entry_reserve=False,
    )

    assert decision.allowed is True
    assert decision.deadline_remaining_seconds == 6.0
    assert decision.effective_timeout_seconds == 1.0
    assert decision.required_lease_ms == 6_000


def test_pre_entry_reserve_blocks_below_threshold_and_accepts_exact_threshold():
    budget = ExchangeCommandDeadlineBudget(absolute_deadline_at=110.0)
    below = decide_exchange_phase_budget(
        budget,
        role="ENTRY",
        monotonic_now=95.001,
        lease_ms=35_000,
        legacy_timeout_cap_seconds=10.0,
        require_pre_entry_reserve=True,
    )
    exact = decide_exchange_phase_budget(
        budget,
        role="ENTRY",
        monotonic_now=95.0,
        lease_ms=35_000,
        legacy_timeout_cap_seconds=10.0,
        require_pre_entry_reserve=True,
    )

    assert below.allowed is False
    assert below.blocker == "protection_deadline_budget_insufficient_before_entry"
    assert exact.allowed is True
    assert exact.effective_timeout_seconds == 6.0


def test_lease_inequality_uses_effective_timeout_not_stale_configured_timeout():
    budget = ExchangeCommandDeadlineBudget(absolute_deadline_at=110.0)
    accepted = decide_exchange_phase_budget(
        budget,
        role="SL",
        monotonic_now=103.0,
        lease_ms=7_000,
        legacy_timeout_cap_seconds=10.0,
        require_pre_entry_reserve=False,
    )
    rejected = decide_exchange_phase_budget(
        budget,
        role="SL",
        monotonic_now=103.0,
        lease_ms=6_999,
        legacy_timeout_cap_seconds=10.0,
        require_pre_entry_reserve=False,
    )

    assert accepted.allowed is True
    assert accepted.effective_timeout_seconds == 2.0
    assert rejected.allowed is False
    assert rejected.blocker == "exchange_command_lease_timeout_budget_invalid"


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "field",
    [
        "absolute_deadline_at",
        "entry_network_timeout_seconds",
        "initial_stop_network_timeout_seconds",
        "tp1_network_timeout_seconds",
        "deadline_commit_margin_seconds",
        "entry_result_commit_reserve_seconds",
        "initial_stop_result_commit_reserve_seconds",
        "shutdown_reserve_seconds",
    ],
)
def test_deadline_budget_rejects_non_finite_typed_values(field, invalid):
    with pytest.raises(ValidationError):
        ExchangeCommandDeadlineBudget(**{"absolute_deadline_at": 110.0, field: invalid})


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_deadline_decision_rejects_non_finite_legacy_cap_and_clock(invalid):
    budget = ExchangeCommandDeadlineBudget(absolute_deadline_at=110.0)
    with pytest.raises(ValueError, match="dispatch_timeout_invalid"):
        decide_exchange_phase_budget(
            budget,
            role="SL",
            monotonic_now=100.0,
            lease_ms=35_000,
            legacy_timeout_cap_seconds=invalid,
            require_pre_entry_reserve=False,
        )
    with pytest.raises(ValueError, match="monotonic_now_invalid"):
        decide_exchange_phase_budget(
            budget,
            role="SL",
            monotonic_now=invalid,
            lease_ms=35_000,
            legacy_timeout_cap_seconds=10.0,
            require_pre_entry_reserve=False,
        )
