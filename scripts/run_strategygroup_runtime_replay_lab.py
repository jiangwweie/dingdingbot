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
    StrategyGroupReplayReport,
    build_mpg001_replay_lab_packet,
)


DEFAULT_OUTPUT_JSON = Path(
    "output/strategygroup-runtime-pilot/replay-lab/runtime-replay-report.json"
)
DEFAULT_OWNER_PROGRESS = Path(
    "output/strategygroup-runtime-pilot/replay-lab/runtime-replay-owner-progress.md"
)


def _owner_markdown(packet: StrategyGroupReplayReport) -> str:
    fixture_cases = ", ".join(
        sorted(item.fixture_case for item in packet.synthetic_fixtures)
    )
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
        f"- Post-submit simulator cases: {len(packet.post_submit_simulator_matrix)}",
        "- Cost review skeleton: present",
        f"- Synthetic fixtures: {fixture_cases}",
        "- Freqtrade: future sidecar research adapter only",
        "",
        "## Checks",
        "",
    ]
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
