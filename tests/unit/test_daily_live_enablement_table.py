from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_daily_live_enablement_table.py"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_daily_live_enablement_table.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _builder():
    return _load_module(BUILDER_PATH, "build_daily_live_enablement_table")


def _validator():
    return _load_module(VALIDATOR_PATH, "validate_daily_live_enablement_table")


def _tradeability() -> dict:
    base = {
        "schema": "brc.strategygroup_tradeability_decision.v1",
        "status": "tradeability_decision_ready",
        "decision_rows": [],
    }
    rows = [
        ("CPM-RO-001", "armed_observation", "computed_not_satisfied", "market", "continue_observation_with_failed_fact_matrix"),
        ("MPG-001", "armed_observation", "scope_not_attached", "engineering", "produce_scoped_live_observation_or_scope_proposal"),
        ("MI-001", "trial_asset_admission_candidate", "scope_not_attached", "engineering", "build_trial_asset_admission_proposal"),
        ("SOR-001", "armed_observation", "action_time_boundary_not_reproduced", "runtime", "repair_non_executing_action_time_rehearsal_path"),
        ("BRF2-001", "armed_observation", "computed_not_satisfied", "market", "continue_brf2_armed_observation_until_disable_clears"),
    ]
    for strategy_group_id, stage, blocker, owner, next_action in rows:
        base["decision_rows"].append(
            {
                "strategy_group_id": strategy_group_id,
                "stage": stage,
                "decision": "not_tradable_market_wait"
                if blocker == "computed_not_satisfied"
                else "not_tradable_asset_admission"
                if blocker == "scope_not_attached"
                else "not_tradable_facts",
                "first_blocker_class": blocker,
                "first_blocker_detail": f"{strategy_group_id} {blocker}",
                "blocker_owner": owner,
                "next_action": next_action,
                "market_wait_validation": {
                    "valid": False,
                    "not_applicable": True,
                    "checks": {},
                },
                "policy_scope": {
                    "side_scope": ["long"],
                    "symbol_scope": ["strategy_scope"],
                },
                "trade_paths": [
                    {
                        "path_id": f"{strategy_group_id}-PATH",
                        "side": "long",
                        "watcher_scope": {"symbols": "strategy_scope"},
                    }
                ],
            }
        )
    return base


def _parity() -> dict:
    return {
        "schema": "brc.replay_live_parity_audit.v1",
        "status": "replay_live_parity_audit_ready",
        "per_symbol_mismatch_table": [
            {
                "strategy_group_id": "CPM-RO-001",
                "symbol": "ETHUSDT",
                "blocker_class": "computed_not_satisfied",
                "detector_attached": True,
                "watcher_tick_present": True,
                "computed": True,
                "failed_facts": ["reclaim_confirmed"],
                "mismatch_count": 12,
                "next_action": "continue_observation_with_failed_fact_matrix",
            },
            {
                "strategy_group_id": "MPG-001",
                "symbol": "SOLUSDT",
                "blocker_class": "scope_not_attached",
                "detector_attached": True,
                "watcher_tick_present": True,
                "computed": True,
                "failed_facts": [],
                "mismatch_count": 25,
                "next_action": "produce_scoped_live_observation_or_scope_proposal",
            },
            {
                "strategy_group_id": "SOR-001",
                "symbol": "AVAXUSDT",
                "blocker_class": "action_time_boundary_not_reproduced",
                "detector_attached": True,
                "watcher_tick_present": True,
                "computed": True,
                "failed_facts": [],
                "mismatch_count": 10,
                "next_action": "repair_non_executing_action_time_rehearsal_path",
            },
        ],
    }


def _action_time() -> dict:
    return {
        "schema": "brc.strategy_fresh_signal_action_time_boundary.v1",
        "status": "strategy_fresh_signal_action_time_boundary_ready",
        "strategy_rows": [
            {
                "strategy_group_id": "CPM-RO-001",
                "path_id": "CPM-LONG",
                "first_blocker": "fresh_cpm_long_signal_absent",
                "dry_run_submit_rehearsal_ready": True,
            },
            {
                "strategy_group_id": "MPG-001",
                "path_id": "MPG-STRONG-SYMBOL-ROTATION",
                "first_blocker": "mpg_high_beta_public_facts_gap",
                "dry_run_submit_rehearsal_ready": False,
            },
            {
                "strategy_group_id": "SOR-001",
                "path_id": "SOR-LONG",
                "first_blocker": "action_time_boundary_not_reproduced",
                "dry_run_submit_rehearsal_ready": False,
            },
        ],
    }


def _mi() -> dict:
    return {
        "schema": "brc.mi_trial_admission_decision.v1",
        "status": "mi_trial_admission_decision_ready",
        "strategy_group_id": "MI-001",
        "trial_admission_decision": "park",
        "promotion_scope": "trial_admission",
        "side": "long",
        "symbol_scope": {"reviewed_symbols": ["AVAXUSDT", "ETHUSDT"]},
    }


def _runtime_safety() -> dict:
    return {
        "schema": "brc.strategygroup_runtime_safety_state.v1",
        "status": "runtime_safety_state_ready",
        "runtime_safety_state": {
            "live_submit_ready": False,
            "live_submit_ready_false_reason": "no_fresh_signal",
        },
    }


def _valid_table() -> dict:
    builder = _builder()
    return builder.build_daily_live_enablement_table(
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        mi_trial_admission=_mi(),
        runtime_safety=_runtime_safety(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )


def _errors(table: dict) -> list[str]:
    return _validator().validate_daily_live_enablement_table(table)


def test_daily_table_generator_emits_five_wip_rows_and_rank_one():
    table = _valid_table()

    assert table["schema"] == "brc.daily_live_enablement_table.v1"
    assert table["status"] == "daily_live_enablement_table_ready"
    assert [row["strategy_group_id"] for row in table["rows"]] == [
        "CPM-RO-001",
        "MPG-001",
        "MI-001",
        "SOR-001",
        "BRF2-001",
    ]
    assert sum(row["closest_to_live_rank"] == 1 for row in table["rows"]) == 1
    rank_1 = next(
        row for row in table["rows"] if row["closest_to_live_rank"] == 1
    )
    assert rank_1["strategy_group_id"] == "SOR-001"
    assert rank_1["first_blocker"] == "action_time_boundary_not_reproduced"
    assert table["source_validation"]["valid"] is True
    assert _errors(table) == []


def test_daily_table_generator_prefers_per_symbol_parity_evidence():
    table = _valid_table()
    rows = {row["strategy_group_id"]: row for row in table["rows"]}

    assert rows["MPG-001"]["symbol"] == "SOLUSDT"
    assert rows["MPG-001"]["first_blocker"] == "scope_not_attached"
    assert rows["MPG-001"]["next_engineering_action"] == (
        "produce_scoped_live_observation_or_scope_proposal"
    )
    assert "latest-replay-live-parity-audit.json" in rows["MPG-001"][
        "first_blocker_evidence"
    ]


def test_daily_table_uses_tradeability_canonical_lane_before_reselecting_symbol():
    builder = _builder()
    tradeability = _tradeability()
    mpg = next(
        row
        for row in tradeability["decision_rows"]
        if row["strategy_group_id"] == "MPG-001"
    )
    mpg["first_blocker_class"] = "watcher_tick_missing"
    mpg["next_action"] = "refresh_or_repair_watcher_public_fact_input"
    mpg["canonical_lane"] = {
        "strategy_group_id": "MPG-001",
        "symbol": "OPUSDT",
        "first_blocker": "watcher_tick_missing",
        "mismatch_count": 3,
        "live_submit_scope_priority": 20,
        "selection_rule": (
            "first_blocker_priority->live_submit_scope_priority->"
            "mismatch_count->symbol"
        ),
    }
    parity = _parity()
    parity["per_symbol_mismatch_table"].extend(
        [
            {
                "strategy_group_id": "MPG-001",
                "symbol": "SOLUSDT",
                "blocker_class": "watcher_tick_missing",
                "detector_attached": True,
                "watcher_tick_present": False,
                "computed": False,
                "failed_facts": [],
                "mismatch_count": 25,
                "live_submit_scope_priority": 0,
                "next_action": "refresh_or_repair_watcher_public_fact_input",
            },
            {
                "strategy_group_id": "MPG-001",
                "symbol": "OPUSDT",
                "blocker_class": "watcher_tick_missing",
                "detector_attached": True,
                "watcher_tick_present": False,
                "computed": False,
                "failed_facts": [],
                "mismatch_count": 3,
                "live_submit_scope_priority": 20,
                "next_action": "refresh_or_repair_watcher_public_fact_input",
            },
        ]
    )

    table = builder.build_daily_live_enablement_table(
        tradeability=tradeability,
        replay_live_parity=parity,
        action_time_boundary=_action_time(),
        mi_trial_admission=_mi(),
        runtime_safety=_runtime_safety(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in table["rows"]}
    assert rows["MPG-001"]["symbol"] == "OPUSDT"
    assert rows["MPG-001"]["canonical_lane"]["symbol"] == "OPUSDT"
    assert rows["MPG-001"]["first_blocker"] == "watcher_tick_missing"


def test_daily_table_validator_rejects_non_wip_lane():
    table = _valid_table()
    table["rows"][0]["strategy_group_id"] = "RBR-001"

    assert any("active WIP" in error for error in _errors(table))


def test_daily_table_validator_rejects_legacy_blocker():
    table = _valid_table()
    table["rows"][0]["first_blocker"] = "fresh_signal_absent"

    assert any("contract blocker" in error for error in _errors(table))


def test_daily_table_validator_rejects_empty_evidence():
    table = _valid_table()
    table["rows"][0]["first_blocker_evidence"] = ""

    assert any("first_blocker_evidence" in error for error in _errors(table))


def test_daily_table_validator_rejects_multi_action_next_action():
    table = _valid_table()
    table["rows"][0]["next_engineering_action"] = "fix_scope then rerun_table"

    assert any("one action" in error for error in _errors(table))


def test_daily_table_validator_rejects_missing_stop_condition():
    table = _valid_table()
    table["rows"][0]["stop_condition"] = ""

    assert any("stop_condition" in error for error in _errors(table))


def test_daily_table_validator_rejects_incomplete_market_wait_checklist():
    table = _valid_table()
    table["rows"][0]["first_blocker"] = "market_wait_validated"
    table["rows"][0]["market_wait_validation"] = {
        "valid": False,
        "not_applicable": False,
        "checks": {"detector": True},
    }

    assert any("complete checklist" in error for error in _errors(table))


def test_daily_table_validator_rejects_artifact_only_advanced():
    table = _valid_table()
    table["rows"][0]["first_blocker"] = "artifact_missing"
    table["rows"][0]["lane_status"] = "advanced"

    assert any("artifact-only" in error for error in _errors(table))


def test_daily_table_validator_rejects_owner_action_for_engineering_blocker():
    table = _valid_table()
    table["rows"][0]["owner_action_required"] = "yes"

    assert any("owner_action_required" in error for error in _errors(table))


def test_daily_table_validator_rejects_missing_authority_boundary():
    table = _valid_table()
    table["rows"][0]["authority_boundary"] = ""

    assert any("authority_boundary" in error for error in _errors(table))


def test_daily_table_validator_rejects_invalid_source_validation():
    table = _valid_table()
    table["source_validation"]["valid"] = False
    table["source_validation"]["sources"]["tradeability"]["valid"] = False
    table["source_validation"]["sources"]["tradeability"]["status_valid"] = False

    errors = _errors(table)

    assert any("source_validation.valid" in error for error in errors)
    assert any("tradeability.valid" in error for error in errors)


def test_daily_table_builder_marks_missing_sources_invalid():
    builder = _builder()

    table = builder.build_daily_live_enablement_table(
        tradeability={},
        replay_live_parity={},
        action_time_boundary={},
        mi_trial_admission={},
        runtime_safety={},
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    assert table["status"] == "daily_live_enablement_table_source_invalid"
    assert table["source_validation"]["valid"] is False
    assert table["source_validation"]["sources"]["tradeability"]["present"] is False
    assert any("source_validation.valid" in error for error in _errors(table))


def test_daily_table_cli_and_validator_cli_round_trip(tmp_path: Path):
    tradeability = tmp_path / "tradeability.json"
    parity = tmp_path / "parity.json"
    action_time = tmp_path / "action-time.json"
    mi = tmp_path / "mi.json"
    runtime_safety = tmp_path / "runtime-safety.json"
    output_json = tmp_path / "daily.json"
    output_md = tmp_path / "daily.md"
    tradeability.write_text(json.dumps(_tradeability()), encoding="utf-8")
    parity.write_text(json.dumps(_parity()), encoding="utf-8")
    action_time.write_text(json.dumps(_action_time()), encoding="utf-8")
    mi.write_text(json.dumps(_mi()), encoding="utf-8")
    runtime_safety.write_text(json.dumps(_runtime_safety()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--tradeability-json",
            str(tradeability),
            "--replay-live-parity-json",
            str(parity),
            "--action-time-boundary-json",
            str(action_time),
            "--mi-trial-admission-json",
            str(mi),
            "--runtime-safety-json",
            str(runtime_safety),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output_json.exists()
    assert output_md.exists()

    validate = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(output_json)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr


def test_daily_table_cli_missing_inputs_do_not_validate(tmp_path: Path):
    output_json = tmp_path / "daily.json"
    output_md = tmp_path / "daily.md"

    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--tradeability-json",
            str(tmp_path / "missing-tradeability.json"),
            "--replay-live-parity-json",
            str(tmp_path / "missing-parity.json"),
            "--action-time-boundary-json",
            str(tmp_path / "missing-action-time.json"),
            "--mi-trial-admission-json",
            str(tmp_path / "missing-mi.json"),
            "--runtime-safety-json",
            str(tmp_path / "missing-runtime-safety.json"),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    table = json.loads(output_json.read_text(encoding="utf-8"))
    assert table["status"] == "daily_live_enablement_table_source_invalid"

    validate = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(output_json)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert validate.returncode == 1
    assert "source_validation.valid" in validate.stderr
