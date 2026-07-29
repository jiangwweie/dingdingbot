from __future__ import annotations

import pytest

import scripts.trading_kernel.abandon_strategy_universe as abandon
from src.trading_kernel.application.abandon_strategy_universe import (
    AbandonStrategyUniverseRequest,
)


def test_abandon_cli_requires_exact_identity_and_stable_reason() -> None:
    parser = abandon._parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--database-url",
                "postgresql+asyncpg://user:secret@localhost/kernel",
                "--reason-code",
                "warming_timeout",
            ]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--database-url",
                "postgresql+asyncpg://user:secret@localhost/kernel",
                "--universe-version-id",
                "universe:exact",
            ]
        )


def test_abandon_cli_delegates_only_the_exact_database_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: list[object] = []

    async def record(database_url: str, request: object) -> None:
        captured.extend((database_url, request))

    monkeypatch.setattr(abandon, "_abandon", record)

    assert (
        abandon.main(
            [
                "--database-url",
                "postgresql+asyncpg://user:secret@localhost/kernel",
                "--universe-version-id",
                "universe:exact",
                "--reason-code",
                "warming_timeout",
                "--attempted-at-ms",
                "1000",
            ]
        )
        == 0
    )

    assert captured[0] == "postgresql+asyncpg://user:secret@localhost/kernel"
    request = captured[1]
    assert isinstance(request, AbandonStrategyUniverseRequest)
    assert request.universe_version_id == "universe:exact"
    assert request.reason_code == "warming_timeout"
    assert request.attempted_at_ms == 1000
    assert capsys.readouterr().out == "status=abandoned universe_version_id=universe:exact\n"
