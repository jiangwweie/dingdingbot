#!/usr/bin/env python3
"""Build BRF2 runtime signal fact input from watcher/read-only sources.

This artifact is the boundary between runtime observation and BRF2 signal
capture. It is intentionally read-only: it does not fetch exchange data, call
FinalGate, call Operation Layer, create authorization evidence, or place orders.
When no BRF2 watcher fact source exists, it records that engineering gap instead
of letting signal capture misclassify missing facts as a market wait.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-live-market-strategy-preview.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-facts.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-facts.md"
)

SCHEMA = "brc.brf2_runtime_signal_facts.v1"
READY_STATUS = "brf2_runtime_signal_facts_ready"
MISSING_STATUS = "brf2_runtime_signal_facts_missing_watcher_input"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", default=str(DEFAULT_SOURCE_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    packet = build_brf2_runtime_signal_facts(
        source_packet=_read_optional_json(Path(args.source_json)),
        source_path=Path(args.source_json),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, packet)
    _write_text(output_md, _markdown(packet, output_json))
    print(
        json.dumps(
            {
                "status": packet["status"],
                "strategy_group_id": packet["strategy_group_id"],
                "fact_input_present": packet["fact_input_present"],
                "watcher_tick_present": packet["watcher_tick_present"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_brf2_runtime_signal_facts(
    *,
    source_packet: dict[str, Any],
    source_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    explicit_facts = _explicit_brf2_facts(source_packet)
    source_row = _source_brf2_row(source_packet)
    fact_input_present = bool(explicit_facts)
    watcher_tick_present = fact_input_present or bool(source_row)
    first_blocker = (
        {
            "class": "none",
            "owner": "runtime",
            "next_action": "run_brf2_runtime_signal_capture",
        }
        if fact_input_present
        else {
            "class": "brf2_watcher_fact_input_missing",
            "owner": "engineering",
            "next_action": "attach_brf2_watcher_fact_input_producer",
        }
    )
    return {
        "schema": SCHEMA,
        "scope": "brf2_runtime_signal_facts_read_model",
        "status": READY_STATUS if fact_input_present else MISSING_STATUS,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "strategy_group_id": "BRF2-001",
        "fact_input_present": fact_input_present,
        "watcher_tick_present": watcher_tick_present,
        "source_status": str(source_packet.get("status") or "missing"),
        "source_path": str(source_path or ""),
        "source_signal_context": _signal_context(explicit_facts, source_row),
        "facts": _facts(explicit_facts),
        "first_blocker": first_blocker,
        "next_action": first_blocker["next_action"],
        "checks": {
            "fact_input_present": fact_input_present,
            "watcher_tick_present": watcher_tick_present,
            "brf2_source_row_present": bool(source_row),
            "missing_watcher_input": not fact_input_present,
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _explicit_brf2_facts(packet: dict[str, Any]) -> dict[str, Any]:
    direct = _as_dict(packet.get("brf2_runtime_signal_facts"))
    if direct:
        return direct
    if packet.get("strategy_group_id") == "BRF2-001" and _as_dict(packet.get("facts")):
        return packet
    return {}


def _source_brf2_row(packet: dict[str, Any]) -> dict[str, Any]:
    for key in ("would_enter_signals", "no_action_signals", "current_signals"):
        for row in packet.get(key) or []:
            item = _as_dict(row)
            if item.get("strategy_group_id") == "BRF2-001":
                return item
    preview = _as_dict(packet.get("preview"))
    for row in preview.get("candidates") or []:
        item = _as_dict(row)
        if item.get("strategy_group_id") == "BRF2-001":
            return item
    return {}


def _facts(packet: dict[str, Any]) -> dict[str, Any]:
    facts = _as_dict(packet.get("facts"))
    return {str(key): _as_dict(value) for key, value in facts.items()}


def _signal_context(packet: dict[str, Any], source_row: dict[str, Any]) -> dict[str, str]:
    context = _as_dict(packet.get("signal_context"))
    return {
        "signal_packet_id": str(context.get("signal_packet_id") or ""),
        "runtime_instance_id": str(context.get("runtime_instance_id") or ""),
        "symbol": str(
            context.get("symbol")
            or packet.get("symbol")
            or source_row.get("symbol")
            or ""
        ),
        "exchange_symbol": str(context.get("exchange_symbol") or ""),
        "market": str(context.get("market") or ""),
        "timeframe": str(context.get("timeframe") or ""),
        "closed_at_utc": str(context.get("closed_at_utc") or ""),
        "source": str(
            context.get("source") or "brf2_runtime_signal_facts_read_model"
        ),
    }


def _markdown(packet: dict[str, Any], output_json: Path) -> str:
    first_blocker = _as_dict(packet.get("first_blocker"))
    lines = [
        "## BRF2 Runtime Signal Facts",
        "",
        f"- Status: `{packet['status']}`",
        f"- Generated: `{packet['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- Fact input present: `{_yes_no(packet['fact_input_present'])}`",
        f"- Watcher tick present: `{_yes_no(packet['watcher_tick_present'])}`",
        f"- First blocker: `{first_blocker.get('class', 'missing')}` / `{first_blocker.get('owner', 'unknown')}`",
        "",
        "## Boundary",
        "",
        "- This packet is local/read-only and non-executing.",
        "- Missing watcher fact input is an engineering gap, not a market signal absence.",
        "- It does not call FinalGate, Operation Layer, exchange write, or order creation.",
    ]
    return "\n".join(lines) + "\n"


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_brf2_runtime_signal_facts",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def _safety_invariants() -> dict[str, bool]:
    return {
        "actionable_now": False,
        "real_order_authority": False,
        "authorization_evidence_created": False,
        "execution_intent_created": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "withdrawal_or_transfer_created": False,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


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
