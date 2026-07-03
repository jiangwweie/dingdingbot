from __future__ import annotations

import json
from pathlib import Path

from src.infrastructure.runtime_control_state_repository import (
    FileBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)


def test_file_backed_runtime_control_state_repository_reads_candidate_pool_inputs(
    tmp_path: Path,
):
    repository = FileBackedRuntimeControlStateRepository()
    paths = {
        key: tmp_path / f"{key}.json"
        for key in (
            "daily_table",
            "tradeability",
            "replay_live_parity",
            "action_time_boundary",
            "sor_detector",
            "mi_trial_admission",
            "brf2_runtime_signal_facts",
            "single_lane_task_packet",
            "runtime_active_monitor",
            "owner_pretrade_authorization",
        )
    }
    for key, path in paths.items():
        path.write_text(json.dumps({"source": key}), encoding="utf-8")

    inputs = repository.candidate_pool_inputs(
        daily_table_json=paths["daily_table"],
        tradeability_json=paths["tradeability"],
        replay_live_parity_json=paths["replay_live_parity"],
        action_time_boundary_json=paths["action_time_boundary"],
        sor_detector_json=paths["sor_detector"],
        mi_trial_admission_json=paths["mi_trial_admission"],
        brf2_runtime_signal_facts_json=paths["brf2_runtime_signal_facts"],
        single_lane_task_packet_json=paths["single_lane_task_packet"],
        runtime_active_monitor_json=paths["runtime_active_monitor"],
        owner_pretrade_authorization_json=paths["owner_pretrade_authorization"],
    )

    assert inputs["daily_table"] == {"source": "daily_table"}
    assert inputs["owner_pretrade_authorization"] == {
        "source": "owner_pretrade_authorization"
    }


def test_file_backed_runtime_control_state_repository_fails_closed_when_required(
    tmp_path: Path,
):
    repository = FileBackedRuntimeControlStateRepository()

    try:
        repository.read_json(tmp_path / "missing.json", missing_ok=False)
    except RuntimeControlStateRepositoryError as exc:
        assert "is missing" in str(exc)
    else:
        raise AssertionError("missing required file did not fail")


def test_file_backed_runtime_control_state_repository_reads_goal_sources(
    tmp_path: Path,
):
    repository = FileBackedRuntimeControlStateRepository()
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "watcher-tick.json").write_text(
        json.dumps({"status": "ok"}),
        encoding="utf-8",
    )
    candidate_pool = tmp_path / "candidate_pool.json"
    candidate_pool.write_text(
        json.dumps({"schema": "brc.strategy_live_candidate_pool.v1"}),
        encoding="utf-8",
    )

    artifacts = repository.goal_status_source_artifacts(
        report_dir=report_dir,
        source_artifact_files={
            "watcher_tick": "watcher-tick.json",
            "latest_summary": "latest-summary.json",
        },
        candidate_pool_json=candidate_pool,
    )

    assert artifacts["watcher_tick"] == {"status": "ok"}
    assert artifacts["latest_summary"] is None
    assert artifacts["candidate_pool"] == {
        "schema": "brc.strategy_live_candidate_pool.v1"
    }
