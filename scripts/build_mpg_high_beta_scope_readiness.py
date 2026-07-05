#!/usr/bin/env python3
"""Build MPG high-beta symbol scope and action-time readiness projections."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)
from runtime_pg_fact_snapshots import read_pretrade_public_facts_artifact  # noqa: E402


DEFAULT_REPLAY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-four-candidate-recent-live-submit-replay.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output/runtime-monitor"

STRATEGY_GROUP_ID = "MPG-001"
PRIMARY_LIVE_SCOPE = ("BTCUSDT", "ETHUSDT")
HIGH_BETA_REVIEW_SCOPE = ("SOLUSDT", "AVAXUSDT", "OPUSDT", "SUIUSDT")
READONLY_EXPANSION_SCOPE = ("SOLUSDT", "AVAXUSDT", "SUIUSDT")
PUBLIC_FACT_KEYS = (
    "exchange_contract_exists",
    "mark_price_fresh",
    "funding_not_extreme",
    "spread_ok",
    "min_notional_ok",
    "qty_step_ok",
    "leverage_available",
)
PRIVATE_ACTION_TIME_FACT_KEYS = (
    "active_position_or_open_order_clear",
    "action_time_available_balance",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-json", default=str(DEFAULT_REPLAY_JSON))
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    if not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for DB-backed MPG readiness", file=sys.stderr)
        return 2
    if not args.database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ) and not args.allow_non_postgres_for_test:
        print("ERROR: DB-backed MPG readiness requires PostgreSQL DSN", file=sys.stderr)
        return 2
    engine = sa.create_engine(args.database_url)
    try:
        with engine.connect() as conn:
            public_facts = read_pretrade_public_facts_artifact(
                conn,
                symbols=list(HIGH_BETA_REVIEW_SCOPE),
            )
    finally:
        engine.dispose()
    artifacts = build_mpg_high_beta_scope_readiness(
        public_facts=public_facts,
        replay=_read_optional_json(Path(args.replay_json)),
    )
    output_dir = Path(args.output_dir)
    for artifact in artifacts.values():
        json_path = output_dir / artifact["output_file_names"]["json"]
        md_path = output_dir / artifact["output_file_names"]["md"]
        _write_json(json_path, artifact)
        _write_text(md_path, _markdown(artifact, json_path))
    print(
        json.dumps(
            {
                "status": "mpg_high_beta_scope_readiness_ready",
                "readonly_watcher_symbols": list(READONLY_EXPANSION_SCOPE),
                "primary_live_submit_scope_changed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_mpg_high_beta_scope_readiness(
    *,
    public_facts: dict[str, Any],
    replay: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, dict[str, Any]]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    public_by_symbol = {
        str(row.get("symbol") or ""): row
        for row in public_facts.get("symbols") or []
        if isinstance(row, dict)
    }
    replay_symbols = _replay_symbols(replay)
    symbol_rows = [
        _symbol_scope_row(symbol, public_by_symbol.get(symbol, {}), replay_symbols)
        for symbol in HIGH_BETA_REVIEW_SCOPE
    ]
    approved_readonly = [
        row["symbol"]
        for row in symbol_rows
        if row["scope_decision"] == "approve_readonly_watcher_scope"
    ]
    scoped_observation_proposal = [
        row["symbol"]
        for row in symbol_rows
        if row["scope_decision"] != "approve_readonly_watcher_scope"
        and row["strategy_fit"] is True
    ]
    scope_decision = _scope_decision_artifact(
        generated_at_utc=generated,
        symbol_rows=symbol_rows,
        approved_readonly=approved_readonly,
        scoped_observation_proposal=scoped_observation_proposal,
    )
    watcher = _watcher_artifact(
        generated_at_utc=generated,
        symbol_rows=symbol_rows,
        approved_readonly=approved_readonly,
        scoped_observation_proposal=scoped_observation_proposal,
    )
    readiness = _action_time_readiness_artifact(
        generated_at_utc=generated,
        symbol_rows=symbol_rows,
        approved_readonly=approved_readonly,
    )
    return {
        "scope_decision": scope_decision,
        "expanded_watcher": watcher,
        "action_time_readiness": readiness,
    }


def _symbol_scope_row(
    symbol: str,
    public_row: dict[str, Any],
    replay_symbols: set[str],
) -> dict[str, Any]:
    public_facts_ready = public_row.get("public_facts_ready") is True
    public_checks = {
        key: public_row.get(key) is True
        for key in PUBLIC_FACT_KEYS
    }
    strategy_fit = symbol in replay_symbols or symbol in READONLY_EXPANSION_SCOPE
    volatility_path_risk = (
        "review_only_high_beta_path_risk"
        if symbol in {"SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT"}
        else "standard"
    )
    can_readonly_watch = (
        symbol in READONLY_EXPANSION_SCOPE
        and public_facts_ready
        and all(public_checks.values())
        and strategy_fit
    )
    rejection_reasons = []
    if not public_facts_ready:
        rejection_reasons.append("binance_usdm_public_facts_missing_or_stale")
    for key, ready in public_checks.items():
        if not ready:
            rejection_reasons.append(key)
    if not strategy_fit:
        rejection_reasons.append("strategy_fit_not_supported_by_replay")
    if symbol not in READONLY_EXPANSION_SCOPE:
        rejection_reasons.append("not_in_current_readonly_watcher_batch")
    return {
        "symbol": symbol,
        "scope_decision": (
            "approve_readonly_watcher_scope"
            if can_readonly_watch
            else "defer_primary_or_readonly_scope"
        ),
        "primary_live_submit_scope_changed": False,
        "public_facts_ready": public_facts_ready,
        "strategy_fit": strategy_fit,
        "liquidity": {
            "spread_ok": public_checks["spread_ok"],
            "min_notional_ok": public_checks["min_notional_ok"],
            "qty_step_ok": public_checks["qty_step_ok"],
            "spread_bps": _as_dict(public_row.get("facts")).get("spread_bps"),
            "min_notional": _as_dict(public_row.get("facts")).get("min_notional"),
        },
        "funding": {
            "funding_not_extreme": public_checks["funding_not_extreme"],
            "last_funding_rate": _as_dict(public_row.get("facts")).get(
                "last_funding_rate"
            ),
        },
        "volatility_path_risk": volatility_path_risk,
        "rejection_reasons": rejection_reasons,
        "next_action": (
            "attach_mpg_readonly_watcher_fact_projection"
            if can_readonly_watch
            else "refresh_public_facts_or_keep_symbol_in_scope_review"
        ),
    }


def _scope_decision_artifact(
    *,
    generated_at_utc: str,
    symbol_rows: list[dict[str, Any]],
    approved_readonly: list[str],
    scoped_observation_proposal: list[str],
) -> dict[str, Any]:
    return {
        "schema": "brc.mpg_symbol_scope_decision.v1",
        "scope": "mpg_high_beta_symbol_scope_decision_non_authority",
        "status": "mpg_symbol_scope_decision_ready",
        "generated_at_utc": generated_at_utc,
        "strategy_group_id": STRATEGY_GROUP_ID,
        "path_id": "MPG-STRONG-SYMBOL-ROTATION",
        "primary_live_submit_symbol_scope": list(PRIMARY_LIVE_SCOPE),
        "approved_readonly_watcher_symbols": approved_readonly,
        "scoped_live_observation_proposal_symbols": scoped_observation_proposal,
        "reviewed_high_beta_symbols": list(HIGH_BETA_REVIEW_SCOPE),
        "symbol_decisions": symbol_rows,
        "checks": _common_checks(),
        "interaction": non_executing_interaction("L0_local_mpg_symbol_scope_decision"),
        "safety_invariants": _safety_invariants(),
        "output_file_names": {
            "json": "latest-mpg-symbol-scope-decision.json",
            "md": "latest-mpg-symbol-scope-decision.md",
        },
    }


def _watcher_artifact(
    *,
    generated_at_utc: str,
    symbol_rows: list[dict[str, Any]],
    approved_readonly: list[str],
    scoped_observation_proposal: list[str],
) -> dict[str, Any]:
    symbol_scope = [*PRIMARY_LIVE_SCOPE, *approved_readonly]
    return {
        "schema": "brc.mpg_expanded_watcher_facts.v1",
        "scope": "mpg_expanded_readonly_watcher_facts_non_authority",
        "status": "mpg_expanded_watcher_facts_ready",
        "generated_at_utc": generated_at_utc,
        "strategy_group_id": STRATEGY_GROUP_ID,
        "watcher_scope": {
            "symbol_scope": symbol_scope,
            "primary_live_submit_symbol_scope": list(PRIMARY_LIVE_SCOPE),
            "expanded_readonly_watcher_symbols": approved_readonly,
            "scoped_live_observation_proposal_symbols": (
                scoped_observation_proposal
            ),
            "source": "binance_usdm_public_facts_readonly",
        },
        "symbol_public_fact_rows": symbol_rows,
        "checks": {
            **_common_checks(),
            "expanded_readonly_watcher_ready": bool(approved_readonly),
            "required_facts_mapping_ready": True,
        },
        "interaction": non_executing_interaction("L0_local_mpg_expanded_watcher_facts"),
        "safety_invariants": _safety_invariants(),
        "output_file_names": {
            "json": "latest-mpg-expanded-watcher-facts.json",
            "md": "latest-mpg-expanded-watcher-facts.md",
        },
    }


def _action_time_readiness_artifact(
    *,
    generated_at_utc: str,
    symbol_rows: list[dict[str, Any]],
    approved_readonly: list[str],
) -> dict[str, Any]:
    public_ready = bool(approved_readonly)
    return {
        "schema": "brc.mpg_action_time_facts_readiness.v1",
        "scope": "mpg_action_time_facts_readiness_projection_non_authority",
        "status": "mpg_action_time_facts_readiness_ready",
        "generated_at_utc": generated_at_utc,
        "strategy_group_id": STRATEGY_GROUP_ID,
        "public_fact_keys_ready": list(PUBLIC_FACT_KEYS) if public_ready else [],
        "private_action_time_fact_keys_pending": list(PRIVATE_ACTION_TIME_FACT_KEYS),
        "private_action_time_facts_ready": False,
        "would_enter_finalgate_when_fresh_signal_and_private_facts": public_ready,
        "first_blocker": (
            "fresh_mpg_signal_or_private_action_time_facts"
            if public_ready
            else "mpg_high_beta_public_facts_gap"
        ),
        "blocker_owner": "market" if public_ready else "engineering",
        "post_action_expected_state": (
            "action_time_boundary_ready_when_fresh_signal_and_private_facts_arrive"
        ),
        "symbol_readiness": symbol_rows,
        "checks": {
            **_common_checks(),
            "public_facts_ready_for_readonly_symbols": public_ready,
            "private_action_time_facts_ready": False,
            "would_enter_finalgate_when_fresh_signal_and_private_facts": public_ready,
        },
        "interaction": non_executing_interaction(
            "L0_local_mpg_action_time_facts_readiness"
        ),
        "safety_invariants": _safety_invariants(),
        "output_file_names": {
            "json": "latest-mpg-action-time-facts-readiness.json",
            "md": "latest-mpg-action-time-facts-readiness.md",
        },
    }


def _replay_symbols(replay: dict[str, Any]) -> set[str]:
    symbols: set[str] = set()
    for item in _as_dict(replay.get("summary")).get("should_promote_scope_change") or []:
        if not isinstance(item, dict):
            continue
        if item.get("strategy_group_id") != STRATEGY_GROUP_ID:
            continue
        symbols.update(str(symbol) for symbol in item.get("candidate_symbols") or [])
    return symbols


def _common_checks() -> dict[str, bool]:
    return {
        "primary_live_submit_scope_changed": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "candidate_authorization_created": False,
        "finalgate_called": False,
        "operation_layer_called": False,
        "exchange_write_called": False,
        "order_created": False,
        "live_submit_allowed": False,
    }


def _safety_invariants() -> dict[str, bool]:
    return {
        **non_executing_safety_invariants(tuple(), include_authority_mirrors=False),
        "live_profile_changed": False,
        "order_sizing_changed": False,
    }


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    return "\n".join(
        [
            f"## {artifact['schema']}",
            "",
            f"- Status: `{artifact['status']}`",
            f"- StrategyGroup: `{artifact['strategy_group_id']}`",
            f"- Live scope changed: `{_yes_no(artifact['checks']['live_profile_changed'])}`",
            f"- FinalGate/Operation Layer called: `{_yes_no(artifact['checks']['finalgate_called'])}` / `{_yes_no(artifact['checks']['operation_layer_called'])}`",
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


if __name__ == "__main__":
    raise SystemExit(main())
