from __future__ import annotations

from pathlib import Path

import pytest

from src.application.current_truth_reducer import (
    reduce_current_truth,
    semantic_state_for_aggregate,
)
from src.domain.runtime_semantic_kernel import RuntimeState
from tests.unit.test_action_time_projection_truth import (
    _attach_certifications,
    _ready_control_state,
)


def test_current_truth_conserves_release_certification_as_one_lane_blocker(
    tmp_path: Path,
) -> None:
    bundle = reduce_current_truth(_ready_control_state(tmp_path))

    assert len(bundle.lane_decisions) == 22
    assert {item.first_blocker for item in bundle.lane_decisions} == {
        "action_time_boundary_not_reproduced"
    }
    assert {item.blocker_owner for item in bundle.lane_decisions} == {"system"}
    assert bundle.system_summary["current_issue_count"] == 22


def test_current_truth_uses_one_stable_market_wait_after_certification(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)
    _attach_certifications(state)

    first = reduce_current_truth(state)
    second = reduce_current_truth(state)

    assert {item.first_blocker for item in first.lane_decisions} == {
        "market_wait_validated"
    }
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert not first.incident_decisions


def test_current_truth_promotes_a_fresh_fully_ready_lane_to_action_time(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)
    _attach_certifications(state)
    candidate = state["candidate_scope"][0]
    now_ms = state["read_now_ms"]
    state["live_signal_events"] = [
        {
            "signal_event_id": "signal:current-truth-ready",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "status": "facts_validated",
            "freshness_state": "fresh",
            "observed_at_ms": now_ms,
            "created_at_ms": now_ms,
            "expires_at_ms": now_ms + 60_000,
        }
    ]

    bundle = reduce_current_truth(state)
    target = next(
        item
        for item in bundle.lane_decisions
        if item.lane_identity.key
        == (candidate["strategy_group_id"], candidate["symbol"], candidate["side"])
    )

    assert target.first_blocker == "action_time_preflight_ready"
    assert target.current_issue is False


def test_current_truth_keeps_two_tickets_as_independent_current_decisions(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)
    for key in (
        "available_control_state_tables",
        "ticket_bound_protected_submit_attempts",
        "ticket_bound_exchange_commands",
        "ticket_bound_order_lifecycle_runs",
        "ticket_bound_reconciliation_ticks",
        "runtime_incidents",
        "ticket_bound_scope_freezes",
    ):
        state.pop(key, None)
    state["action_time_tickets"] = [
        {
            "ticket_id": "ticket:btc",
            "status": "outcome_unknown",
            "exposure_episode_id": "exposure:btc",
            "netting_domain_key": "binance:BTCUSDT",
            "protection_state": "ready",
            "reconciliation_state": "pending",
            "created_at_ms": state["read_now_ms"],
        },
        {
            "ticket_id": "ticket:eth",
            "status": "submitted",
            "exposure_episode_id": "exposure:eth",
            "netting_domain_key": "binance:ETHUSDT",
            "protection_state": "missing",
            "reconciliation_state": "pending",
            "created_at_ms": state["read_now_ms"],
        },
    ]

    bundle = reduce_current_truth(state)
    by_ticket = {item.ticket_id: item for item in bundle.trade_decisions}

    assert set(by_ticket) == {"ticket:btc", "ticket:eth"}
    assert by_ticket["ticket:btc"].first_blocker == "outcome_unknown"
    assert by_ticket["ticket:eth"].first_blocker == "protection_missing"
    assert by_ticket["ticket:btc"].semantic_fingerprint != by_ticket["ticket:eth"].semantic_fingerprint


def test_unknown_aggregate_status_is_a_current_fail_closed_blocker() -> None:
    semantic = semantic_state_for_aggregate("ticket", "a_new_status")

    assert semantic.state is RuntimeState.BLOCKED
    assert semantic.is_current is True
    assert semantic.reason_code == "unsupported_runtime_status:ticket:a_new_status"


@pytest.mark.parametrize(
    ("case", "owner_state", "runtime_state", "blocker", "owner_action"),
    (
        (
            "entry_unknown",
            "processing",
            RuntimeState.OUTCOME_UNKNOWN,
            "entry_exchange_outcome_unknown",
            False,
        ),
        (
            "accepted_zero_fill",
            "processing",
            RuntimeState.RUNNING,
            "entry_fill_pending",
            False,
        ),
        (
            "sl_pending_within_sla",
            "processing",
            RuntimeState.RUNNING,
            "initial_stop_pending_within_sla",
            False,
        ),
        (
            "sl_hard_incident",
            "needs_intervention",
            RuntimeState.BLOCKED,
            "initial_stop_deadline_exhausted",
            True,
        ),
        (
            "sl_pending_overdue",
            "needs_intervention",
            RuntimeState.BLOCKED,
            "initial_stop_deadline_exhausted",
            True,
        ),
        (
            "active_hold_without_incident",
            "needs_intervention",
            RuntimeState.BLOCKED,
            "initial_stop_pending",
            True,
        ),
        (
            "tp1_degraded",
            "running",
            RuntimeState.RUNNING,
            "tp1_recovery_pending",
            False,
        ),
        (
            "protected_matched",
            "running",
            RuntimeState.RUNNING,
            "",
            False,
        ),
        (
            "closed",
            "completed",
            RuntimeState.TERMINAL,
            "",
            False,
        ),
    ),
)
def test_current_truth_reduces_typed_ticket_chain_without_market_wait_fallback(
    case,
    owner_state,
    runtime_state,
    blocker,
    owner_action,
):
    state = _typed_trade_control_state(case)

    bundle = reduce_current_truth(state)

    assert len(bundle.trade_decisions) == 1
    decision = bundle.trade_decisions[0]
    assert decision.owner_state == owner_state
    assert decision.state is runtime_state
    assert decision.first_blocker == blocker
    assert decision.owner_action_required is owner_action
    assert decision.first_blocker not in {"market_wait_validated", "no_signal"}
    assert decision.capacity_held is (case != "closed")


@pytest.mark.parametrize(
    "case",
    ("closed_open_sl", "closed_capacity_held", "budget_settled_only"),
)
def test_current_truth_does_not_complete_without_full_terminal_release_proof(case):
    state = _typed_trade_control_state(case)

    decision = reduce_current_truth(state).trade_decisions[0]

    assert decision.owner_state != "completed"
    assert decision.state is RuntimeState.BLOCKED
    assert decision.capacity_held is True


def test_current_truth_uses_attempt_current_protection_generation_not_maximum():
    state = _typed_trade_control_state("protected_matched")
    attempt = state["ticket_bound_protected_submit_attempts"][0]
    attempt["protection_barrier_generation"] = 2
    for command in state["ticket_bound_exchange_commands"]:
        if command["order_role"] in {"SL", "TP1"}:
            command["command_generation"] = 2
    stale_future = {
        **state["ticket_bound_exchange_commands"][1],
        "exchange_command_id": "command:sl:future",
        "command_generation": 3,
        "command_state": "confirmed_rejected",
        "exchange_order_id": None,
        "exchange_order_status": "REJECTED",
    }
    state["ticket_bound_exchange_commands"].append(stale_future)

    decision = reduce_current_truth(state).trade_decisions[0]

    assert decision.first_blocker == "current_truth_future_protection_generation"
    assert decision.state is RuntimeState.BLOCKED


def test_current_truth_ignores_closed_stale_generation_incident_history():
    state = _typed_trade_control_state("protected_matched")
    state["runtime_incidents"] = [
        {
            "incident_id": "incident:old-generation",
            "incident_type": "initial_stop_not_established",
            "status": "closed",
            "blocker_class": "initial_stop_deadline_exhausted",
            "details": {
                "ticket_id": "ticket:typed-trade",
                "protected_submit_attempt_id": "attempt:typed-trade",
                "exposure_episode_id": "episode:old",
                "netting_domain_key": "domain:old",
                "protection_barrier_generation": 0,
            },
        }
    ]

    decision = reduce_current_truth(state).trade_decisions[0]

    assert decision.owner_state == "running"
    assert decision.first_blocker == ""


def test_current_truth_keeps_hard_stopped_sl_recovery_as_needs_intervention():
    state = _typed_trade_control_state("protected_matched")
    state["ticket_bound_protected_submit_attempts"][0][
        "protection_barrier_state"
    ] = "hard_stopped"
    state["ticket_bound_protection_recovery_commands"] = [
        _recovery_command(state, status="prepared")
    ]

    decision = reduce_current_truth(state).trade_decisions[0]

    assert decision.owner_state == "needs_intervention"
    assert decision.state is RuntimeState.BLOCKED
    assert decision.first_blocker == "initial_stop_recovery_in_progress"
    assert decision.owner_action_required is True


def test_current_truth_keeps_tp1_only_recovery_running_without_owner_action():
    state = _typed_trade_control_state("tp1_degraded")
    state["ticket_bound_protection_recovery_commands"] = [
        _recovery_command(state, status="prepared", missing_roles=("TP1",))
    ]

    decision = reduce_current_truth(state).trade_decisions[0]

    assert decision.owner_state == "running"
    assert decision.state is RuntimeState.RUNNING
    assert decision.first_blocker == "tp1_recovery_pending"
    assert decision.owner_action_required is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ticket_id", "ticket:other"),
        ("protected_submit_attempt_id", "attempt:other"),
        ("exposure_episode_id", "episode:other"),
        ("netting_domain_key", "domain:other"),
        ("source_entry_exchange_command_id", "command:other"),
        ("protection_quantity", "0.02"),
    ),
)
def test_current_truth_fails_closed_on_current_recovery_lineage_mismatch(
    field,
    value,
):
    state = _typed_trade_control_state("protected_matched")
    recovery = _recovery_command(state, status="prepared")
    recovery[field] = value
    state["ticket_bound_protection_recovery_commands"] = [recovery]

    decision = reduce_current_truth(state).trade_decisions[0]

    assert decision.state is RuntimeState.BLOCKED
    assert decision.first_blocker == "current_truth_recovery_identity_mismatch"


def test_current_truth_ignores_terminal_stale_recovery_generation_history():
    state = _typed_trade_control_state("protected_matched")
    state["ticket_bound_protected_submit_attempts"][0][
        "protection_barrier_generation"
    ] = 2
    for command in state["ticket_bound_exchange_commands"]:
        if command["order_role"] in {"SL", "TP1"}:
            command["command_generation"] = 2
    state["ticket_bound_protection_recovery_commands"] = [
        {
            **_recovery_command(state, status="failed"),
            "protection_barrier_generation": 1,
        }
    ]

    decision = reduce_current_truth(state).trade_decisions[0]

    assert decision.owner_state == "running"
    assert decision.first_blocker == ""


def test_current_truth_fails_closed_on_future_recovery_generation():
    state = _typed_trade_control_state("protected_matched")
    state["ticket_bound_protection_recovery_commands"] = [
        {
            **_recovery_command(state, status="prepared"),
            "protection_barrier_generation": 2,
        }
    ]

    decision = reduce_current_truth(state).trade_decisions[0]

    assert decision.state is RuntimeState.BLOCKED
    assert decision.first_blocker == "current_truth_future_recovery_generation"


def test_current_truth_fails_closed_when_repository_schema_lacks_typed_table():
    state = _typed_trade_control_state("protected_matched")
    state["available_control_state_tables"] = tuple(
        key
        for key in state
        if key != "ticket_bound_protection_recovery_commands"
    )

    decision = reduce_current_truth(state).trade_decisions[0]

    assert decision.state is RuntimeState.BLOCKED
    assert decision.first_blocker == "schema_revision_mismatch"
    assert decision.capacity_held is True
    assert decision.owner_state == "needs_intervention"
    assert decision.owner_action_required is True


def test_zero_fill_requires_exact_flat_terminal_proof_before_completion():
    state = _typed_trade_control_state("accepted_zero_fill")

    active = reduce_current_truth(state).trade_decisions[0]

    assert active.owner_state == "processing"
    assert active.capacity_held is True
    assert active.first_blocker == "entry_fill_pending"
    assert all(
        command.get("exchange_write_called") is False
        for command in state["ticket_bound_exchange_commands"]
        if command["order_role"] in {"SL", "TP1"}
    )

    state["action_time_tickets"][0]["status"] = "closed"
    state["ticket_bound_protected_submit_attempts"][0].update(
        entry_effect_state="reconciled_absent",
        protection_barrier_state="closed",
    )
    state["ticket_bound_exchange_commands"][0].update(
        command_state="reconciled_absent",
        outcome_class="reconciled_absence",
        exchange_order_status="CANCELED",
    )
    state["ticket_bound_order_lifecycle_runs"][0]["status"] = "lifecycle_closed"
    state["ticket_bound_reconciliation_ticks"][0].update(
        status="matched",
        position_state="flat",
    )
    state["budget_reservations"][0]["status"] = "released"

    completed = reduce_current_truth(state).trade_decisions[0]

    assert completed.owner_state == "completed"
    assert completed.capacity_held is False


def _recovery_command(
    state: dict,
    *,
    status: str,
    missing_roles: tuple[str, ...] = ("SL",),
) -> dict:
    ticket = state["action_time_tickets"][0]
    attempt = state["ticket_bound_protected_submit_attempts"][0]
    entry = state["ticket_bound_exchange_commands"][0]
    lifecycle = state["ticket_bound_order_lifecycle_runs"][0]
    return {
        "protection_recovery_command_id": "recovery:typed-trade",
        "protected_submit_attempt_id": attempt["protected_submit_attempt_id"],
        "lifecycle_run_id": lifecycle["lifecycle_run_id"],
        "ticket_id": ticket["ticket_id"],
        "strategy_group_id": ticket["strategy_group_id"],
        "symbol": ticket["symbol"],
        "side": ticket["side"],
        "protection_barrier_generation": attempt[
            "protection_barrier_generation"
        ],
        "exposure_episode_id": ticket["exposure_episode_id"],
        "netting_domain_key": entry["netting_domain_key"],
        "source_entry_exchange_command_id": entry["exchange_command_id"],
        "protection_quantity": attempt["protection_quantity"],
        "status": status,
        "command_plan": {
            "submit_missing_orders": [
                {"order_role": role} for role in missing_roles
            ]
        },
        "first_blocker": (
            "protection_recovery_failed" if status in {"blocked", "failed"} else None
        ),
    }


def _typed_trade_control_state(case: str) -> dict:
    now_ms = 1_770_001_000_000
    ticket_id = "ticket:typed-trade"
    attempt_id = "attempt:typed-trade"
    episode_id = "episode:typed-trade"
    netting_key = "account|instrument|one_way|BOTH"
    state = {
        "read_now_ms": now_ms,
        "candidate_scope": [],
        "action_time_tickets": [
            {
                "ticket_id": ticket_id,
                "action_time_lane_input_id": "lane:typed-trade",
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "status": "submitted",
                "exposure_episode_id": episode_id,
                "created_at_ms": now_ms - 10_000,
            }
        ],
        "ticket_bound_protected_submit_attempts": [
            {
                "protected_submit_attempt_id": attempt_id,
                "ticket_id": ticket_id,
                "status": "submitted",
                "entry_effect_state": "accepted_filled",
                "entry_effect_observed_at_ms": now_ms - 5_000,
                "protection_barrier_state": "initial_stop_confirmed",
                "protection_barrier_generation": 1,
                "initial_stop_deadline_at_ms": now_ms + 10_000,
                "protection_quantity": "0.01",
                "created_at_ms": now_ms - 9_000,
                "updated_at_ms": now_ms - 1_000,
            }
        ],
        "action_time_lane_inputs": [
            {
                "action_time_lane_input_id": "lane:typed-trade",
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
            }
        ],
        "ticket_bound_exchange_commands": [
            {
                "exchange_command_id": "command:entry",
                "protected_submit_attempt_id": attempt_id,
                "ticket_id": ticket_id,
                "order_role": "ENTRY",
                "command_source": "protected_submit",
                "source_command_id": attempt_id,
                "command_generation": 1,
                "command_state": "confirmed_submitted",
                "outcome_class": "exchange_accepted",
                "exchange_order_id": "exchange:entry",
                "exchange_order_status": "FILLED",
                "result_facts_complete": True,
                "executed_qty": "0.01",
                "average_exec_price": "2000",
                "updated_at_ms": now_ms - 5_000,
                "exposure_episode_id": episode_id,
                "netting_domain_key": netting_key,
            },
            {
                "exchange_command_id": "command:sl",
                "protected_submit_attempt_id": attempt_id,
                "ticket_id": ticket_id,
                "order_role": "SL",
                "command_source": "protected_submit",
                "source_command_id": attempt_id,
                "command_generation": 1,
                "command_state": "confirmed_submitted",
                "outcome_class": "exchange_accepted",
                "exchange_order_id": "exchange:sl",
                "exchange_order_status": "OPEN",
                "result_facts_complete": True,
                "exposure_episode_id": episode_id,
                "netting_domain_key": netting_key,
            },
            {
                "exchange_command_id": "command:tp1",
                "protected_submit_attempt_id": attempt_id,
                "ticket_id": ticket_id,
                "order_role": "TP1",
                "command_source": "protected_submit",
                "source_command_id": attempt_id,
                "command_generation": 1,
                "command_state": "confirmed_submitted",
                "outcome_class": "exchange_accepted",
                "exchange_order_id": "exchange:tp1",
                "exchange_order_status": "OPEN",
                "result_facts_complete": True,
                "exposure_episode_id": episode_id,
                "netting_domain_key": netting_key,
            },
        ],
        "ticket_bound_order_lifecycle_runs": [
            {
                "lifecycle_run_id": "lifecycle:typed-trade",
                "protected_submit_attempt_id": attempt_id,
                "ticket_id": ticket_id,
                "status": "position_protected",
                "entry_fill_confirmed": True,
                "updated_at_ms": now_ms - 500,
            }
        ],
        "ticket_bound_reconciliation_ticks": [
            {
                "reconciliation_tick_id": "tick:typed-trade",
                "protected_submit_attempt_id": attempt_id,
                "ticket_id": ticket_id,
                "exposure_episode_id": episode_id,
                "status": "matched",
                "position_state": "open",
                "updated_at_ms": now_ms - 250,
            }
        ],
        "runtime_incidents": [],
        "ticket_bound_scope_freezes": [],
        "ticket_bound_protection_recovery_commands": [],
        "budget_reservations": [{"ticket_id": ticket_id, "status": "consumed"}],
    }
    attempt = state["ticket_bound_protected_submit_attempts"][0]
    commands = state["ticket_bound_exchange_commands"]
    lifecycle = state["ticket_bound_order_lifecycle_runs"][0]
    if case == "entry_unknown":
        commands[0].update(
            command_state="outcome_unknown",
            outcome_class="network_ambiguous",
            exchange_order_id=None,
            exchange_order_status=None,
            result_facts_complete=False,
        )
        attempt.update(
            entry_effect_state="outcome_unknown",
            protection_barrier_state="hard_stopped",
        )
    elif case == "accepted_zero_fill":
        commands[0].update(
            exchange_order_status="OPEN",
            executed_qty="0",
            average_exec_price=None,
        )
        for command in commands[1:]:
            command.update(
                command_state="reconciled_absent",
                outcome_class="reconciled_absence",
                exchange_order_id=None,
                exchange_order_status=None,
                exchange_write_called=False,
                result_facts_complete=True,
            )
        attempt.update(
            entry_effect_state="accepted_zero_fill",
            protection_barrier_state="fill_pending",
            protection_quantity=None,
        )
        lifecycle.update(
            status="entry_fill_pending",
            entry_fill_confirmed=False,
        )
        state["ticket_bound_reconciliation_ticks"][0].update(
            status="pending_visibility",
            position_state="unknown",
        )
    elif case == "sl_pending_within_sla":
        commands[1].update(
            command_state="prepared",
            outcome_class="pending",
            exchange_order_id=None,
            exchange_order_status=None,
            result_facts_complete=False,
        )
        attempt["protection_barrier_state"] = "initial_stop_pending"
    elif case == "sl_hard_incident":
        commands[1].update(
            command_state="confirmed_rejected",
            outcome_class="authoritative_rejection",
            exchange_order_id=None,
            exchange_order_status="REJECTED",
        )
        attempt.update(
            protection_barrier_state="hard_stopped",
            initial_stop_deadline_at_ms=now_ms - 1,
        )
        state["runtime_incidents"] = [
            {
                "incident_id": "incident:initial-stop",
                "incident_type": "initial_stop_not_established",
                "status": "open",
                "severity": "critical",
                "blocker_class": "initial_stop_deadline_exhausted",
                "details": {
                    "ticket_id": ticket_id,
                    "protected_submit_attempt_id": attempt_id,
                    "exposure_episode_id": episode_id,
                    "netting_domain_key": netting_key,
                    "protection_barrier_generation": 1,
                },
            }
        ]
        state["ticket_bound_scope_freezes"] = [
            {
                "scope_freeze_id": "hold:initial-stop",
                "source_ticket_id": ticket_id,
                "source_kind": "protection_barrier",
                "status": "active",
                "first_blocker": "initial_stop_deadline_exhausted",
                "netting_domain_key": netting_key,
            }
        ]
    elif case == "sl_pending_overdue":
        commands[1].update(
            command_state="prepared",
            outcome_class="pending",
            exchange_order_id=None,
            exchange_order_status=None,
            result_facts_complete=False,
        )
        attempt.update(
            protection_barrier_state="initial_stop_pending",
            initial_stop_deadline_at_ms=now_ms,
        )
    elif case == "active_hold_without_incident":
        commands[1].update(
            command_state="prepared",
            outcome_class="pending",
            exchange_order_id=None,
            exchange_order_status=None,
            result_facts_complete=False,
        )
        attempt["protection_barrier_state"] = "initial_stop_pending"
        state["ticket_bound_scope_freezes"] = [
            {
                "scope_freeze_id": "hold:initial-stop",
                "source_ticket_id": ticket_id,
                "source_kind": "protection_barrier",
                "status": "active",
                "first_blocker": "initial_stop_pending",
                "netting_domain_key": netting_key,
            }
        ]
    elif case == "tp1_degraded":
        commands[2].update(
            command_state="confirmed_rejected",
            outcome_class="authoritative_rejection",
            exchange_order_id=None,
            exchange_order_status="REJECTED",
        )
        attempt["protection_barrier_state"] = "degraded"
        lifecycle["status"] = "protection_degraded"
    elif case in {
        "closed",
        "closed_open_sl",
        "closed_capacity_held",
        "budget_settled_only",
    }:
        state["action_time_tickets"][0]["status"] = "closed"
        attempt["protection_barrier_state"] = "closed"
        lifecycle["status"] = "lifecycle_closed"
        state["ticket_bound_reconciliation_ticks"][0]["position_state"] = "flat"
        state["budget_reservations"][0]["status"] = "released"
        commands[1]["exchange_order_status"] = "FILLED"
        commands[2]["exchange_order_status"] = "CANCELED"
        if case == "closed_open_sl":
            commands[1]["exchange_order_status"] = "OPEN"
        elif case == "closed_capacity_held":
            state["budget_reservations"][0]["status"] = "consumed"
        elif case == "budget_settled_only":
            lifecycle["status"] = "budget_settled"
    return state
