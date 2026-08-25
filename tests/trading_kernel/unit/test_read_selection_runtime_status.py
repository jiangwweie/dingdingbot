from __future__ import annotations

import importlib

import pytest


def test_selection_runtime_status_cli_requires_exact_period_identity() -> None:
    module = importlib.import_module(
        "scripts.trading_kernel.read_selection_runtime_status"
    )
    parser = module._parser()

    args = parser.parse_args(
        [
            "--database-url",
            "postgresql+asyncpg://kernel:test@localhost/kernel",
            "--strategy-group-id",
            "SOR-001",
            "--selection-spec-id",
            "sor-dynamic-selection-v0",
            "--session-start-ms",
            "1800057600000",
        ]
    )
    request = module._request(args)

    assert request.strategy_group_id == "SOR-001"
    assert request.selection_spec_id == "sor-dynamic-selection-v0"
    assert request.session_start_ms == 1_800_057_600_000
    with pytest.raises(ValueError, match=r"postgresql\+asyncpg"):
        module._request(
            parser.parse_args(
                [
                    "--database-url",
                    "postgresql://kernel:test@localhost/kernel",
                    "--strategy-group-id",
                    "SOR-001",
                    "--selection-spec-id",
                    "sor-dynamic-selection-v0",
                    "--session-start-ms",
                    "1800057600000",
                ]
            )
        )
