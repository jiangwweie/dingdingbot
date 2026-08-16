from __future__ import annotations

from src.trading_kernel.application.owner_console.entry_scope import (
    build_effective_entry_scope,
)
from src.trading_kernel.application.owner_console.models import (
    EffectiveEntryScopeFacts,
    EntryScopeFacts,
)

NOW_MS = 1_800_000_000_000


def _scope(**overrides: object) -> EntryScopeFacts:
    values: dict[str, object] = {
        "runtime_scope_id": "scope:1",
        "strategy_group_id": "SOR-US-EQ-PERP-001",
        "strategy_version_id": "strategy-version:1",
        "event_spec_id": "event-spec:1",
        "timeframe": "15m",
        "exchange_instrument_id": "binance-usdm:AAPLUSDT",
        "position_side": "long",
        "lifecycle_state": "active",
        "entry_enabled": True,
        "strategy_entry_state": "enabled",
        "runtime_profile_status": "active",
        "readiness_state": "candidate_ready",
        "readiness_first_blocker": None,
        "product_profile_status": "active",
        "entry_session_policy": "regular_only",
        "product_status": "active",
        "session_state": "regular",
        "product_valid_until_ms": NOW_MS + 60_000,
        "scope_updated_at_ms": NOW_MS - 1_000,
        "readiness_updated_at_ms": NOW_MS - 500,
        "product_observed_at_ms": NOW_MS - 200,
    }
    values.update(overrides)
    return EntryScopeFacts.model_validate(values)


def _facts(**overrides: object) -> EffectiveEntryScopeFacts:
    values: dict[str, object] = {
        "owner_policy_id": "policy-main",
        "policy_version": 12,
        "policy_enabled": True,
        "new_entry_submit_enabled": True,
        "runtime_capability_enabled": True,
        "max_concurrent_tickets": 3,
        "active_ticket_count": 1,
        "scopes": (_scope(),),
    }
    values.update(overrides)
    return EffectiveEntryScopeFacts.model_validate(values)


def test_effective_entry_scope_is_ready_only_for_a_current_candidate() -> None:
    result = build_effective_entry_scope(_facts(), now_ms=NOW_MS)

    assert result.can_issue_ticket_now is True
    assert result.eligible_scope_count == 1
    assert result.remaining_ticket_slots == 2
    assert result.scopes[0].first_blocker is None


def test_effective_entry_scope_keeps_the_first_persisted_readiness_blocker() -> None:
    result = build_effective_entry_scope(
        _facts(scopes=(_scope(readiness_state="blocked", readiness_first_blocker="spread_too_wide"),)),
        now_ms=NOW_MS,
    )

    assert result.can_issue_ticket_now is False
    assert result.first_blocker == "spread_too_wide"
    assert result.scopes[0].first_blocker == "spread_too_wide"


def test_effective_entry_scope_prioritizes_global_pause_over_scope_facts() -> None:
    result = build_effective_entry_scope(
        _facts(new_entry_submit_enabled=False, scopes=(_scope(strategy_entry_state="paused"),)),
        now_ms=NOW_MS,
    )

    assert result.first_blocker == "global_entry_paused"
    assert result.scopes[0].first_blocker == "global_entry_paused"


def test_effective_entry_scope_does_not_call_itself_an_admission_guarantee_when_no_signal_exists() -> None:
    result = build_effective_entry_scope(
        _facts(scopes=(_scope(readiness_state="signal_absent"),)),
        now_ms=NOW_MS,
    )

    assert result.can_issue_ticket_now is False
    assert result.first_blocker == "signal_absent"
