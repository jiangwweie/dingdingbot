from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine

from scripts import build_strategygroup_tradeability_decision as tradeability
from src.application.action_time.capability_certification import (
    build_action_time_capability_identities,
)
from src.application.readmodels.daily_live_enablement_table import (
    build_daily_live_enablement_table_from_control_state,
)
from src.application.readmodels.strategy_live_candidate_pool import (
    build_strategy_live_candidate_pool_from_control_state,
)
from src.application.readmodels.strategygroup_runtime_goal_status import (
    build_goal_status_artifact_from_control_state,
)
from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)
from tests.unit.test_strategygroup_tradeability_decision import (
    _attach_satisfied_pg_observation,
    _create_seeded_runtime_control_db,
)


RUNTIME_HEAD = "f" * 40


def _ready_control_state(tmp_path: Path) -> dict:
    database_url = _create_seeded_runtime_control_db(tmp_path / "runtime.db")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            state = PgBackedRuntimeControlStateRepository(
                conn,
                now_ms=1_770_001_000_000,
            ).read_control_state()
    finally:
        engine.dispose()
    _attach_satisfied_pg_observation(state, now_ms=1_770_001_000_000)
    state["server_monitor_runs"] = [
        {
            "monitor_run_id": "monitor:current",
            "runtime_head": RUNTIME_HEAD,
            "status": "quiet",
            "created_at_ms": 1_770_001_000_000,
        }
    ]
    return state


def _attach_certifications(state: dict) -> None:
    state["runtime_process_outcomes"] = [
        {
            "process_name": "action_time_capability_certification",
            "scope_key": identity.scope_key,
            "run_id": "certification:pytest:22-scope",
            "process_state": "succeeded",
            "business_state": "completed",
            "first_blocker": None,
            "runtime_head": RUNTIME_HEAD,
            "source_watermark": identity.source_watermark,
            "projector_owner": "runtime_process_outcome_projector",
            "updated_at_ms": 1_770_001_000_001,
        }
        for identity in build_action_time_capability_identities(state)
    ]


def _projection_blockers(state: dict) -> dict[str, set[str]]:
    candidate = build_strategy_live_candidate_pool_from_control_state(state)
    trade = tradeability.build_tradeability_decision_from_control_state(state)
    daily = build_daily_live_enablement_table_from_control_state(state)
    goal = build_goal_status_artifact_from_control_state(control_state=state)
    return {
        "candidate": {
            row["first_blocker"] for row in candidate["symbol_readiness_rows"]
        },
        "tradeability": {
            row["first_blocker_class"] for row in trade["decision_rows"]
        },
        "daily": {row["first_blocker"] for row in daily["rows"]},
        "goal": set(goal["evidence"]["pg_blocker_counts"]),
    }


def test_missing_release_certification_is_one_conserved_engineering_blocker(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)

    blockers = _projection_blockers(state)

    assert blockers == {
        "candidate": {"action_time_boundary_not_reproduced"},
        "tradeability": {"action_time_boundary_not_reproduced"},
        "daily": {"action_time_boundary_not_reproduced"},
        "goal": {"action_time_boundary_not_reproduced"},
    }
    goal = build_goal_status_artifact_from_control_state(control_state=state)
    assert goal["status"] == "missing_fact"
    assert goal["plain_language_stage"] == "前置事实不完整"
    candidate = build_strategy_live_candidate_pool_from_control_state(state)
    assert {
        row["action_time"]["action_time_capability_certified"]
        for row in candidate["symbol_readiness_rows"]
    } == {False}


def test_current_release_certification_allows_consistent_validated_market_wait(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)
    _attach_certifications(state)

    blockers = _projection_blockers(state)

    assert blockers == {
        "candidate": {"market_wait_validated"},
        "tradeability": {"market_wait_validated"},
        "daily": {"market_wait_validated"},
        "goal": {"market_wait_validated"},
    }
    goal = build_goal_status_artifact_from_control_state(control_state=state)
    assert goal["status"] == "waiting_for_signal"
    assert goal["plain_language_stage"] == "等待市场机会"
    candidate = build_strategy_live_candidate_pool_from_control_state(state)
    assert {
        row["action_time"]["action_time_capability_certified"]
        for row in candidate["symbol_readiness_rows"]
    } == {True}
    daily = build_daily_live_enablement_table_from_control_state(state)
    assert all(
        row["market_wait_validation"]["checks"]["action_time_path"] is True
        for row in daily["rows"]
    )


def test_runtime_head_drift_reopens_the_same_engineering_blocker(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)
    _attach_certifications(state)
    state["server_monitor_runs"][0]["runtime_head"] = "0" * 40

    blockers = _projection_blockers(state)

    assert all(
        values == {"action_time_boundary_not_reproduced"}
        for values in blockers.values()
    )


def test_tradeability_capability_check_uses_release_certification_not_static_shape(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)

    assert tradeability._pg_action_time_capability_certified(
        state,
        strategy_group_id="CPM-RO-001",
    ) is False

    _attach_certifications(state)

    assert tradeability._pg_action_time_capability_certified(
        state,
        strategy_group_id="CPM-RO-001",
    ) is True
