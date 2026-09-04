import hashlib
import json
from pathlib import Path

from src.trading_kernel.domain.instrument_selection import (
    FROZEN_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
V1_MANIFEST = (
    REPO_ROOT
    / "research/multi_strategy_selection/stage2_replay_manifest_v1_blocked.json"
)
V2_MANIFEST = REPO_ROOT / "research/multi_strategy_selection/stage2_replay_manifest.json"


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
