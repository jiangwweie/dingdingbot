from __future__ import annotations

from pathlib import Path

from scripts import runtime_legacy_compatibility_isolation_packet as script


def _write(root: Path, rel_path: str, text: str = "# test\n") -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_all_required(root: Path) -> None:
    for rel_path in script.MAINLINE_ARTIFACTS:
        text = "# mainline\n"
        if rel_path.endswith("runtime_official_prepare_api_flow.py"):
            text += "from scripts.runtime_first_real_submit_api_flow import FlowConfig\n"
        if rel_path in script.STANDING_RECOVERY_PROOF_ARTIFACTS:
            text += "selected_action = 'monitor_position_or_prepare_official_reduce_only_recovery'\n"
        _write(root, rel_path, text)
    for item in script.LEGACY_COMPATIBILITY_ARTIFACTS:
        _write(root, item["path"], "# legacy\n")
        _write(root, item["history_path"], "# history\n")


def test_legacy_compatibility_isolation_passes_for_clean_mainline(tmp_path):
    _write_all_required(tmp_path)

    packet = script.build_isolation_packet(repo_root=tmp_path)

    assert packet["status"] == "legacy_compatibility_isolated_from_runtime_mainline"
    assert packet["blockers"] == []
    assert packet["checks"]["mainline_artifacts_present"] is True
    assert packet["checks"]["standing_recovery_proof_artifacts_present"] is True
    assert (
        packet["checks"]["standing_recovery_proofs_have_no_legacy_owner_close_terms"]
        is True
    )
    assert packet["checks"]["legacy_artifacts_classified"] is True
    assert packet["checks"]["legacy_artifacts_archived_to_replay_recovery_history"] is True
    assert packet["checks"]["legacy_wrapper_paths_preserved"] is True
    assert packet["checks"]["mainline_has_no_legacy_primary_gate_terms"] is True
    assert packet["checks"]["runtime_level_chain_remains_primary"] is True
    assert packet["checks"]["legacy_pre_attempt_not_primary_gate"] is True
    assert packet["checks"]["one_shot_owner_bounded_execution_preserved"] is True
    assert any(
        item["classification"] == "legacy_pre_attempt_rehearsal_replay_only"
        and item["wrapper_exists"]
        and item["history_exists"]
        for item in packet["legacy_compatibility_artifacts"]
    )
    assert all(
        item["primary_action_present"]
        for item in packet["standing_recovery_proof_artifacts"]
    )
    assert packet["cleanup_policy"]["mainline_exit_cleanup_complete"] is True
    assert packet["cleanup_policy"]["future_cleanup_required"] is False
    assert packet["cleanup_policy"]["future_archive_hygiene_recommended"] is False
    assert packet["cleanup_policy"]["archive_hygiene_completed"] is True
    assert packet["safety_invariants"]["exchange_called"] is False


def test_isolation_allows_historical_helper_only_in_neutral_wrapper(tmp_path):
    _write_all_required(tmp_path)

    packet = script.build_isolation_packet(repo_root=tmp_path)

    assert packet["status"] == "legacy_compatibility_isolated_from_runtime_mainline"
    assert any(
        warning.startswith("historically_named_prepare_helper_still_referenced:")
        for warning in packet["warnings"]
    )
    assert packet["checks"]["historically_named_prepare_helper_wrapped"] is True
    matching = [
        item
        for item in packet["mainline_artifacts"]
        if item["allowed_historical_helper_terms"]
    ]
    assert matching
    assert matching[0]["path"] == "scripts/runtime_official_prepare_api_flow.py"
    assert any(
        term.endswith(":FlowConfig")
        for term in matching[0]["allowed_historical_helper_terms"]
    )


def test_isolation_blocks_when_mainline_uses_legacy_primary_gate(tmp_path):
    _write_all_required(tmp_path)
    target = tmp_path / script.MAINLINE_ARTIFACTS[0]
    target.write_text(
        "from scripts.verify_runtime_submit_rehearsal_pre_live_packet import main\n",
        encoding="utf-8",
    )

    packet = script.build_isolation_packet(repo_root=tmp_path)

    assert packet["status"] == "legacy_compatibility_isolation_blocked"
    assert any(
        blocker.startswith("mainline_uses_legacy_primary_gate_terms:")
        for blocker in packet["blockers"]
    )
    assert packet["checks"]["mainline_has_no_legacy_primary_gate_terms"] is False


def test_isolation_blocks_missing_legacy_artifact(tmp_path):
    _write_all_required(tmp_path)
    missing = tmp_path / script.LEGACY_COMPATIBILITY_ARTIFACTS[0]["history_path"]
    missing.unlink()

    packet = script.build_isolation_packet(repo_root=tmp_path)

    assert packet["status"] == "legacy_compatibility_isolation_blocked"
    assert any(
        blocker.startswith("legacy_artifact_missing:")
        for blocker in packet["blockers"]
    )
    assert packet["checks"]["legacy_artifacts_classified"] is False
    assert packet["checks"]["legacy_artifacts_archived_to_replay_recovery_history"] is False


def test_isolation_blocks_legacy_owner_close_terms_in_standing_recovery_proof(tmp_path):
    _write_all_required(tmp_path)
    target = tmp_path / script.STANDING_RECOVERY_PROOF_ARTIFACTS[0]
    target.write_text(
        "selected_action = 'monitor_position_or_owner_authorize_reduce_only_close'\n",
        encoding="utf-8",
    )

    packet = script.build_isolation_packet(repo_root=tmp_path)

    assert packet["status"] == "legacy_compatibility_isolation_blocked"
    assert any(
        blocker.startswith("standing_recovery_proof_uses_legacy_owner_close_terms:")
        for blocker in packet["blockers"]
    )
    assert (
        packet["checks"]["standing_recovery_proofs_have_no_legacy_owner_close_terms"]
        is False
    )


def test_isolation_cli_outputs_json(tmp_path, capsys, monkeypatch):
    output_path = tmp_path / "out" / "packet.json"

    monkeypatch.setattr(
        script,
        "ROOT_DIR",
        Path("/Users/jiangwei/Documents/final-sprint6-integration"),
    )

    assert script.main(["--output-json", str(output_path)]) == 0

    captured = capsys.readouterr()
    assert "legacy_compatibility_isolated_from_runtime_mainline" in captured.out
    assert output_path.exists()
