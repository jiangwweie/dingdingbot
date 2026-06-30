#!/usr/bin/env python3
"""Build runtime activation evidence for MPG/SOR and CPM fresh-path readiness.

This is a non-authority projection. It turns Binance USD-M public facts and
recent replay scope review into machine-checkable watcher/facts/rehearsal
evidence. It never creates candidate authorization, never calls FinalGate or
Operation Layer, never writes to an exchange, and never changes live profile or
order sizing.
"""

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


DEFAULT_PUBLIC_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-binance-usdm-public-facts.json"
)
DEFAULT_REPLAY_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-recent-live-submit-replay.json"
)
DEFAULT_CPM_CAPTURE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-capture.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output/runtime-monitor"

SCHEMA = "brc.four_candidate_runtime_activation_evidence.v1"
ACTION_TIME_FACT_KEYS = (
    "exchange_contract_exists",
    "mark_price_fresh",
    "funding_not_extreme",
    "spread_ok",
    "min_notional_ok",
    "qty_step_ok",
    "leverage_available",
    "active_position_or_open_order_clear",
    "action_time_available_balance",
)
PUBLIC_FACT_KEYS = ACTION_TIME_FACT_KEYS[:7]
PRIVATE_ACTION_TIME_FACT_KEYS = ACTION_TIME_FACT_KEYS[7:]
PUBLIC_FACT_ARTIFACT_MAX_AGE_SECONDS = 300

STRATEGY_CONFIG = {
    "MPG-001": {
        "priority": "P0",
        "path_id": "MPG-STRONG-SYMBOL-ROTATION",
        "signal_id": "mpg_strong_symbol_rotation_signal_v1",
        "primary_live_submit_symbol_scope": ["BTCUSDT", "ETHUSDT"],
        "expanded_readonly_watcher_symbols": ["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
        "output_json": "latest-mpg-runtime-activation-evidence.json",
        "output_md": "latest-mpg-runtime-activation-evidence.md",
        "next_blocker": "fresh_mpg_signal_or_private_action_time_facts",
    },
    "SOR-001": {
        "priority": "P1",
        "path_id": "SOR-SESSION-BREAKOUT",
        "signal_id": "sor_session_breakout_signal_v1",
        "primary_live_submit_symbol_scope": ["BTCUSDT", "ETHUSDT"],
        "expanded_readonly_watcher_symbols": ["SOLUSDT", "AVAXUSDT"],
        "output_json": "latest-sor-runtime-activation-evidence.json",
        "output_md": "latest-sor-runtime-activation-evidence.md",
        "next_blocker": "fresh_sor_signal_or_private_action_time_facts",
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-facts-json", default=str(DEFAULT_PUBLIC_FACTS_JSON))
    parser.add_argument("--replay-json", default=str(DEFAULT_REPLAY_JSON))
    parser.add_argument("--cpm-capture-json", default=str(DEFAULT_CPM_CAPTURE_JSON))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    artifacts = build_four_candidate_runtime_activation_evidence(
        public_facts=_read_optional_json(Path(args.public_facts_json)),
        replay=_read_optional_json(Path(args.replay_json)),
        cpm_capture=_read_optional_json(Path(args.cpm_capture_json)),
    )
    for name, artifact in artifacts.items():
        json_path = output_dir / artifact["output_file_names"]["json"]
        md_path = output_dir / artifact["output_file_names"]["md"]
        _write_json(json_path, artifact)
        _write_text(md_path, _markdown(artifact, json_path))
        artifacts[name]["output_paths"] = {"json": str(json_path), "md": str(md_path)}
    print(
        json.dumps(
            {
                "status": "four_candidate_runtime_activation_evidence_ready",
                "mpg_ready": artifacts["mpg"]["runtime_artifact_ready"],
                "sor_ready": artifacts["sor"]["runtime_artifact_ready"],
                "scope_decision": artifacts["scope_decision"]["status"],
                "cpm_public_fact_path_ready": artifacts["cpm_fresh_path"][
                    "public_fact_path_ready"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if all(_artifact_passed(artifact) for artifact in artifacts.values()) else 2


def build_four_candidate_runtime_activation_evidence(
    *,
    public_facts: dict[str, Any],
    replay: dict[str, Any],
    cpm_capture: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, dict[str, Any]]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    generated_dt = _parse_utc(generated)
    public_facts_generated_at = _parse_utc_or_none(
        str(public_facts.get("generated_at_utc") or "")
    )
    public_facts_age_seconds = _age_seconds(public_facts_generated_at, generated_dt)
    public_facts_artifact_fresh = (
        public_facts_age_seconds is not None
        and public_facts_age_seconds <= PUBLIC_FACT_ARTIFACT_MAX_AGE_SECONDS
    )
    public_fact_by_symbol = {
        str(row.get("symbol") or ""): row
        for row in public_facts.get("symbols") or []
        if isinstance(row, dict)
    }
    mpg = _strategy_artifact(
        strategy_group_id="MPG-001",
        config=STRATEGY_CONFIG["MPG-001"],
        replay=replay,
        public_fact_by_symbol=public_fact_by_symbol,
        public_facts_artifact_fresh=public_facts_artifact_fresh,
        public_facts_age_seconds=public_facts_age_seconds,
        generated_at_utc=generated,
    )
    sor = _strategy_artifact(
        strategy_group_id="SOR-001",
        config=STRATEGY_CONFIG["SOR-001"],
        replay=replay,
        public_fact_by_symbol=public_fact_by_symbol,
        public_facts_artifact_fresh=public_facts_artifact_fresh,
        public_facts_age_seconds=public_facts_age_seconds,
        generated_at_utc=generated,
    )
    scope_decision = _scope_decision_artifact(
        replay=replay,
        generated_at_utc=generated,
    )
    cpm_fresh_path = _cpm_fresh_path_artifact(
        public_fact_by_symbol=public_fact_by_symbol,
        public_facts_artifact_fresh=public_facts_artifact_fresh,
        public_facts_age_seconds=public_facts_age_seconds,
        cpm_capture=cpm_capture,
        generated_at_utc=generated,
    )
    return {
        "mpg": mpg,
        "sor": sor,
        "scope_decision": scope_decision,
        "cpm_fresh_path": cpm_fresh_path,
    }


def _strategy_artifact(
    *,
    strategy_group_id: str,
    config: dict[str, Any],
    replay: dict[str, Any],
    public_fact_by_symbol: dict[str, dict[str, Any]],
    public_facts_artifact_fresh: bool,
    public_facts_age_seconds: int | None,
    generated_at_utc: str,
) -> dict[str, Any]:
    primary = list(config["primary_live_submit_symbol_scope"])
    expanded = list(config["expanded_readonly_watcher_symbols"])
    symbols = [*primary, *expanded]
    symbol_rows = [
        _symbol_fact_projection(
            symbol,
            public_fact_by_symbol,
            public_facts_artifact_fresh=public_facts_artifact_fresh,
        )
        for symbol in symbols
    ]
    public_ready = all(row["public_facts_ready"] is True for row in symbol_rows)
    replay_row = _replay_row(replay, strategy_group_id)
    review_signals = _longest_window_value(replay_row, "counterfactual_fresh_signal_count")
    missed = _longest_window_value(replay_row, "missed_opportunity_review_count")
    boundary = _longest_window_value(
        replay_row, "would_reach_action_time_boundary_count"
    )
    runtime_ready = public_ready and review_signals > 0 and missed > 0
    return {
        "schema": SCHEMA,
        "scope": "runtime_activation_evidence_non_authority",
        "status": (
            "runtime_activation_evidence_ready"
            if runtime_ready
            else "runtime_activation_evidence_public_facts_unavailable"
        ),
        "generated_at_utc": generated_at_utc,
        "strategy_group_id": strategy_group_id,
        "path_id": config["path_id"],
        "signal_id": config["signal_id"],
        "priority": config["priority"],
        "runtime_artifact_ready": runtime_ready,
        "watcher_scope_contract_ready": runtime_ready,
        "required_facts_contract_ready": runtime_ready,
        "candidate_evidence_shape_ready": runtime_ready,
        "fresh_signal_rehearsal_ready": runtime_ready,
        "action_time_boundary_ready": runtime_ready,
        "live_submit_allowed": False,
        "watcher_scope": {
            "symbol_scope": symbols,
            "primary_live_submit_symbol_scope": primary,
            "expanded_readonly_watcher_symbols": expanded,
            "source": "binance_usdm_public_facts_readonly",
        },
        "required_facts_contract": {
            "public_fact_keys_ready": list(PUBLIC_FACT_KEYS) if public_ready else [],
            "private_action_time_fact_keys_pending": list(
                PRIVATE_ACTION_TIME_FACT_KEYS
            ),
            "private_action_time_facts_ready": False,
            "replay_proxy_facts_are_not_live_required_facts": True,
        },
        "candidate_evidence_shape": {
            "ready": runtime_ready,
            "candidate_authorization_created": False,
            "rehearsal_only": True,
        },
        "fresh_signal_rehearsal": {
            "ready": runtime_ready,
            "synthetic_or_replay_only": True,
            "replay_treated_as_live_signal": False,
        },
        "replay_summary": {
            "unique_review_signal_count": review_signals,
            "missed_opportunity_review_count": missed,
            "would_reach_action_time_boundary_count": boundary,
        },
        "symbol_public_facts": symbol_rows,
        "public_facts_freshness": {
            "artifact_fresh": public_facts_artifact_fresh,
            "artifact_age_seconds": public_facts_age_seconds,
            "max_artifact_age_seconds": PUBLIC_FACT_ARTIFACT_MAX_AGE_SECONDS,
        },
        "next_blocker": (
            config["next_blocker"]
            if runtime_ready
            else (
                "binance_usdm_public_facts_stale_or_unavailable"
                if not public_facts_artifact_fresh
                else "binance_usdm_public_facts_or_replay_scope_missing"
            )
        ),
        "checks": {
            "public_facts_artifact_fresh": public_facts_artifact_fresh,
            "public_symbol_facts_ready": public_ready,
            "replay_scope_review_present": review_signals > 0 and missed > 0,
            "watcher_scope_contract_ready": runtime_ready,
            "required_facts_contract_ready": runtime_ready,
            "candidate_evidence_shape_ready": runtime_ready,
            "fresh_signal_rehearsal_ready": runtime_ready,
            "live_submit_allowed": False,
            "candidate_authorization_created": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
        "authority_boundary": _authority_boundary(
            "runtime_activation_evidence_not_live_authority"
        ),
        "interaction": non_executing_interaction(
            f"L0_local_{strategy_group_id.lower().replace('-', '_')}_runtime_activation_evidence"
        ),
        "safety_invariants": _safety_invariants(),
        "output_file_names": {
            "json": config["output_json"],
            "md": config["output_md"],
        },
    }


def _scope_decision_artifact(
    *, replay: dict[str, Any], generated_at_utc: str
) -> dict[str, Any]:
    recommendations = _scope_recommendations(replay)
    decisions = []
    desired = {
        "MPG-001": ["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
        "CPM-RO-001": ["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
        "SOR-001": ["SOLUSDT", "AVAXUSDT"],
    }
    for strategy_group_id, symbols in desired.items():
        replay_symbols = recommendations.get(strategy_group_id, [])
        decisions.append(
            {
                "strategy_group_id": strategy_group_id,
                "decision": "approve_readonly_watcher_scope_expansion",
                "symbols": symbols,
                "replay_recommended_symbols": replay_symbols,
                "primary_live_submit_scope_changed": False,
                "requires_binance_usdm_public_facts": True,
                "requires_private_action_time_facts_before_live_submit": True,
                "owner_policy_required": False,
                "authority_boundary": "read_only_watcher_scope_only_not_live_scope",
            }
        )
    return {
        "schema": "brc.four_candidate_scope_review_decision.v1",
        "scope": "scope_review_decision_non_authority",
        "status": "four_candidate_scope_review_decision_ready",
        "generated_at_utc": generated_at_utc,
        "decisions": decisions,
        "summary": {
            "decision_count": len(decisions),
            "primary_live_submit_scope_changed_count": 0,
            "readonly_watcher_scope_expansion_count": len(decisions),
            "deferred_replay_symbols": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "reason": "not_in_owner_requested_sol_avax_sui_batch",
                }
            ],
        },
        "checks": {
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "owner_policy_required": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
        "authority_boundary": _authority_boundary("scope_review_decision_not_live_authority"),
        "interaction": non_executing_interaction(
            "L0_local_four_candidate_scope_review_decision"
        ),
        "safety_invariants": _safety_invariants(),
        "output_file_names": {
            "json": "latest-four-candidate-scope-review-decision.json",
            "md": "latest-four-candidate-scope-review-decision.md",
        },
    }


def _cpm_fresh_path_artifact(
    *,
    public_fact_by_symbol: dict[str, dict[str, Any]],
    public_facts_artifact_fresh: bool,
    public_facts_age_seconds: int | None,
    cpm_capture: dict[str, Any],
    generated_at_utc: str,
) -> dict[str, Any]:
    symbols = ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"]
    symbol_rows = [
        _symbol_fact_projection(
            symbol,
            public_fact_by_symbol,
            public_facts_artifact_fresh=public_facts_artifact_fresh,
        )
        for symbol in symbols
    ]
    public_ready = all(row["public_facts_ready"] is True for row in symbol_rows)
    signal_state = str(cpm_capture.get("current_signal_state") or "")
    fresh_signal_present = signal_state == "fresh_signal_present"
    return {
        "schema": "brc.cpm_fresh_signal_live_path_readiness.v1",
        "scope": "cpm_fresh_signal_live_path_readiness_non_authority",
        "status": "cpm_fresh_signal_live_path_readiness_ready",
        "generated_at_utc": generated_at_utc,
        "strategy_group_id": "CPM-RO-001",
        "path_id": "CPM-LONG",
        "watcher_scope_symbols": symbols,
        "public_fact_path_ready": public_ready,
        "public_facts_freshness": {
            "artifact_fresh": public_facts_artifact_fresh,
            "artifact_age_seconds": public_facts_age_seconds,
            "max_artifact_age_seconds": PUBLIC_FACT_ARTIFACT_MAX_AGE_SECONDS,
        },
        "fresh_signal_present": fresh_signal_present,
        "current_signal_state": signal_state or "unknown",
        "private_action_time_facts_ready": False,
        "would_enter_finalgate_when_fresh_signal_and_private_facts": public_ready,
        "finalgate_called": False,
        "operation_layer_called": False,
        "live_submit_allowed": False,
        "symbol_public_facts": symbol_rows,
        "next_blocker": (
            "binance_usdm_public_facts_stale_or_unavailable"
            if not public_ready
            else (
                "fresh_cpm_long_signal_absent"
                if not fresh_signal_present
                else "private_action_time_facts_required"
            )
        ),
        "checks": {
            "public_facts_artifact_fresh": public_facts_artifact_fresh,
            "public_fact_path_ready": public_ready,
            "fresh_signal_present": fresh_signal_present,
            "private_action_time_facts_ready": False,
            "candidate_authorization_created": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_submit_allowed": False,
        },
        "authority_boundary": _authority_boundary(
            "cpm_fresh_signal_live_path_readiness_not_live_authority"
        ),
        "interaction": non_executing_interaction(
            "L0_local_cpm_fresh_signal_live_path_readiness"
        ),
        "safety_invariants": _safety_invariants(),
        "output_file_names": {
            "json": "latest-cpm-fresh-signal-live-path-readiness.json",
            "md": "latest-cpm-fresh-signal-live-path-readiness.md",
        },
    }


def _symbol_fact_projection(
    symbol: str,
    public_fact_by_symbol: dict[str, dict[str, Any]],
    *,
    public_facts_artifact_fresh: bool,
) -> dict[str, Any]:
    source = public_fact_by_symbol.get(symbol, {})
    source_ready = source.get("public_facts_ready") is True
    mark_fresh = source.get("mark_price_fresh") is True
    return {
        "symbol": symbol,
        "public_facts_ready": public_facts_artifact_fresh and source_ready and mark_fresh,
        "source_public_facts_ready": source_ready,
        "public_facts_artifact_fresh": public_facts_artifact_fresh,
        "exchange_contract_exists": source.get("exchange_contract_exists") is True,
        "mark_price_fresh": mark_fresh,
        "mark_price_observed_at_utc": source.get("mark_price_observed_at_utc"),
        "mark_price_age_seconds": source.get("mark_price_age_seconds"),
        "max_mark_price_age_seconds": source.get("max_mark_price_age_seconds"),
        "funding_not_extreme": source.get("funding_not_extreme") is True,
        "spread_ok": source.get("spread_ok") is True,
        "min_notional_ok": source.get("min_notional_ok") is True,
        "qty_step_ok": source.get("qty_step_ok") is True,
        "leverage_available": source.get("leverage_available") is True,
        "facts": source.get("facts") or {},
    }


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _parse_utc_or_none(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return _parse_utc(value)
    except ValueError:
        return None


def _age_seconds(observed_at: datetime | None, now: datetime) -> int | None:
    if observed_at is None:
        return None
    return max(0, int((now - observed_at).total_seconds()))


def _artifact_passed(artifact: dict[str, Any]) -> bool:
    status = str(artifact.get("status") or "")
    return status.endswith("_ready")


def _scope_recommendations(replay: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    summary = replay.get("summary") if isinstance(replay.get("summary"), dict) else {}
    for item in summary.get("should_promote_scope_change") or []:
        if not isinstance(item, dict):
            continue
        out[str(item.get("strategy_group_id") or "")] = [
            str(symbol) for symbol in item.get("candidate_symbols") or []
        ]
    return out


def _replay_row(replay: dict[str, Any], strategy_group_id: str) -> dict[str, Any]:
    for row in replay.get("strategy_rows") or []:
        if isinstance(row, dict) and row.get("strategy_group_id") == strategy_group_id:
            return row
    return {}


def _longest_window_value(row: dict[str, Any], key: str) -> int:
    windows = [item for item in row.get("window_results") or [] if isinstance(item, dict)]
    if not windows:
        return 0
    window = sorted(windows, key=lambda item: int(item.get("window_days") or 0))[-1]
    return int(window.get(key) or 0)


def _authority_boundary(role: str) -> dict[str, Any]:
    return {
        "artifact_role": role,
        "changes_live_profile": False,
        "changes_order_sizing": False,
        "replay_treated_as_live_signal": False,
        "candidate_authorization_created": False,
        "finalgate_called": False,
        "operation_layer_called": False,
        "exchange_write_called": False,
        "order_created": False,
    }


def _safety_invariants() -> dict[str, bool]:
    return non_executing_safety_invariants(
        (
            "live_profile_changed",
            "order_sizing_changed",
            "replay_treated_as_live_signal",
            "candidate_authorization_created",
            "calls_finalgate",
            "calls_operation_layer",
            "calls_exchange_write",
            "places_order",
            "order_created",
        ),
        include_authority_mirrors=False,
    )


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    if artifact["scope"] == "runtime_activation_evidence_non_authority":
        return _strategy_markdown(artifact, output_json)
    if artifact["scope"] == "scope_review_decision_non_authority":
        return _scope_markdown(artifact, output_json)
    return _cpm_markdown(artifact, output_json)


def _strategy_markdown(artifact: dict[str, Any], output_json: Path) -> str:
    return "\n".join(
        [
            f"## {artifact['strategy_group_id']} Runtime Activation Evidence",
            "",
            f"- Status: `{artifact['status']}`",
            f"- Runtime artifact ready: `{_yes_no(artifact['runtime_artifact_ready'])}`",
            f"- Watcher/facts/candidate/rehearsal: `{_yes_no(artifact['watcher_scope_contract_ready'])}` / `{_yes_no(artifact['required_facts_contract_ready'])}` / `{_yes_no(artifact['candidate_evidence_shape_ready'])}` / `{_yes_no(artifact['fresh_signal_rehearsal_ready'])}`",
            f"- Live-submit allowed: `{_yes_no(artifact['live_submit_allowed'])}`",
            f"- Next blocker: `{artifact['next_blocker']}`",
            f"- Output JSON: `{output_json}`",
        ]
    ) + "\n"


def _scope_markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## Four-Candidate Scope Review Decision",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Read-only watcher expansions: `{artifact['summary']['readonly_watcher_scope_expansion_count']}`",
        f"- Live profile changes: `{artifact['summary']['primary_live_submit_scope_changed_count']}`",
        f"- Output JSON: `{output_json}`",
        "",
        "| Strategy | Decision | Symbols |",
        "| --- | --- | --- |",
    ]
    for item in artifact["decisions"]:
        lines.append(
            f"| `{item['strategy_group_id']}` | `{item['decision']}` | `{', '.join(item['symbols'])}` |"
        )
    return "\n".join(lines) + "\n"


def _cpm_markdown(artifact: dict[str, Any], output_json: Path) -> str:
    return "\n".join(
        [
            "## CPM Fresh-Signal Live Path Readiness",
            "",
            f"- Status: `{artifact['status']}`",
            f"- Public fact path ready: `{_yes_no(artifact['public_fact_path_ready'])}`",
            f"- Fresh signal present: `{_yes_no(artifact['fresh_signal_present'])}`",
            f"- FinalGate/Operation Layer called: `{_yes_no(artifact['finalgate_called'])}` / `{_yes_no(artifact['operation_layer_called'])}`",
            f"- Live-submit allowed: `{_yes_no(artifact['live_submit_allowed'])}`",
            f"- Next blocker: `{artifact['next_blocker']}`",
            f"- Output JSON: `{output_json}`",
        ]
    ) + "\n"


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
