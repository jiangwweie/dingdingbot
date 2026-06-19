#!/usr/bin/env python3
"""Run the local StrategyGroup runtime replay lab.

This script is intentionally local-only. It writes a replay report for Owner
review and dry-run audit input, but it does not call Tokyo, FinalGate,
Operation Layer, exchange write, or any real-order path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.strategygroup_runtime_replay import (  # noqa: E402
    ReplayReviewRecommendation,
    StrategyGroupReplayReport,
    build_mpg001_replay_lab_packet,
)


DEFAULT_OUTPUT_JSON = Path(
    "output/strategygroup-runtime-pilot/replay-lab/runtime-replay-report.json"
)
DEFAULT_OWNER_PROGRESS = Path(
    "output/strategygroup-runtime-pilot/replay-lab/runtime-replay-owner-progress.md"
)


def _count_review_signals(items: list[object]) -> int:
    return sum(
        1
        for item in items
        if getattr(item, "required_facts_ready")
        and getattr(item, "signal_status") not in {"no_signal", "stale_signal"}
        and getattr(item, "blocker_class") != "waiting_for_market"
    )


def _count_quiet(items: list[object]) -> int:
    return sum(
        1
        for item in items
        if getattr(item, "signal_status") == "no_signal"
        or getattr(item, "blocker_class") == "waiting_for_market"
    )


def _count_revise(items: list[object]) -> int:
    return sum(
        1
        for item in items
        if getattr(item, "review_recommendation") == ReplayReviewRecommendation.REVISE
    )


def _strategygroup_replay_review_rows(
    packet: StrategyGroupReplayReport,
) -> list[dict[str, object]]:
    groups = [
        (
            "MPG-001",
            "L4 replay baseline",
            packet.replay_samples,
            "dry-run only; live order still requires real fresh signal and official chain",
        ),
        (
            "BTPC-001",
            "L2 shadow",
            packet.l2_shadow_replay_samples,
            "shadow evidence only; no Operation Layer",
        ),
        (
            "BRF-001",
            "L1 observe",
            [
                item
                for item in packet.l1_observe_replay_samples
                if item.strategy_group_id == "BRF-001"
            ],
            "observe-only; no prepare chain",
        ),
        (
            "VCB-001",
            "L1 observe",
            [
                item
                for item in packet.l1_observe_replay_samples
                if item.strategy_group_id == "VCB-001"
            ],
            "observe-only; no prepare chain",
        ),
        (
            "LSR-001",
            "L1 observe",
            [
                item
                for item in packet.l1_observe_replay_samples
                if item.strategy_group_id == "LSR-001"
            ],
            "observe-only; no prepare chain",
        ),
    ]
    return [
        {
            "strategy_group_id": strategy_group_id,
            "layer": layer,
            "samples": len(items),
            "review_signals": _count_review_signals(items),
            "quiet_no_action": _count_quiet(items),
            "revise": _count_revise(items),
            "boundary": boundary,
        }
        for strategy_group_id, layer, items, boundary in groups
    ]


def _owner_markdown(packet: StrategyGroupReplayReport) -> str:
    fixture_cases = ", ".join(
        sorted(item.fixture_case for item in packet.synthetic_fixtures)
    )
    review_rows = _strategygroup_replay_review_rows(packet)
    lines = [
        "## Runtime Replay Lab",
        "",
        f"- 当前阶段: {packet.owner_summary.current_state}",
        "- 当前动作: 本地 replay / synthetic 演练",
        "- Owner 介入: 否",
        "- 服务器修改: 否",
        "- 接近真实订单: 否",
        "- Exchange write: 否",
        "",
        "## Coverage",
        "",
        f"- StrategyGroup: {packet.strategy_group_id}",
        f"- Replay samples: {len(packet.replay_samples)}",
        f"- L2 shadow replay samples: {len(packet.l2_shadow_replay_samples)}",
        f"- L1 observe replay samples: {len(packet.l1_observe_replay_samples)}",
        f"- Post-submit simulator cases: {len(packet.post_submit_simulator_matrix)}",
        "- Cost review skeleton: present",
        f"- Synthetic fixtures: {fixture_cases}",
        "- Freqtrade: future sidecar research adapter only",
        "",
        "## StrategyGroup Replay Review",
        "",
        "| StrategyGroup | Layer | Samples | Review signals | Quiet / no-action | Revise | Boundary |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in review_rows:
        lines.append(
            "| "
            f"{row['strategy_group_id']} | "
            f"{row['layer']} | "
            f"{row['samples']} | "
            f"{row['review_signals']} | "
            f"{row['quiet_no_action']} | "
            f"{row['revise']} | "
            f"{row['boundary']} |"
        )
    lines.extend(
        [
            "",
            "## Checks",
            "",
        ]
    )
    for name, ok in sorted(packet.checks.items()):
        lines.append(f"- {name}: {'是' if ok else '否'}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Replay / synthetic signals are not live market signals.",
            "- This report does not authorize FinalGate, Operation Layer, exchange write, or real orders.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_packet() -> StrategyGroupReplayReport:
    return build_mpg001_replay_lab_packet(generated_at_ms=int(time.time() * 1000))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument(
        "--output-owner-progress", type=Path, default=DEFAULT_OWNER_PROGRESS
    )
    args = parser.parse_args()

    packet = build_packet()
    payload = packet.model_dump(mode="json")
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_owner_progress.parent.mkdir(parents=True, exist_ok=True)
    args.output_owner_progress.write_text(_owner_markdown(packet), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
