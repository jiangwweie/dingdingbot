from __future__ import annotations

import sqlalchemy as sa

from src.application.action_time import typed_coordinator
from src.domain.action_time_deadline import ActionTimeDeadline


def test_typed_coordinator_calls_direct_application_steps_without_subprocess(monkeypatch):
    calls: list[str] = []

    def account(*_args, **_kwargs):
        calls.append("account")
        return {"status": "runtime_account_safe_facts_ready", "checks": {"account_safe_facts_ready": True}}

    def ticket(*_args, **_kwargs):
        calls.append("ticket")
        return {"status": "action_time_ticket_sequence_committed", "ticket": {"ticket_id": "ticket:one"}, "blockers": []}

    def finalgate(*_args, **_kwargs):
        calls.append("finalgate")
        return {"status": "finalgate_ready", "finalgate_pass_id": "pass:one", "blockers": []}

    def handoff(*_args, **_kwargs):
        calls.append("handoff")
        return {"status": "operation_layer_handoff_ready", "operation_layer_handoff_id": "handoff:one", "blockers": []}

    def safety(*_args, **_kwargs):
        calls.append("safety")
        return {"status": "runtime_safety_state_ready", "blockers": []}

    monkeypatch.setattr(typed_coordinator, "_materialize_account_safe_facts", account)
    monkeypatch.setattr(typed_coordinator, "materialize_action_time_ticket_sequence", ticket)
    monkeypatch.setattr(typed_coordinator, "materialize_action_time_finalgate_preflight", finalgate)
    monkeypatch.setattr(typed_coordinator, "materialize_action_time_operation_layer_handoff", handoff)
    monkeypatch.setattr(typed_coordinator, "materialize_ticket_bound_runtime_safety_state", safety)
    engine = sa.create_engine("sqlite://")
    try:
        result = typed_coordinator.coordinate_action_time_invocation(
            engine,
            action_time_invocation_id="invocation:one",
            deadline=ActionTimeDeadline.start(
                opened_wall_ms=1_000,
                opened_monotonic_ms=5_000,
            ),
            env_file=None,
            base_url="https://unit.invalid",
            wall_clock_ms=lambda: 1_001,
            monotonic_clock_ms=lambda: 5_001,
        )
    finally:
        engine.dispose()

    assert result.status == "ready"
    assert result.ticket_id == "ticket:one"
    assert result.operation_layer_handoff_id == "handoff:one"
    assert [step.name for step in result.steps] == [
        "materialize_account_safe_facts",
        "materialize_action_time_ticket_sequence",
        "materialize_action_time_finalgate_preflight",
        "materialize_action_time_operation_layer_handoff",
        "materialize_ticket_bound_runtime_safety_state",
    ]
    assert calls == ["account", "ticket", "finalgate", "handoff", "safety"]


def test_typed_coordinator_stops_before_next_authority_boundary_when_deadline_is_expired(monkeypatch):
    called = False

    def account(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("account fact collection must not begin after deadline")

    monkeypatch.setattr(typed_coordinator, "_materialize_account_safe_facts", account)
    engine = sa.create_engine("sqlite://")
    try:
        result = typed_coordinator.coordinate_action_time_invocation(
            engine,
            action_time_invocation_id="invocation:expired",
            deadline=ActionTimeDeadline.start(
                opened_wall_ms=1_000,
                opened_monotonic_ms=5_000,
                system_budget_ms=1,
            ),
            env_file=None,
            base_url="https://unit.invalid",
            monotonic_clock_ms=lambda: 5_001,
        )
    finally:
        engine.dispose()

    assert result.status == "business_blocked"
    assert result.first_blocker == "action_time_deadline_expired"
    assert called is False
