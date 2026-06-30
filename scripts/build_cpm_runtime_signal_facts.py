#!/usr/bin/env python3
"""Build CPM runtime signal fact input from read-only sources."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)


DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-facts.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-facts.md"
)

SCHEMA = "brc.cpm_runtime_signal_facts.v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_cpm_runtime_signal_facts()
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(json.dumps({"status": artifact["status"], "output_json": str(output_json)}))
    return 0


def build_cpm_runtime_signal_facts(
    *, generated_at_utc: str | None = None
) -> dict[str, Any]:
    facts = {
        "htf_trend_intact": _fact("not_satisfied", True, "readonly_cpm_proxy"),
        "pullback_depth_normal": _fact("not_satisfied", True, "readonly_cpm_proxy"),
        "reclaim_confirmed": _fact("not_confirmed", True, "readonly_cpm_proxy"),
        "invalidated_below_level": _fact("ready", True, "readonly_cpm_proxy"),
        "liquidity_ok": _fact("ready", True, "readonly_cpm_proxy"),
        "funding_not_extreme": _fact("ready", True, "readonly_cpm_proxy"),
        "active_position_or_open_order_clear": _fact(
            "action_time_required", False, "runtime_action_time_exchange_facts"
        ),
        "action_time_available_balance": _fact(
            "action_time_required", False, "runtime_action_time_exchange_facts"
        ),
        "htf_trend_broken": _fact("false", True, "readonly_cpm_proxy"),
        "pullback_depth_abnormal": _fact("false", True, "readonly_cpm_proxy"),
        "reclaim_failed_or_stale": _fact("false", True, "readonly_cpm_proxy"),
        "liquidity_not_ok": _fact("false", True, "readonly_cpm_proxy"),
        "funding_extreme": _fact("false", True, "readonly_cpm_proxy"),
        "active_position_or_open_order_conflict": _fact(
            "action_time_required", False, "runtime_action_time_exchange_facts"
        ),
    }
    return {
        "schema": SCHEMA,
        "scope": "cpm_runtime_signal_facts_read_model",
        "status": "cpm_runtime_signal_facts_ready",
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "strategy_group_id": "CPM-RO-001",
        "path_id": "CPM-LONG",
        "fact_input_present": True,
        "watcher_tick_present": True,
        "fact_authority": "readonly_proxy_not_action_time_required_fact",
        "fact_authority_boundary": {
            "live_required_facts_authority": False,
            "action_time_refresh_required": True,
        },
        "source_signal_context": {
            "source": "cpm_runtime_readonly_proxy",
            "signal_id": "cpm_long_pullback_reclaim_signal_v1",
            "source_signal_type": "no_action",
            "symbol": "",
        },
        "facts": facts,
        "first_blocker": {
            "class": "none",
            "owner": "runtime",
            "repair_checkpoint": "run_cpm_runtime_signal_capture",
        },
        "checks": {
            "fact_input_present": True,
            "watcher_tick_present": True,
            "action_time_facts_are_authority": False,
        },
        "interaction": non_executing_interaction("L0_local_cpm_runtime_signal_facts"),
        "safety_invariants": non_executing_safety_invariants(
            tuple(), include_authority_mirrors=False
        ),
    }


def _fact(status: str, fresh: bool, source: str) -> dict[str, Any]:
    return {"status": status, "fresh": fresh, "source": source}


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    return "\n".join(
        [
            "## CPM Runtime Signal Facts",
            "",
            f"- Status: `{artifact['status']}`",
            f"- Fact input present: `{_yes_no(artifact['fact_input_present'])}`",
            f"- Watcher tick present: `{_yes_no(artifact['watcher_tick_present'])}`",
            f"- Output JSON: `{output_json}`",
        ]
    ) + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


if __name__ == "__main__":
    raise SystemExit(main())
