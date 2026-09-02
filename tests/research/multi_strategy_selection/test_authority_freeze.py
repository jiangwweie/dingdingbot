import hashlib
import json
from pathlib import Path

from src.trading_kernel.domain.instrument_selection import (
    FROZEN_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = (
    REPO_ROOT
    / "research/multi_strategy_selection/stage2_replay_manifest.json"
)


def test_stage2_manifest_freezes_exact_current_candidate_universe() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
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

