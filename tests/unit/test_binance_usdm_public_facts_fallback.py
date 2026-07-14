from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "fetch_binance_usdm_public_facts.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_binance_usdm_public_facts",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_facts_rejects_legacy_fallback_json_arg(tmp_path: Path):
    module = _load_module()
    fallback = tmp_path / "fallback.json"

    with pytest.raises(SystemExit):
        module.main(["--fallback-json", str(fallback)])

    assert not hasattr(module, "_fallback_public_facts")


def test_public_facts_requires_pg_database_url_before_fetching(monkeypatch):
    module = _load_module()
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)

    assert module.main(["--symbols", "ETHUSDT"]) == 2


def test_public_facts_reads_default_symbols_from_pg_candidate_scope(tmp_path, monkeypatch, capsys):
    module = _load_module()
    database_url = f"sqlite:///{tmp_path / 'runtime.db'}"
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    CREATE TABLE brc_strategy_group_candidate_scope (
                      symbol TEXT,
                      status TEXT,
                      observation_scope TEXT
                    )
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    CREATE TABLE brc_runtime_fact_snapshots (
                      fact_snapshot_id TEXT PRIMARY KEY,
                      strategy_group_id TEXT,
                      symbol TEXT,
                      side TEXT,
                      runtime_profile_id TEXT,
                      fact_surface TEXT,
                      source_kind TEXT,
                      source_ref TEXT,
                      computed BOOLEAN,
                      satisfied BOOLEAN,
                      freshness_state TEXT,
                      failed_facts TEXT,
                      fact_values TEXT,
                      blocker_class TEXT,
                      observed_at_ms INTEGER,
                      valid_until_ms INTEGER,
                      created_at_ms INTEGER
                    )
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_strategy_group_candidate_scope
                      (symbol, status, observation_scope)
                    VALUES
                      ('OPUSDT', 'active', 'active_wip'),
                      ('ETH/USDT:USDT', 'active', 'active_wip'),
                      ('BTCUSDT', 'paused', 'active_wip')
                    """
                )
            )
    finally:
        engine.dispose()

    seen: dict[str, list[str]] = {}

    def fake_build_public_facts(*, symbols, generated_at_utc=None):
        seen["symbols"] = list(symbols)
        return {
            "status": "binance_usdm_public_facts_ready",
            "generated_at_utc": "2026-07-07T00:00:00+00:00",
            "summary": {"ready_symbol_count": len(symbols)},
            "symbols": [],
            "interaction": {"remote_interaction_count": 0},
        }

    monkeypatch.setattr(module, "build_public_facts", fake_build_public_facts)
    monkeypatch.setattr(
        module,
        "write_pretrade_public_fact_snapshots",
        lambda conn, artifact, source_ref: [],
    )

    assert (
        module.main(
            [
                "--database-url",
                database_url,
                "--allow-non-postgres-for-test",
            ]
        )
        == 0
    )

    assert seen["symbols"] == ["ETHUSDT", "OPUSDT"]
    assert json.loads(capsys.readouterr().out)["status"] == (
        "binance_usdm_public_facts_ready"
    )


def test_public_fact_row_persists_market_entry_minimum_quantity(monkeypatch):
    module = _load_module()
    observed_at = datetime(2026, 7, 12, tzinfo=timezone.utc)

    def fake_fetch(path, errors):
        if "premiumIndex" in path:
            return {
                "markPrice": "100",
                "lastFundingRate": "0.0001",
                "time": int(observed_at.timestamp() * 1000),
            }
        if "bookTicker" in path:
            return {"bidPrice": "99.99", "askPrice": "100.01"}
        raise AssertionError(path)

    monkeypatch.setattr(module, "_fetch_json", fake_fetch)
    row = module._symbol_row(
        "TESTUSDT",
        {
            "status": "TRADING",
            "contractType": "PERPETUAL",
            "filters": [
                {
                    "filterType": "LOT_SIZE",
                    "minQty": "0.01",
                    "stepSize": "0.01",
                },
                {
                    "filterType": "MARKET_LOT_SIZE",
                    "minQty": "0.001",
                    "stepSize": "0.001",
                },
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ],
        },
        [],
        observed_at,
    )

    assert row["public_facts_ready"] is True
    assert row["facts"]["min_qty"] == "0.001"
    assert row["facts"]["qty_step"] == "0.001"
    assert row["facts"]["quantity_rule_source"] == "MARKET_LOT_SIZE"
    assert row["facts"]["order_rule_surface"] == "market_entry"
