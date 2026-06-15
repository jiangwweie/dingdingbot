#!/usr/bin/env python3
"""Plan or execute StrategyGroup runtime pilot bootstrap.

This script bridges the Owner-facing StrategyGroup picker to the existing
official runtime bootstrap API flow. Default mode is plan-only. With
``--execute`` it may create StrategyFamily / Admission / TrialBinding /
shadow StrategyRuntimeInstance records through official API surfaces. It never
creates candidates, ExecutionIntents, orders, withdrawals, transfers, or
exchange submit actions.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
import shlex
import sys
import time
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.build_strategy_group_handoff_intake_packet import (  # noqa: E402
    DEFAULT_HANDOFF_DIR,
    build_packet as build_handoff_intake_packet,
)
from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    DEFAULT_API_BASE,
    UrlLibApiClient,
)
from scripts.runtime_live_bootstrap_api_flow import (  # noqa: E402
    BootstrapConfig,
    RuntimeLiveBootstrapApiFlow,
)


DEFAULT_OUTPUT_JSON = (
    ROOT_DIR / "output/strategygroup-runtime-pilot/runtime-bootstrap-packet.json"
)
DEFAULT_PLAYBOOK_ID = "PB-BRC-STRATEGYGROUP-RUNTIME-PILOT-V1"
DEFAULT_MAX_SYMBOLS_PER_GROUP = 1
DEFAULT_MAX_TOTAL_NEW_RUNTIMES = 4
BOOTSTRAPPABLE_INTAKE_STATUSES = {
    "armed_observation_intake_ready",
    "conditional_armed_observation_intake_ready",
}
BOOTSTRAPPABLE_DEFAULT_MODES = {
    "armed_observation",
    "conditional_armed_observation",
}
FORBIDDEN_EFFECT_FLAGS = {
    "creates_order_candidate",
    "creates_execution_intent",
    "creates_order",
    "calls_exchange_submit",
    "withdrawal_or_transfer_created",
}


@dataclass(frozen=True)
class RuntimePilotBootstrapConfig:
    api_base: str = DEFAULT_API_BASE
    execute: bool = False
    strategy_group_ids: tuple[str, ...] = ()
    include_observe_only: bool = False
    max_symbols_per_group: int = DEFAULT_MAX_SYMBOLS_PER_GROUP
    max_total_new_runtimes: int = DEFAULT_MAX_TOTAL_NEW_RUNTIMES
    account_facts_source: str = "binance_readonly"
    account_facts_json: str | None = None
    owner_operator_id: str = "owner-standing-authorization"
    playbook_id: str = DEFAULT_PLAYBOOK_ID
    output_json: str | None = None


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _load_env_file(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value).expanduser()
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(raw_value, comments=False, posix=True)
        except ValueError:
            parsed = []
        value = parsed[0] if len(parsed) == 1 else raw_value.strip().strip("\"'")
        if value and not os.environ.get(key):
            os.environ[key] = value


def _list_active_runtimes(client: Any) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        response = client.request_json("GET", "/api/trading-console/strategy-runtimes")
    except Exception as exc:
        return [], [f"active_runtime_inventory_unavailable:{type(exc).__name__}"]
    body = response.get("body")
    if response.get("http_status", 0) >= 300 or response.get("error"):
        return [], [f"active_runtime_inventory_http_{response.get('http_status')}"]
    items = body if isinstance(body, list) else (body or {}).get("items", [])
    if not isinstance(items, list):
        return [], ["active_runtime_inventory_response_not_list"]
    active = [
        item
        for item in items
        if isinstance(item, dict)
        and str(item.get("status") or "").lower() == "active"
    ]
    return active, []


def _runtime_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = [
        payload.get("items"),
        payload.get("runtimes"),
        payload.get("runtime_summaries"),
        payload.get("runtime_signal_summaries"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("runtime_summaries"),
                data.get("runtime_signal_summaries"),
            ]
        )
        watcher = data.get("watcher")
        if isinstance(watcher, dict):
            candidates.append(watcher.get("runtime_signal_summaries"))
    status_packet = payload.get("status_packet")
    if isinstance(status_packet, dict):
        candidates.extend(
            [
                status_packet.get("runtime_summaries"),
                status_packet.get("runtime_signal_summaries"),
            ]
        )
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _exchange_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip().upper()
    if not text:
        return ""
    return text.replace("/", "").replace(":USDT", "")


def _runtime_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip()
    if not text:
        return ""
    if "/" in text:
        return text
    upper = text.upper()
    if upper.endswith("USDT"):
        return f"{upper[:-4]}/USDT:USDT"
    return text


def _safe_id(value: str) -> str:
    return (
        value.lower()
        .replace("/", "-")
        .replace(":", "-")
        .replace("_", "-")
        .replace(" ", "-")
    )


def _group_id(row: dict[str, Any]) -> str:
    return str(row.get("strategy_group_id") or "").strip()


def _side(group: dict[str, Any]) -> str:
    rule = group.get("signal_ready_rule")
    if isinstance(rule, dict):
        side = str(rule.get("side") or "").strip().lower()
        if side in {"long", "short"}:
            return side
    for item in group.get("supported_sides") or []:
        side = str(item).strip().lower()
        if side in {"long", "short"}:
            return side
    return "long"


def _decimal_from(value: Any, default: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _readiness_by_group(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("strategy_group_id")): item
        for item in packet.get("readiness") or []
        if isinstance(item, dict) and item.get("strategy_group_id")
    }


def _active_key(runtime: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(runtime.get("strategy_family_id") or runtime.get("family") or ""),
        _exchange_symbol(runtime.get("symbol")),
        str(runtime.get("side") or "").lower(),
    )


def _active_groups(active_runtimes: list[dict[str, Any]]) -> set[str]:
    return {
        str(runtime.get("strategy_family_id") or runtime.get("family") or "")
        for runtime in active_runtimes
        if runtime.get("strategy_family_id") or runtime.get("family")
    }


def _is_bootstrappable_group(
    group: dict[str, Any],
    *,
    include_observe_only: bool,
    selected_ids: set[str],
) -> tuple[bool, str]:
    strategy_group_id = _group_id(group)
    if selected_ids and strategy_group_id not in selected_ids:
        return False, "not_selected"
    picker = group.get("picker") if isinstance(group.get("picker"), dict) else {}
    default_mode = str(picker.get("default_mode") or "").strip()
    intake_status = str(group.get("intake_status") or "").strip()
    if include_observe_only:
        return True, "selected"
    if (
        intake_status in BOOTSTRAPPABLE_INTAKE_STATUSES
        or default_mode in BOOTSTRAPPABLE_DEFAULT_MODES
    ):
        return True, "selected"
    return False, f"mode_not_bootstrappable:{default_mode or intake_status or 'unknown'}"


def _ready_symbols(
    *,
    group: dict[str, Any],
    readiness: dict[str, Any] | None,
) -> list[str]:
    if readiness:
        exchange_rules = readiness.get("exchange_rules")
        if isinstance(exchange_rules, dict):
            symbols = [
                _exchange_symbol(item)
                for item in exchange_rules.get("ready_symbols") or []
            ]
            if symbols:
                return [item for item in symbols if item]
    return [_exchange_symbol(item) for item in group.get("supported_symbols") or [] if item]


def _bootstrap_config(
    *,
    config: RuntimePilotBootstrapConfig,
    group: dict[str, Any],
    symbol: str,
    side: str,
) -> BootstrapConfig:
    strategy_group_id = _group_id(group)
    risk_defaults = (
        group.get("risk_defaults") if isinstance(group.get("risk_defaults"), dict) else {}
    )
    max_notional = _decimal_from(
        risk_defaults.get("max_notional_per_action_usdt")
        or risk_defaults.get("max_notional_usdt"),
        "8",
    )
    max_leverage = int(_decimal_from(risk_defaults.get("max_leverage"), "1"))
    supported_symbols = [
        _runtime_symbol(item)
        for item in group.get("supported_symbols") or []
        if _runtime_symbol(item)
    ]
    runtime_symbol = _runtime_symbol(symbol)
    return BootstrapConfig(
        api_base=config.api_base,
        mode="bootstrap",
        strategy_family_id=strategy_group_id,
        strategy_family_version_id=f"{strategy_group_id}-v0",
        family_key=f"{strategy_group_id.lower()}-strategygroup-pilot",
        family_name=str(group.get("name") or strategy_group_id),
        symbol=runtime_symbol,
        supported_symbols=supported_symbols,
        side=side,
        capital_base=Decimal("30"),
        max_loss_budget=Decimal("9"),
        max_notional=max_notional,
        max_leverage=max_leverage,
        max_attempts=3,
        playbook_id=config.playbook_id,
        account_facts_source=config.account_facts_source,
        account_facts_json=config.account_facts_json,
        owner_operator_id=config.owner_operator_id,
        runtime_carrier_id=(
            f"strategygroup-runtime-pilot:{strategy_group_id}:"
            f"{_safe_id(runtime_symbol)}:{side}"
        ),
        reason=(
            "Owner standing-authorized StrategyGroup runtime pilot bootstrap; "
            "creates observation runtime only, not order authority."
        ),
    )


def _target_row(
    *,
    group: dict[str, Any],
    symbol: str,
    side: str,
    readiness: dict[str, Any] | None,
    status: str,
    reason: str,
    runtime_instance_id: str | None = None,
) -> dict[str, Any]:
    strategy_group_id = _group_id(group)
    picker = group.get("picker") if isinstance(group.get("picker"), dict) else {}
    return {
        "strategy_group_id": strategy_group_id,
        "strategy_family_version_id": f"{strategy_group_id}-v0",
        "symbol": _runtime_symbol(symbol),
        "exchange_symbol": _exchange_symbol(symbol),
        "side": side,
        "picker_rank": picker.get("rank"),
        "default_mode": picker.get("default_mode"),
        "readiness_status": (
            readiness.get("readiness_status") if isinstance(readiness, dict) else None
        ),
        "status": status,
        "reason": reason,
        "runtime_instance_id": runtime_instance_id,
    }


def build_packet(
    *,
    config: RuntimePilotBootstrapConfig,
    intake_packet: dict[str, Any],
    live_facts_readiness: dict[str, Any],
    active_runtimes: list[dict[str, Any]],
    active_inventory_blockers: list[str] | None = None,
    active_inventory_counts: dict[str, Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    generated_at_ms = int(time.time() * 1000)
    selected_ids = {item.strip() for item in config.strategy_group_ids if item.strip()}
    readiness_map = _readiness_by_group(live_facts_readiness)
    active_keys = {_active_key(runtime) for runtime in active_runtimes}
    active_group_ids = _active_groups(active_runtimes)
    blockers = list(active_inventory_blockers or [])
    targets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    new_runtime_ids: list[str] = []
    total_new = 0

    groups = [
        item for item in intake_packet.get("strategy_picker") or []
        if isinstance(item, dict)
    ]
    groups.sort(
        key=lambda item: (
            (item.get("picker") or {}).get("rank", 999),
            str(item.get("strategy_group_id") or ""),
        )
    )
    for group in groups:
        strategy_group_id = _group_id(group)
        selected, selected_reason = _is_bootstrappable_group(
            group,
            include_observe_only=config.include_observe_only,
            selected_ids=selected_ids,
        )
        side = _side(group)
        readiness = readiness_map.get(strategy_group_id)
        if not selected:
            skipped.append(
                _target_row(
                    group=group,
                    symbol=(group.get("supported_symbols") or [""])[0],
                    side=side,
                    readiness=readiness,
                    status="skipped",
                    reason=selected_reason,
                )
            )
            continue
        if not readiness or not bool(readiness.get("observe_ready")):
            skipped.append(
                _target_row(
                    group=group,
                    symbol=(group.get("supported_symbols") or [""])[0],
                    side=side,
                    readiness=readiness,
                    status="blocked",
                    reason="strategy_group_observe_readiness_not_ready",
                )
            )
            continue
        if strategy_group_id in active_group_ids and not selected_ids:
            skipped.append(
                _target_row(
                    group=group,
                    symbol=(group.get("supported_symbols") or [""])[0],
                    side=side,
                    readiness=readiness,
                    status="skipped",
                    reason="strategy_group_already_has_active_runtime",
                )
            )
            continue
        selected_symbols = _ready_symbols(group=group, readiness=readiness)[
            : max(config.max_symbols_per_group, 0)
        ]
        if not selected_symbols:
            skipped.append(
                _target_row(
                    group=group,
                    symbol=(group.get("supported_symbols") or [""])[0],
                    side=side,
                    readiness=readiness,
                    status="blocked",
                    reason="no_exchange_ready_symbols",
                )
            )
            continue
        for symbol in selected_symbols:
            key = (strategy_group_id, _exchange_symbol(symbol), side)
            if key in active_keys:
                skipped.append(
                    _target_row(
                        group=group,
                        symbol=symbol,
                        side=side,
                        readiness=readiness,
                        status="skipped",
                        reason="runtime_already_active_for_group_symbol_side",
                    )
                )
                continue
            if total_new >= config.max_total_new_runtimes:
                skipped.append(
                    _target_row(
                        group=group,
                        symbol=symbol,
                        side=side,
                        readiness=readiness,
                        status="skipped",
                        reason="max_total_new_runtimes_reached",
                    )
                )
                continue
            row = _target_row(
                group=group,
                symbol=symbol,
                side=side,
                readiness=readiness,
                status="planned",
                reason="ready_for_runtime_bootstrap",
            )
            targets.append(row)
            total_new += 1

    if config.execute and blockers:
        status = "blocked_active_runtime_inventory_unavailable"
    elif not targets and not blockers:
        status = "noop_runtime_bootstrap_not_needed"
    elif not config.execute:
        status = "planned_runtime_bootstrap"
    else:
        api_client = client or UrlLibApiClient(api_base=config.api_base)
        for target in targets:
            group = next(
                item for item in groups
                if _group_id(item) == target["strategy_group_id"]
            )
            flow = RuntimeLiveBootstrapApiFlow(
                client=api_client,
                config=_bootstrap_config(
                    config=config,
                    group=group,
                    symbol=target["exchange_symbol"],
                    side=target["side"],
                ),
            )
            report = flow.run()
            execution = {
                "target": target,
                "report": report,
                "blockers": list(report.get("blockers") or []),
                "ready_for_shadow_candidate_planning": bool(
                    report.get("ready_for_shadow_candidate_planning")
                ),
                "runtime_instance_id": (report.get("ids") or {}).get(
                    "runtime_instance_id"
                ),
                "runtime_status": (report.get("ids") or {}).get("runtime_status"),
                "safety": report.get("safety") or {},
            }
            executions.append(execution)
            if execution["runtime_instance_id"]:
                new_runtime_ids.append(str(execution["runtime_instance_id"]))
        execution_blockers = [
            f"{item['target']['strategy_group_id']}:{blocker}"
            for item in executions
            for blocker in item["blockers"]
        ]
        blockers.extend(execution_blockers)
        status = "executed_runtime_bootstrap" if not blockers else "blocked_runtime_bootstrap"

    selected_runtime_instance_ids = [
        str(runtime.get("runtime_instance_id") or runtime.get("runtime_id"))
        for runtime in active_runtimes
        if runtime.get("runtime_instance_id") or runtime.get("runtime_id")
    ] + new_runtime_ids
    return {
        "scope": "strategygroup_runtime_pilot_bootstrap",
        "status": status,
        "generated_at_ms": generated_at_ms,
        "mode": "execute" if config.execute else "plan",
        "standing_authorization_reference": (
            "OWNER_STANDING_AUTHORIZATION_STRATEGYGROUP_RUNTIME_PILOT_DEV_STAGE"
        ),
        "counts": {
            "strategy_groups_in_intake": len(groups),
            "active_runtime_rows_seen": len(active_runtimes),
            "active_runtime_count_reported": (
                (active_inventory_counts or {}).get("active_runtime_count")
            ),
            "monitored_runtime_count_reported": (
                (active_inventory_counts or {}).get("monitored_runtime_count")
            ),
            "targets": len(targets),
            "skipped": len(skipped),
            "executions": len(executions),
            "new_runtime_ids": len(new_runtime_ids),
        },
        "targets": targets,
        "skipped": skipped,
        "executions": executions,
        "runtime_scope": {
            "selected_runtime_instance_ids": selected_runtime_instance_ids,
            "new_runtime_instance_ids": new_runtime_ids,
            "watcher_scope_update_needed": bool(new_runtime_ids),
            "watcher_scope_note": (
                "The default systemd watcher monitors all ACTIVE runtimes when "
                "no --runtime-instance-id filter is present; server env/drop-in "
                "must be inspected if selected runtime count stays lower."
            ),
        },
        "operator_path": {
            "next_step": _next_step(status, bool(new_runtime_ids)),
            "can_start_or_continue_watcher_observation": (
                status in {
                    "planned_runtime_bootstrap",
                    "executed_runtime_bootstrap",
                    "noop_runtime_bootstrap_not_needed",
                }
            ),
            "requires_fresh_strategy_signal_before_candidate": True,
            "requires_action_time_final_gate_before_submit": True,
            "requires_official_operation_layer": True,
        },
        "safety_invariants": {
            "official_api_surfaces_only": True,
            "plan_only": not config.execute,
            "creates_runtime_records": bool(new_runtime_ids),
            "mutates_pg_only_for_runtime_admission": bool(executions),
            "creates_candidate": False,
            "creates_execution_intent": False,
            "creates_order": False,
            "calls_exchange_submit": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": {
                name: False for name in sorted(FORBIDDEN_EFFECT_FLAGS)
            },
        },
        "blockers": sorted(set(blockers)),
    }


def _next_step(status: str, new_runtime_created: bool) -> str:
    if status == "executed_runtime_bootstrap" and new_runtime_created:
        return "restart_or_wait_for_runtime_signal_watcher_tick"
    if status == "planned_runtime_bootstrap":
        return "execute_strategygroup_runtime_bootstrap_under_standing_authorization"
    if status == "noop_runtime_bootstrap_not_needed":
        return "continue_watcher_observation"
    if status == "blocked_active_runtime_inventory_unavailable":
        return "restore_trading_console_api_or_operator_session"
    return "resolve_strategygroup_runtime_bootstrap_blockers"


def _active_inventory_counts(payload: dict[str, Any]) -> dict[str, Any]:
    counts = {
        "active_runtime_count": payload.get("active_runtime_count"),
        "monitored_runtime_count": payload.get("monitored_runtime_count"),
    }
    status_packet = payload.get("status_packet")
    if isinstance(status_packet, dict):
        counts["active_runtime_count"] = (
            counts["active_runtime_count"] or status_packet.get("active_runtime_count")
        )
        counts["monitored_runtime_count"] = (
            counts["monitored_runtime_count"]
            or status_packet.get("monitored_runtime_count")
        )
    data = payload.get("data")
    if isinstance(data, dict):
        watcher = data.get("watcher")
        if isinstance(watcher, dict):
            counts["active_runtime_count"] = (
                counts["active_runtime_count"] or watcher.get("active_runtime_count")
            )
            counts["monitored_runtime_count"] = (
                counts["monitored_runtime_count"]
                or watcher.get("monitored_runtime_count")
            )
    return {key: value for key, value in counts.items() if value is not None}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.environ.get("RUNTIME_LIVE_BOOTSTRAP_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--env-file")
    parser.add_argument("--handoff-dir", default=str(DEFAULT_HANDOFF_DIR))
    parser.add_argument("--intake-json")
    parser.add_argument("--live-facts-readiness-json")
    parser.add_argument("--active-runtimes-json")
    parser.add_argument("--strategy-group-id", action="append", default=[])
    parser.add_argument("--include-observe-only", action="store_true")
    parser.add_argument("--max-symbols-per-group", type=int, default=DEFAULT_MAX_SYMBOLS_PER_GROUP)
    parser.add_argument("--max-total-new-runtimes", type=int, default=DEFAULT_MAX_TOTAL_NEW_RUNTIMES)
    parser.add_argument(
        "--account-facts-source",
        choices=["binance_readonly", "static"],
        default="binance_readonly",
    )
    parser.add_argument("--account-facts-json")
    parser.add_argument("--owner-operator-id", default="owner-standing-authorization")
    parser.add_argument("--playbook-id", default=DEFAULT_PLAYBOOK_ID)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _load_env_file(args.env_file)
    intake = (
        _read_json(args.intake_json)
        if args.intake_json
        else build_handoff_intake_packet(handoff_dir=Path(args.handoff_dir))
    )
    live_facts_readiness = _read_json(args.live_facts_readiness_json)
    if args.active_runtimes_json:
        active_payload = _read_json(args.active_runtimes_json)
        active_runtimes = _runtime_rows_from_payload(active_payload)
        active_counts = _active_inventory_counts(active_payload)
        active_blockers: list[str] = []
        client = UrlLibApiClient(api_base=args.api_base) if args.execute else None
    else:
        client = UrlLibApiClient(api_base=args.api_base)
        active_runtimes, active_blockers = _list_active_runtimes(client)
        active_counts = {
            "active_runtime_count": len(active_runtimes),
            "monitored_runtime_count": None,
        }
    packet = build_packet(
        config=RuntimePilotBootstrapConfig(
            api_base=args.api_base,
            execute=args.execute,
            strategy_group_ids=tuple(args.strategy_group_id or []),
            include_observe_only=args.include_observe_only,
            max_symbols_per_group=args.max_symbols_per_group,
            max_total_new_runtimes=args.max_total_new_runtimes,
            account_facts_source=args.account_facts_source,
            account_facts_json=args.account_facts_json,
            owner_operator_id=args.owner_operator_id,
            playbook_id=args.playbook_id,
            output_json=args.output_json,
        ),
        intake_packet=intake,
        live_facts_readiness=live_facts_readiness,
        active_runtimes=active_runtimes,
        active_inventory_blockers=active_blockers,
        active_inventory_counts=active_counts,
        client=client,
    )
    _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not packet["blockers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
