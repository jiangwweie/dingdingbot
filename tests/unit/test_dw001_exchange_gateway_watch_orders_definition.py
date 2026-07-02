from __future__ import annotations

import ast
from pathlib import Path


def test_exchange_gateway_has_single_watch_orders_definition():
    source_path = Path("src/infrastructure/exchange_gateway.py")
    module = ast.parse(source_path.read_text(encoding="utf-8"))

    exchange_gateway_class = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "ExchangeGateway"
    )
    watch_orders_defs = [
        node
        for node in exchange_gateway_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "watch_orders"
    ]

    assert len(watch_orders_defs) == 1
