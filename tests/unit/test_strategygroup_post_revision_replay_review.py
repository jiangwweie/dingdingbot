from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_strategygroup_post_revision_replay_review.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_post_revision_replay_review",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_post_revision_replay_review_accepts_lsr_vcb_revision_cases() -> None:
    module = _load_module()

    packet = module.build_post_revision_replay_review()

    assert packet["status"] == "passed"
    assert packet["counts"]["review_case_count"] == 5
    assert packet["counts"]["passed_case_count"] == 5
    assert packet["counts"]["failed_case_count"] == 0
    assert packet["counts"]["would_enter_case_count"] == 2
    assert packet["counts"]["disable_or_no_action_case_count"] == 3
    assert packet["counts"]["real_order_authorized_count"] == 0
    assert packet["counts"]["l4_scope_change_recommended_count"] == 0
    assert packet["checks"] == {
        "lsr_short_revival_would_enter": True,
        "lsr_old_long_preview_disabled": True,
        "vcb_true_breakout_with_volume_would_enter": True,
        "vcb_false_breakout_reversal_disabled": True,
        "vcb_volume_expansion_missing_disabled": True,
        "no_case_authorizes_execution": True,
    }

    rows = {
        (row["strategy_group_id"], row["fixture_case"]): row
        for row in packet["review_rows"]
    }
    assert set(rows) == {
        ("LSR-001", "short_revival_short_would_enter"),
        ("LSR-001", "old_long_preview_disabled"),
        ("VCB-001", "true_breakout_with_volume_would_enter"),
        ("VCB-001", "false_breakout_reversal_disabled"),
        ("VCB-001", "volume_expansion_missing_disabled"),
    }

    lsr_short = rows[("LSR-001", "short_revival_short_would_enter")]
    assert lsr_short["observed_signal_type"] == "would_enter"
    assert lsr_short["observed_side"] == "short"
    assert lsr_short["logic_version"] == "lsr-001-price-action-v1"
    assert {
        "lsr_upper_range_liquidity_sweep_detected",
        "lsr_short_revival_confirmation_present",
        "lsr_lookahead_proxy_absent",
    }.issubset(set(lsr_short["reason_codes"]))

    lsr_disabled = rows[("LSR-001", "old_long_preview_disabled")]
    assert lsr_disabled["observed_signal_type"] == "no_action"
    assert lsr_disabled["observed_side"] == "none"
    assert lsr_disabled["reason_codes"] == [
        "lsr_disable_long_preview_conflicts_with_short_revival_lead"
    ]

    vcb_long = rows[("VCB-001", "true_breakout_with_volume_would_enter")]
    assert vcb_long["observed_signal_type"] == "would_enter"
    assert vcb_long["observed_side"] == "long"
    assert vcb_long["logic_version"] == "vcb-001-price-action-v1"
    assert {
        "vcb_compression_window_present",
        "vcb_breakout_close_confirmed",
        "vcb_volume_expansion_confirmed",
        "vcb_post_entry_edge_proxy_without_lookahead",
    }.issubset(set(vcb_long["reason_codes"]))

    vcb_false_breakout = rows[("VCB-001", "false_breakout_reversal_disabled")]
    assert vcb_false_breakout["observed_signal_type"] == "no_action"
    assert vcb_false_breakout["observed_side"] == "none"
    assert vcb_false_breakout["reason_codes"] == [
        "vcb_disable_false_breakout_reversal_detected"
    ]

    vcb_missing_volume = rows[("VCB-001", "volume_expansion_missing_disabled")]
    assert vcb_missing_volume["observed_signal_type"] == "no_action"
    assert vcb_missing_volume["observed_side"] == "none"
    assert vcb_missing_volume["reason_codes"] == [
        "vcb_no_action_volume_expansion_missing"
    ]

    for row in packet["review_rows"]:
        assert row["passed"] is True
        assert row["real_order_authority"] is False
        assert row["candidate_or_finalgate_authority"] is False
        assert row["operation_layer_authority"] is False
        assert row["l2_promotion_authority"] is False
        assert row["l4_scope_change_recommended"] is False

    assert packet["decision"] == {
        "post_revision_replay_review_passed": True,
        "l2_promotion_recommended_now": False,
        "l4_scope_change_recommended": False,
        "real_order_scope_change_recommended": False,
        "default_next_step": "record_lsr001_vcb001_post_revision_quality_before_l2",
    }
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["approaches_real_order"] is False
    assert packet["interaction"]["calls_finalgate"] is False
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["interaction"]["calls_exchange_write"] is False
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["server_files_mutated"] is False
    assert packet["safety_invariants"]["l4_real_order_scope_expanded"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_post_revision_replay_review_cli_writes_json_and_owner_progress(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    output_json = tmp_path / "post-revision-review.json"
    output_md = tmp_path / "post-revision-review.md"

    exit_code = module.main(
        [
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "strategygroup_post_revision_replay_review"
    assert file_payload["status"] == "passed"
    owner_text = output_md.read_text(encoding="utf-8")
    assert "LSR/VCB Post-Revision Replay Review" in owner_text
    assert "short_revival_short_would_enter" in owner_text
    assert "false_breakout_reversal_disabled" in owner_text
    assert "record_lsr001_vcb001_post_revision_quality_before_l2" in owner_text
