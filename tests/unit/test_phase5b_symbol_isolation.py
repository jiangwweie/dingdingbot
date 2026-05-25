from __future__ import annotations

import ast
from pathlib import Path

from src.application.runtime_symbol_isolation_audit import (
    SymbolIsolationStatus,
    build_phase5b_symbol_isolation_audit,
)
from src.infrastructure.exchange_gateway import ExchangeGateway


def test_recent_order_updates_are_symbol_scoped_before_legacy_fallback():
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    eth = {
        "id": "same-exchange-id",
        "clientOrderId": "same-client-id",
        "symbol": "ETH/USDT:USDT",
    }
    btc = {
        "id": "same-exchange-id",
        "clientOrderId": "same-client-id",
        "symbol": "BTC/USDT:USDT",
    }

    gateway._remember_recent_order_update(eth)
    gateway._remember_recent_order_update(btc)

    eth_candidates = gateway._recent_order_update_candidates(
        "same-exchange-id",
        "same-client-id",
        expected_symbol="ETH/USDT:USDT",
    )
    btc_candidates = gateway._recent_order_update_candidates(
        "same-exchange-id",
        "same-client-id",
        expected_symbol="BTC/USDT:USDT",
    )

    assert eth_candidates[0]["symbol"] == "ETH/USDT:USDT"
    assert btc_candidates[0]["symbol"] == "BTC/USDT:USDT"


def test_order_watch_running_state_has_symbol_scope():
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)

    gateway._order_ws_running = True
    gateway._order_ws_running_symbols["ETH/USDT:USDT"] = True
    gateway._order_ws_running_symbols["BTC/USDT:USDT"] = False

    assert gateway._order_ws_running is True
    assert gateway._order_ws_running_symbols["ETH/USDT:USDT"] is True
    assert gateway._order_ws_running_symbols["BTC/USDT:USDT"] is False


def test_phase5b_symbol_isolation_audit_marks_multi_symbol_blocked():
    report = build_phase5b_symbol_isolation_audit()
    statuses = {check.check_id: check.status for check in report.checks}

    assert report.multi_symbol_runtime_authorized is False
    assert statuses["P5B-SYM-001"] == SymbolIsolationStatus.PASS
    assert statuses["P5B-SYM-002"] == SymbolIsolationStatus.PASS
    assert statuses["P5B-SYM-005"] == SymbolIsolationStatus.BLOCKED
    assert report.verdict.endswith("multi_symbol_runtime_still_blocked")


def test_symbol_isolation_audit_does_not_import_io_frameworks():
    forbidden = {"ccxt", "aiohttp", "requests", "fastapi", "yaml", "sqlalchemy"}
    tree = ast.parse(
        Path("src/application/runtime_symbol_isolation_audit.py").read_text(
            encoding="utf-8"
        )
    )
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert imports.isdisjoint(forbidden)
