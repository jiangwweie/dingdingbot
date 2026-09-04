import hashlib
import json
from pathlib import Path

import pandas as pd

from src.trading_kernel.domain.instrument_selection import (
    FROZEN_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
V1_MANIFEST = (
    REPO_ROOT
    / "research/multi_strategy_selection/stage2_replay_manifest_v1_blocked.json"
)
V2_MANIFEST = REPO_ROOT / "research/multi_strategy_selection/stage2_replay_manifest.json"
ARTIFACTS = REPO_ROOT / "research/multi_strategy_selection/artifacts"


def test_stage2_manifest_freezes_exact_current_candidate_universe() -> None:
    manifest = json.loads(V1_MANIFEST.read_text(encoding="utf-8"))
    expected = tuple(sorted(FROZEN_CANDIDATE_EXCHANGE_INSTRUMENT_IDS))
    digest = "sha256:" + hashlib.sha256(
        json.dumps(
            expected,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    assert manifest["dev_head_sha"] == (
        "2697f4b5943ed6a98f04a93e1b78d38e53780890"
    )
    assert manifest["candidate_count"] == 24
    assert tuple(manifest["candidate_universe"]) == expected
    assert manifest["candidate_universe_digest"] == digest
    assert manifest["completed_stages"] == ["R0", "R1", "R2"]
    assert manifest["blocked_before_stage"] == "R3"


def test_protocol_v2_manifest_preserves_authority_and_claim_boundary() -> None:
    manifest = json.loads(V2_MANIFEST.read_text(encoding="utf-8"))
    expected = tuple(sorted(FROZEN_CANDIDATE_EXCHANGE_INSTRUMENT_IDS))

    assert manifest["protocol_version"] == "2"
    assert manifest["research_status"] == "STAGE2_FULL_REPLAY_COMPLETE"
    assert manifest["candidate_count"] == 24
    assert tuple(manifest["candidate_universe"]) == expected
    assert manifest["research_estimand"] == "signal_basis_event_path_quality"
    assert manifest["signal_anchor_basis"] == "trigger_candle_final_close"
    assert manifest["forward_path_start"] == "strictly_after_trigger_close"
    assert manifest["execution_equivalence"] is False
    assert manifest["production_execution_validation"] == "secondary_only"
    assert manifest["option_a"] == "OUT_OF_SCOPE"
    assert manifest["completed_stages"] == [f"R{index}" for index in range(17)]
    assert manifest["selector_design_authority"] == "NONE"
    assert manifest["implementation_authority"] == "NONE"
    assert manifest["production_authority"] == "NONE"


def test_stage2_1_manifest_binds_inputs_outputs_and_no_selector_authority() -> None:
    path = ARTIFACTS / "stage2_1_cluster_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    summary = pd.read_csv(ARTIFACTS / "stage2_1_cluster_summary.csv")

    assert manifest["research_status"] == "STAGE2_1_CLUSTER_ROBUSTNESS_COMPLETE"
    assert manifest["base_stage2_commit"] == (
        "3e073c29a27621dcde8830af6a1a7cb8115ae83e"
    )
    assert manifest["bootstrap"]["replicates"] == 20_000
    assert len(manifest["supported_hypotheses"]) == len(summary) == 4
    assert manifest["feature_selection_changed"] is False
    assert manifest["cutoff_changed"] is False
    assert manifest["selector_design_authority"] == "NONE"
    assert manifest["implementation_authority"] == "NONE"
    assert manifest["production_authority"] == "NONE"
    audit_code = REPO_ROOT / "research/multi_strategy_selection/cluster_robustness.py"
    assert manifest["audit_code_sha256"] == (
        "sha256:" + hashlib.sha256(audit_code.read_bytes()).hexdigest()
    )
    for name, expected in manifest["artifact_sha256"].items():
        actual = "sha256:" + hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest()
        assert actual == expected
