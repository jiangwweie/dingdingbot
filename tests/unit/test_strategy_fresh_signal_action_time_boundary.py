from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategy_fresh_signal_action_time_boundary.py"
)
NOW_MS = 1_800_000


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategy_fresh_signal_action_time_boundary",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _control_state(
    *,
    readiness: list[dict] | None = None,
    signals: list[dict] | None = None,
    promotions: list[dict] | None = None,
    lanes: list[dict] | None = None,
    facts: list[dict] | None = None,
) -> dict:
    rows = {
        "pretrade_readiness_rows": readiness or [],
        "live_signal_events": signals or [],
        "promotion_candidates": promotions or [],
        "action_time_lane_inputs": lanes or [],
        "action_time_tickets": [],
        "runtime_fact_snapshots": facts or [],
    }
    return {
        "schema": "brc.runtime_control_state_repository.v1",
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "table_counts": {key: len(value) for key, value in rows.items()},
        **rows,
    }


def _readiness(
    *,
    strategy_group_id: str = "SOR-001",
    symbol: str = "ETHUSDT",
    side: str = "long",
    state: str = "action_time_lane",
    blocker: str = "action_time_preflight_ready",
) -> dict:
    return {
        "readiness_row_id": f"ready:{strategy_group_id}:{symbol}:{side}",
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "readiness_state": state,
        "public_facts_state": "satisfied",
        "signal_lifecycle_status": "facts_validated"
        if state == "action_time_lane"
        else "absent",
        "signal_freshness_state": "fresh" if state == "action_time_lane" else "missing",
        "first_blocker_class": blocker,
        "computed_at_ms": NOW_MS - 200,
        "valid_until_ms": NOW_MS + 60_000,
    }


def _signal(
    *,
    strategy_group_id: str = "SOR-001",
    symbol: str = "ETHUSDT",
    side: str = "long",
    fact_snapshot_id: str = "fact:public",
    source_kind: str = "live_market",
    status: str = "facts_validated",
    freshness_state: str = "fresh",
) -> dict:
    return {
        "signal_event_id": f"signal:{strategy_group_id}:{symbol}:{side}",
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "detector_key": "sor_session_detector",
        "source_kind": source_kind,
        "status": status,
        "freshness_state": freshness_state,
        "fact_snapshot_id": fact_snapshot_id,
        "event_time_ms": NOW_MS - 500,
        "trigger_candle_close_time_ms": NOW_MS - 500,
        "observed_at_ms": NOW_MS - 100,
        "expires_at_ms": NOW_MS + 60_000,
    }


def _promotion(
    *,
    strategy_group_id: str = "SOR-001",
    symbol: str = "ETHUSDT",
    side: str = "long",
    status: str = "arbitration_won",
    blockers: list[str] | None = None,
) -> dict:
    return {
        "promotion_candidate_id": f"promotion:{strategy_group_id}:{symbol}:{side}",
        "signal_event_id": f"signal:{strategy_group_id}:{symbol}:{side}",
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "status": status,
        "blockers": blockers or [],
        "created_at_ms": NOW_MS - 80,
        "expires_at_ms": NOW_MS + 60_000,
    }


def _lane(
    *,
    strategy_group_id: str = "SOR-001",
    symbol: str = "ETHUSDT",
    side: str = "long",
    first_blocker: str = "action_time_preflight_ready",
) -> dict:
    return {
        "action_time_lane_input_id": f"lane:{strategy_group_id}:{symbol}:{side}",
        "promotion_candidate_id": f"promotion:{strategy_group_id}:{symbol}:{side}",
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "runtime_profile_id": "runtime:tiny-live",
        "lane_scope": "real_submit_candidate",
        "status": "ticket_pending",
        "signal_event_id": f"signal:{strategy_group_id}:{symbol}:{side}",
        "public_fact_snapshot_id": "fact:public",
        "action_time_fact_snapshot_id": "fact:action",
        "first_blocker_class": first_blocker,
        "created_at_ms": NOW_MS - 50,
        "expires_at_ms": NOW_MS + 60_000,
    }


def _fact(
    fact_snapshot_id: str,
    *,
    surface: str,
    strategy_group_id: str | None = "SOR-001",
    symbol: str | None = "ETHUSDT",
    side: str | None = "long",
    satisfied: bool = True,
    fact_values: dict | None = None,
) -> dict:
    return {
        "fact_snapshot_id": fact_snapshot_id,
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "fact_surface": surface,
        "computed": True,
        "satisfied": satisfied,
        "freshness_state": "fresh",
        "fact_values": fact_values or {},
        "observed_at_ms": NOW_MS - 75,
        "valid_until_ms": NOW_MS + 60_000,
    }


def _ready_facts() -> list[dict]:
    return [
        _fact("fact:public", surface="public_pretrade"),
        _fact("fact:action", surface="action_time"),
        _fact(
            "fact:account-safe",
            surface="account_safe",
            strategy_group_id=None,
            symbol=None,
            side=None,
            fact_values={
                "account_safe": True,
                "active_position_or_open_order_clear": True,
                "action_time_available_balance": True,
            },
        ),
        _fact(
            "fact:account-mode",
            surface="account_mode",
            strategy_group_id=None,
            symbol=None,
            side=None,
        ),
    ]


def test_pg_action_time_lane_projects_trade_identity_without_authority():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        control_state=_control_state(
            readiness=[_readiness()],
            signals=[_signal()],
            promotions=[_promotion()],
            lanes=[_lane()],
            facts=_ready_facts(),
        ),
        generated_at_utc="2026-07-05T00:00:00+00:00",
        now_ms=NOW_MS,
    )

    row = artifact["strategy_rows"][0]
    assert artifact["source_mode"] == "db_backed"
    assert artifact["checks"]["legacy_strategy_json_inputs_allowed"] is False
    assert row["strategy_group_id"] == "SOR-001"
    assert row["symbol"] == "ETHUSDT"
    assert row["side"] == "long"
    assert row["signal_event_id"] == "signal:SOR-001:ETHUSDT:long"
    assert row["promotion_candidate_id"] == "promotion:SOR-001:ETHUSDT:long"
    assert row["action_time_lane_input_id"] == "lane:SOR-001:ETHUSDT:long"
    assert row["fresh_signal_present"] is True
    assert row["first_blocker"] == "action_time_preflight_ready"
    assert row["required_facts_readiness"]["private_action_time_facts_ready"] is True
    assert row["action_time_path_ready"] is True
    assert row["would_enter_finalgate_if_private_facts_ready"] is True
    assert row["calls_finalgate"] is False
    assert row["calls_operation_layer"] is False
    assert row["calls_exchange_write"] is False
    assert row["order_created"] is False
    assert row["live_submit_allowed"] is False


def test_pg_market_wait_row_does_not_pretend_to_have_fresh_signal():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        control_state=_control_state(
            readiness=[
                _readiness(
                    strategy_group_id="CPM-RO-001",
                    symbol="SOLUSDT",
                    side="long",
                    state="market_wait_validated",
                    blocker="market_wait_validated",
                )
            ],
            facts=[
                _fact(
                    "fact:cpm-public",
                    surface="public_pretrade",
                    strategy_group_id="CPM-RO-001",
                    symbol="SOLUSDT",
                    side="long",
                )
            ],
        ),
        generated_at_utc="2026-07-05T00:00:00+00:00",
        now_ms=NOW_MS,
    )

    row = artifact["strategy_rows"][0]
    assert row["strategy_group_id"] == "CPM-RO-001"
    assert row["symbol"] == "SOLUSDT"
    assert row["fresh_signal_present"] is False
    assert row["first_blocker"] == "market_wait_validated"
    assert row["blocker_owner"] == "market"
    assert row["would_enter_finalgate_if_private_facts_ready"] is False
    assert row["next_action"] == "continue_watcher_observation_until_fresh_signal"


def test_pg_projection_fails_closed_to_watcher_tick_missing_when_public_fact_is_absent():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        control_state=_control_state(
            readiness=[_readiness()],
            signals=[_signal()],
            promotions=[_promotion()],
            lanes=[_lane()],
            facts=[
                fact for fact in _ready_facts() if fact["fact_surface"] != "public_pretrade"
            ],
        ),
        generated_at_utc="2026-07-05T00:00:00+00:00",
        now_ms=NOW_MS,
    )

    row = artifact["strategy_rows"][0]
    assert row["required_facts_readiness"]["public_facts_ready"] is False
    assert row["first_blocker"] == "watcher_tick_missing"
    assert row["blocker_owner"] == "runtime"
    assert row["action_time_path_ready"] is False
    assert row["would_enter_finalgate_if_private_facts_ready"] is False


def test_pg_projection_fails_closed_when_readiness_projection_is_expired():
    module = _load_module()
    expired_readiness = _readiness(
        strategy_group_id="MPG-001",
        symbol="OPUSDT",
        side="long",
        state="market_wait_validated",
        blocker="market_wait_validated",
    )
    expired_readiness["valid_until_ms"] = NOW_MS - 1

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        control_state=_control_state(readiness=[expired_readiness]),
        generated_at_utc="2026-07-05T00:00:00+00:00",
        now_ms=NOW_MS,
    )

    row = artifact["strategy_rows"][0]
    assert row["required_facts_readiness"]["public_facts_ready"] is False
    assert row["first_blocker"] == "watcher_tick_missing"
    assert row["blocker_owner"] == "runtime"
    assert row["next_action"] == "refresh_or_repair_watcher_public_fact_input"


def test_pg_projection_ignores_non_live_or_stale_signal_rows():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        control_state=_control_state(
            readiness=[_readiness(state="market_wait_validated", blocker="market_wait_validated")],
            signals=[
                _signal(source_kind="synthetic"),
                _signal(status="detected"),
                _signal(freshness_state="stale"),
            ],
            facts=_ready_facts(),
        ),
        generated_at_utc="2026-07-05T00:00:00+00:00",
        now_ms=NOW_MS,
    )

    row = artifact["strategy_rows"][0]
    assert row["fresh_signal_present"] is False
    assert row["signal_event_id"] == ""
    assert row["first_blocker"] == "market_wait_validated"


def test_action_time_boundary_rejects_retired_strategy_json_arg(tmp_path: Path):
    module = _load_module()

    with pytest.raises(SystemExit):
        module.main(
            [
                "--cpm-capture-json",
                str(tmp_path / "cpm-runtime-signal-capture-fixture.json"),
            ]
        )
