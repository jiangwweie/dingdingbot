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
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
READONLY_PROXY_FACT_AUTHORITY = "readonly_proxy_not_action_time_required_fact"
RUNTIME_READONLY_FACT_AUTHORITY = "runtime_watcher_readonly_not_action_time_required_fact"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json")
    parser.add_argument(
        "--strategy-source",
        choices=["sample", "local_sqlite_fallback", "live_market"],
        default="local_sqlite_fallback",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    source_packet, source_path = _load_source_packet(
        source_json=args.source_json,
        strategy_source=args.strategy_source,
    )
    packet = build_brf2_runtime_signal_facts(
        source_packet=source_packet,
        source_path=source_path,
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
    derived_facts = _derived_brf2_facts(source_row)
    fact_packet = explicit_facts or derived_facts
    fact_input_present = bool(fact_packet)
    watcher_tick_present = fact_input_present or bool(source_row)
    source_is_brf_reference_row = _is_brf_reference_row(source_row)
    fact_authority = _fact_authority(
        fact_packet=fact_packet,
        source_is_brf_reference_row=source_is_brf_reference_row,
    )
    source_signal_context = _signal_context(fact_packet, source_row)
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
        "source_signal_context": source_signal_context,
        "signal_context": source_signal_context,
        "fact_authority": fact_authority,
        "fact_authority_boundary": _fact_authority_boundary(
            fact_authority=fact_authority,
            source_is_brf_reference_row=source_is_brf_reference_row,
        ),
        "facts": _facts(fact_packet),
        "first_blocker": first_blocker,
        "next_action": first_blocker["next_action"],
        "checks": {
            "fact_input_present": fact_input_present,
            "watcher_tick_present": watcher_tick_present,
            "brf2_source_row_present": bool(source_row),
            "source_strategy_group_id": str(source_row.get("strategy_group_id") or ""),
            "source_is_brf_reference_row": source_is_brf_reference_row,
            "missing_watcher_input": not fact_input_present,
            "actionable_now": False,
            "real_order_authority": False,
            "action_time_required_facts_satisfied": False,
            "derived_proxy_not_action_time_authority": (
                fact_authority == READONLY_PROXY_FACT_AUTHORITY
            ),
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
    preview = _as_dict(packet.get("preview"))
    for key in ("current_signals", "signal_history"):
        for row in preview.get(key) or []:
            item = _as_dict(row)
            if _is_brf2_or_brf_source_row(item):
                return item
    for key in (
        "would_enter_signals",
        "no_action_signals",
        "invalid_signals",
        "current_signals",
        "high_priority_no_action_signals",
    ):
        for row in packet.get(key) or []:
            item = _as_dict(row)
            if _is_brf2_or_brf_source_row(item):
                return item
    for row in preview.get("candidates") or []:
        item = _as_dict(row)
        if _is_brf2_or_brf_source_row(item):
            return item
    return {}


def _is_brf2_or_brf_source_row(row: dict[str, Any]) -> bool:
    strategy_group_id = str(row.get("strategy_group_id") or "")
    if strategy_group_id == "BRF2-001":
        return True
    return _is_brf_reference_row(row)


def _is_brf_reference_row(row: dict[str, Any]) -> bool:
    return (
        str(row.get("strategy_group_id") or "") == "BRF-001"
        and str(row.get("side") or "").lower() in {"short", "none", ""}
    )


def _facts(packet: dict[str, Any]) -> dict[str, Any]:
    facts = _as_dict(packet.get("facts"))
    return {str(key): _as_dict(value) for key, value in facts.items()}


def _derived_brf2_facts(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    evidence = _as_dict(row.get("evidence_payload"))
    preview = _as_dict(row.get("latest_signal_preview"))
    signal_input = _as_dict(row.get("signal_input_snapshot"))
    market_snapshot = _as_dict(signal_input.get("market_snapshot"))
    candle_context = _as_dict(market_snapshot.get("candle_context"))
    windows = _as_dict(candle_context.get("windows"))
    one_hour = _list_of_dicts(windows.get("1h"))
    five_minute = _list_of_dicts(windows.get("5m"))
    price_action = _as_dict(evidence.get("price_action_structure"))
    squeeze = _as_dict(evidence.get("short_squeeze_risk"))
    reason_codes = [str(value) for value in row.get("reason_codes") or []]
    signal_type = str(row.get("signal_type") or preview.get("signal_type") or "")
    htf_context = str(evidence.get("htf_context") or "").lower()
    rally_extension = evidence.get("rally_extension_confirmed") is True
    rejection = evidence.get("rejection_confirmed") is True or signal_type == "would_enter"
    squeeze_warning = squeeze.get("squeeze_warning") is True
    volume_present = _latest_volume_present(one_hour) or _latest_volume_present(five_minute)

    facts = {
        "closed_1h_ohlcv": _fact(
            status="ready" if one_hour or price_action.get("closed_bar") is True else "missing",
            fresh=bool(one_hour or price_action.get("closed_bar") is True),
            source="strategy_group_readonly_observation_preview",
            detail={
                "timeframe": "1h",
                "closed_bar": price_action.get("closed_bar", True),
                "latest_open_time_ms": _latest_open_time_ms(one_hour)
                or row.get("market_bar_timestamp_ms")
                or evidence.get("latest_1h_open_time_ms"),
            },
        ),
        "closed_5m_ohlcv": _closed_5m_fact(five_minute, row),
        "rally_context": _fact(
            status=(
                "bear_or_weak_reclaim"
                if rally_extension and htf_context != "strong_uptrend"
                else "not_satisfied"
            ),
            fresh=True,
            source="brf_price_action_evaluator_evidence",
            detail={
                "htf_context": htf_context,
                "rally_extension_confirmed": rally_extension,
                "rally_pct": price_action.get("rally_pct"),
            },
        ),
        "rally_failure_trigger_state": _fact(
            status="confirmed" if rejection else "not_confirmed",
            fresh=True,
            source="brf_price_action_evaluator_evidence",
            detail={
                "signal_type": signal_type,
                "rejection_confirmed": rejection,
                "reason_codes": reason_codes,
                "close_reversal_pct": price_action.get("close_reversal_pct"),
                "rejection_upper_wick_ratio": price_action.get(
                    "rejection_upper_wick_ratio"
                ),
            },
        ),
        "short_squeeze_risk_state": _fact(
            status="bounded" if not squeeze_warning else "red",
            fresh=True,
            source="brf_short_squeeze_review_proxy",
            detail=squeeze,
        ),
        "strong_reclaim_disable_state": _fact(
            status="true" if htf_context == "strong_uptrend" else "false",
            fresh=True,
            source="brf_price_action_evaluator_evidence",
            detail={"htf_context": htf_context},
        ),
        "rally_extension_invalidates_failure_state": _fact(
            status="false" if not squeeze_warning else "active",
            fresh=True,
            source="brf_price_action_evaluator_evidence",
            detail={"squeeze_warning": squeeze_warning},
        ),
        "liquidity_downshift_state": _fact(
            status="false" if volume_present else "unknown",
            fresh=True,
            source="closed_candle_volume_proxy",
            detail={"volume_present": volume_present},
        ),
        "spread_liquidity_state": _fact(
            status="acceptable" if volume_present else "unknown",
            fresh=True,
            source="closed_candle_volume_proxy",
            detail={
                "volume_present": volume_present,
                "bid_ask_spread": market_snapshot.get("bid_ask_spread"),
            },
        ),
    }
    return {
        "strategy_group_id": "BRF2-001",
        "signal_context": _derived_signal_context(row),
        "facts": facts,
    }


def _closed_5m_fact(five_minute: list[dict[str, Any]], row: dict[str, Any]) -> dict[str, Any]:
    if five_minute:
        return _fact(
            status="ready",
            fresh=True,
            source="strategy_group_readonly_observation_preview",
            detail={
                "timeframe": "5m",
                "latest_open_time_ms": _latest_open_time_ms(five_minute),
            },
        )
    return _fact(
        status="ready",
        fresh=True,
        source="strategy_group_readonly_observation_tick_proxy",
        detail={
            "timeframe": "5m",
            "proxy_source": "latest_closed_strategy_observation_tick",
            "authority": READONLY_PROXY_FACT_AUTHORITY,
            "proxy_is_not_action_time_live_required_fact": True,
            "market_bar_timestamp_ms": row.get("market_bar_timestamp_ms"),
        },
    )


def _fact_authority(
    *,
    fact_packet: dict[str, Any],
    source_is_brf_reference_row: bool,
) -> str:
    if not fact_packet:
        return ""
    if source_is_brf_reference_row:
        return READONLY_PROXY_FACT_AUTHORITY
    return str(fact_packet.get("fact_authority") or RUNTIME_READONLY_FACT_AUTHORITY)


def _fact_authority_boundary(
    *,
    fact_authority: str,
    source_is_brf_reference_row: bool,
) -> dict[str, Any]:
    if not fact_authority:
        return {
            "action_time_required_facts_satisfied": False,
            "usable_for_armed_observation": False,
            "usable_for_finalgate": False,
            "usable_for_operation_layer": False,
            "usable_for_exchange_write": False,
        }
    return {
        "fact_authority": fact_authority,
        "source_is_brf_reference_row": source_is_brf_reference_row,
        "usable_for_armed_observation": True,
        "usable_for_market_wait_classification": True,
        "action_time_required_facts_satisfied": False,
        "usable_for_finalgate": False,
        "usable_for_operation_layer": False,
        "usable_for_exchange_write": False,
        "notes": (
            "BRF reference rows are read-only observation proxies; action-time "
            "RequiredFacts must be rebuilt from live runtime/exchange facts."
            if source_is_brf_reference_row
            else "Runtime read-only facts can arm observation but do not satisfy action-time submit authority."
        ),
    }


def _fact(
    *,
    status: str,
    fresh: bool,
    source: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "fresh": fresh,
        "source": source,
        "detail": detail or {},
    }


def _derived_signal_context(row: dict[str, Any]) -> dict[str, Any]:
    timestamp_ms = _int(row.get("market_bar_timestamp_ms") or row.get("evaluated_at_ms"))
    closed_at = (
        datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc).isoformat()
        if timestamp_ms > 0
        else ""
    )
    return {
        "signal_packet_id": str(
            row.get("record_id")
            or row.get("candidate_id")
            or f"brf2-derived:{timestamp_ms}"
        ),
        "runtime_instance_id": "",
        "symbol": str(row.get("symbol") or ""),
        "exchange_symbol": str(row.get("symbol") or ""),
        "market": "binance_usdm",
        "timeframe": "1h_closed_observation_with_5m_proxy",
        "closed_at_utc": closed_at,
        "source": "brf_reference_readonly_preview_derived_brf2_fact_input",
        "source_strategy_group_id": str(row.get("strategy_group_id") or ""),
        "source_candidate_id": str(row.get("candidate_id") or ""),
        "source_signal_type": str(row.get("signal_type") or ""),
    }


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
        "source_strategy_group_id": str(
            context.get("source_strategy_group_id")
            or source_row.get("strategy_group_id")
            or ""
        ),
        "source_candidate_id": str(
            context.get("source_candidate_id") or source_row.get("candidate_id") or ""
        ),
        "source_signal_type": str(
            context.get("source_signal_type") or source_row.get("signal_type") or ""
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
        f"- Fact authority: `{packet.get('fact_authority') or 'none'}`",
        "- Action-time RequiredFacts satisfied: `否`",
        "",
        "## Boundary",
        "",
        "- This packet is local/read-only and non-executing.",
        "- BRF reference derived facts are observation proxies, not action-time live RequiredFacts.",
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


def _load_source_packet(
    *,
    source_json: str | None,
    strategy_source: str,
) -> tuple[dict[str, Any], Path | None]:
    if source_json:
        path = Path(source_json)
        return _read_optional_json(path), path
    try:
        from scripts.preview_strategy_group_readonly_observation import (
            build_preview_packet,
        )

        packet = build_preview_packet(source_name=strategy_source)  # type: ignore[arg-type]
        return packet, Path(f"generated:{strategy_source}:strategy_group_preview")
    except Exception as exc:
        return {
            "status": "preview_source_unavailable",
            "source_error": type(exc).__name__,
            "source_error_message": str(exc),
        }, Path(f"generated:{strategy_source}:unavailable")


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


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _latest_open_time_ms(rows: list[dict[str, Any]]) -> Any:
    if not rows:
        return None
    return rows[-1].get("open_time_ms") or rows[-1].get("timestamp")


def _latest_volume_present(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    value = rows[-1].get("volume")
    try:
        return float(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
