from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HANDOFF_ROOT = ROOT / "docs" / "current" / "strategy-group-handoffs"

PILOT_READY_SIGNAL_CONFIDENCE = {
    "MPG-001": Decimal("0.61"),
    "TEQ-001": Decimal("0.62"),
    "FBS-001": Decimal("0.60"),
    "PMR-001": Decimal("0.59"),
    "SOR-001": Decimal("0.58"),
}


def test_pilot_handoff_confidence_floor_does_not_block_ready_evaluator_outputs():
    for strategy_group_id, evaluator_confidence in PILOT_READY_SIGNAL_CONFIDENCE.items():
        path = HANDOFF_ROOT / strategy_group_id / "handoff.json"
        payload = json.loads(path.read_text())
        confidence_min = Decimal(str(payload["signal_ready_rule"]["confidence_min"]))

        assert confidence_min <= evaluator_confidence, strategy_group_id
