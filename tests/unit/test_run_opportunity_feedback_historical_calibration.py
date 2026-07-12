from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from scripts.seed_runtime_control_state_foundation import build_seed_rows
from src.application.opportunity_feedback_historical_replay import (
    build_historical_replay_scopes,
)


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_opportunity_feedback_historical_calibration.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_opportunity_feedback_historical_calibration",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _scopes():
    rows = build_seed_rows(now_ms=1_800_000_000_000)
    return build_historical_replay_scopes(
        event_specs=rows["brc_strategy_side_event_specs"],
        candidate_scopes=rows["brc_strategy_group_candidate_scope"],
        bindings=rows["brc_candidate_scope_event_bindings"],
        event_fact_rows=rows["brc_strategy_event_required_facts"],
        evaluator_versions={
            group_id: f"{group_id}-v0"
            for group_id in (
                "CPM-RO-001",
                "MPG-001",
                "MI-001",
                "SOR-001",
                "BRF2-001",
            )
        },
    )


def test_cli_has_no_file_output_interface_and_requires_pg_truth() -> None:
    module = _load_module()

    args = module._parse_args(
        [
            "--database-url",
            "postgresql://unit.invalid/brc",
            "--as-of-ms",
            "1800000000000",
        ]
    )

    assert args.database_url == "postgresql://unit.invalid/brc"
    assert args.as_of_ms == 1_800_000_000_000
    assert not hasattr(args, "output")
    assert not hasattr(args, "output_dir")
    assert args.max_workers == 4


def test_required_public_series_cover_22_scopes_without_duplicate_fetches() -> None:
    module = _load_module()

    series = module._required_candle_series(_scopes())

    assert len(series) == 16
    assert ("BTCUSDT", "15m") in series
    assert ("BTCUSDT", "1h") in series
    assert ("BTCUSDT", "4h") in series
    assert ("OPUSDT", "1h") in series
    assert ("OPUSDT", "4h") in series
    assert ("OPUSDT", "15m") not in series
