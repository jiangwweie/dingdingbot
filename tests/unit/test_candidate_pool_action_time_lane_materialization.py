from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import materialize_candidate_pool_action_time_lane as materializer


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "materialization_dir": str(tmp_path / "materialized"),
        "env_file": None,
        "api_base": "http://unit",
        "source": "sample",
        "one_hour_limit": 25,
        "four_hour_limit": 25,
        "timeout_seconds": 10.0,
        "allow_prepare_records": True,
        "owner_operator_id": "owner",
        "owner_confirmation_reference": "owner-authorized-unit",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _candidate_pool() -> dict:
    return {
        "schema": "brc.strategy_live_candidate_pool.v1",
        "status": "strategy_live_candidate_pool_ready",
        "action_time_lane_inputs": [
            {
                "strategy_group_id": "SOR-001",
                "strategy_family_version_id": "SOR-001-v0",
                "symbol": "ETHUSDT",
                "side": "long",
                "fresh_signal_timestamp_utc": "2026-07-03T12:00:00+00:00",
                "lane_fingerprint": "lane-sor-eth-long-1",
                "runtime_profile": {
                    "runtime_profile_id": "profile-sor-eth",
                    "target_notional_usdt": "10",
                    "max_notional": "10",
                    "leverage": "1",
                    "authority_boundary": "selected_runtime_profile_boundary_only; no_live_profile_or_sizing_change",
                },
                "signal_state": "fresh",
                "scope_state": "live_submit_allowed",
                "promotion_state": "action_time_lane",
                "first_blocker": "action_time_preflight_ready",
                "selected_runtime_instance_ids": ["runtime-SOR-001-ETHUSDT"],
            }
        ],
    }


def test_materializes_action_time_lane_into_watcher_prepare_evidence(tmp_path: Path):
    candidate_pool_json = tmp_path / "candidate-pool.json"
    report_dir = tmp_path / "report"
    output_json = report_dir / "action-time-lane-materialization.json"
    _write(candidate_pool_json, _candidate_pool())
    _write(
        report_dir / "status-artifact.json",
        {
            "status": "ok",
            "selected_runtime_instance_ids": ["runtime-SOR-001-ETHUSDT"],
            "runtime_signal_summaries": [],
            "safety_invariants": {"exchange_write_called": False},
        },
    )

    def fake_prepare(args: argparse.Namespace) -> dict:
        signal_path = Path(args.signal_output_json)
        _write(
            signal_path,
            {
                "strategy_family_id": "SOR-001",
                "strategy_family_version_id": "SOR-001-v0",
                "runtime_instance_id": "runtime-SOR-001-ETHUSDT",
                "symbol": "ETHUSDT",
                "side": "long",
            },
        )
        return {
            "scope": "runtime_next_attempt_observation_api_prepare_flow",
            "status": "ready_for_final_gate_preflight",
            "signal_input_json": str(signal_path),
            "blockers": [],
            "ids": {
                "authorization_id": "auth-sor-eth-1",
                "order_candidate_id": "candidate-sor-eth-1",
            },
            "safety_invariants": {
                "prepare_records_created": True,
                "shadow_candidate_created": True,
                "runtime_execution_intent_draft_created": True,
                "recorded_execution_intent_created": True,
                "submit_authorization_created": True,
                "protection_plan_created": True,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    payload = materializer.materialize_action_time_lane(
        candidate_pool_json=candidate_pool_json,
        report_dir=report_dir,
        output_json=output_json,
        args=_args(tmp_path),
        prepare_builder=fake_prepare,
    )

    assert payload["status"] == "ready_for_action_time_final_gate"
    assert payload["strategy_group_id"] == "SOR-001"
    assert payload["symbol"] == "ETHUSDT"
    assert payload["prepared_authorization_id"] == "auth-sor-eth-1"
    assert payload["shadow_candidate_id"] == "candidate-sor-eth-1"
    assert payload["lane_fingerprint"] == "lane-sor-eth-long-1"
    assert payload["runtime_profile"]["max_notional"] == "10"
    status = json.loads((report_dir / "status-artifact.json").read_text())
    latest = json.loads((report_dir / "latest-status.json").read_text())
    assert status == latest
    assert status["signal_input_json"].endswith(
        "runtime-SOR-001-ETHUSDT-signal-input.json"
    )
    assert status["prepared_authorization_id"] == "auth-sor-eth-1"
    assert status["shadow_candidate_id"] == "candidate-sor-eth-1"
    assert status["candidate_pool_action_time_lane_materialization"][
        "lane_fingerprint"
    ] == "lane-sor-eth-long-1"
    assert status["runtime_signal_summaries"][0]["status"] == (
        "ready_for_final_gate_preflight"
    )
    assert status["safety_invariants"]["observed_submit_authorization_created"] is True
    assert status["safety_invariants"]["exchange_write_called"] is False
    assert json.loads((report_dir / "wakeup-evidence.json").read_text())[
        "status"
    ] == "prepared_shadow_evidence_ready_for_owner_review"
    assert output_json.exists()


def test_materializer_blocks_prepare_identity_mismatch(tmp_path: Path):
    candidate_pool_json = tmp_path / "candidate-pool.json"
    report_dir = tmp_path / "report"
    output_json = report_dir / "action-time-lane-materialization.json"
    _write(candidate_pool_json, _candidate_pool())
    _write(
        report_dir / "status-artifact.json",
        {
            "status": "ok",
            "selected_runtime_instance_ids": ["runtime-SOR-001-ETHUSDT"],
            "runtime_signal_summaries": [],
            "safety_invariants": {"exchange_write_called": False},
        },
    )

    def fake_prepare(args: argparse.Namespace) -> dict:
        signal_path = Path(args.signal_output_json)
        _write(
            signal_path,
            {
                "strategy_family_id": "SOR-001",
                "strategy_family_version_id": "SOR-001-v0",
                "runtime_instance_id": "runtime-SOR-001-ETHUSDT",
                "symbol": "ETHUSDT",
                "side": "short",
            },
        )
        return {
            "status": "ready_for_final_gate_preflight",
            "signal_input_json": str(signal_path),
            "blockers": [],
            "ids": {"authorization_id": "auth-wrong"},
            "safety_invariants": {"exchange_write_called": False},
        }

    payload = materializer.materialize_action_time_lane(
        candidate_pool_json=candidate_pool_json,
        report_dir=report_dir,
        output_json=output_json,
        args=_args(tmp_path),
        prepare_builder=fake_prepare,
    )

    assert payload["status"] == "blocked"
    assert "prepare_artifact_identity_mismatch:side" in payload["blockers"]
    assert not (report_dir / "latest-status.json").exists()


def test_materializer_noops_without_action_time_lane(tmp_path: Path):
    candidate_pool_json = tmp_path / "candidate-pool.json"
    report_dir = tmp_path / "report"
    _write(
        candidate_pool_json,
        {
            "status": "strategy_live_candidate_pool_ready",
            "action_time_lane_inputs": [],
        },
    )

    payload = materializer.materialize_action_time_lane(
        candidate_pool_json=candidate_pool_json,
        report_dir=report_dir,
        output_json=report_dir / "materialization.json",
        args=_args(tmp_path),
        prepare_builder=lambda args: (_ for _ in ()).throw(
            AssertionError("prepare must not run without an action-time lane")
        ),
    )

    assert payload["status"] == "no_action_time_lane_input"
    assert payload["prepared_authorization_id"] is None
    assert payload["safety_invariants"]["exchange_write_called"] is False


def test_materializer_noops_conditional_rehearsal_lane(tmp_path: Path):
    candidate_pool = _candidate_pool()
    candidate_pool["action_time_lane_inputs"][0][
        "scope_state"
    ] = "conditional_action_time_rehearsal_allowed"
    candidate_pool_json = tmp_path / "candidate-pool.json"
    report_dir = tmp_path / "report"
    _write(candidate_pool_json, candidate_pool)

    payload = materializer.materialize_action_time_lane(
        candidate_pool_json=candidate_pool_json,
        report_dir=report_dir,
        output_json=report_dir / "materialization.json",
        args=_args(tmp_path),
        prepare_builder=lambda args: (_ for _ in ()).throw(
            AssertionError("conditional rehearsal must not create prepare records")
        ),
    )

    assert payload["status"] == "no_live_submit_action_time_lane_input"
    assert payload["blockers"] == [
        "action_time_lane_scope_not_live_submit:conditional_action_time_rehearsal_allowed"
    ]
