from __future__ import annotations

import pytest

import scripts.trading_kernel.bootstrap_strategy_universes as bootstrap
from src.trading_kernel.application.read_strategy_universe_status import (
    StrategyUniverseMemberStatus,
    StrategyUniverseStatusResult,
    StrategyUniverseVersionStatus,
)


def test_bootstrap_manifest_is_exactly_the_approved_six_events_and_seven_members() -> None:
    """The operation has no operator-supplied universe, venue, or asset scope."""

    assert bootstrap.EVENT_ORDER == (
        "CPM-LONG",
        "MPG-LONG",
        "MI-LONG",
        "SOR-LONG",
        "SOR-SHORT",
        "BRF2-SHORT",
    )
    assert bootstrap.INITIAL_MEMBERS == (
        "binance-usdm:ADAUSDT:perpetual",
        "binance-usdm:BNBUSDT:perpetual",
        "binance-usdm:BTCUSDT:perpetual",
        "binance-usdm:DOGEUSDT:perpetual",
        "binance-usdm:ETHUSDT:perpetual",
        "binance-usdm:SOLUSDT:perpetual",
        "binance-usdm:XRPUSDT:perpetual",
    )
    assert "AVAX" not in " ".join(bootstrap.INITIAL_MEMBERS)
    assert "--instrument" not in bootstrap._parser().format_help()


def test_tradfi_bootstrap_manifest_has_two_events_and_eight_equity_members() -> None:
    event_specs, members = bootstrap._manifest_for_profile(
        "tradfi-equity-usdm-v1"
    )

    assert tuple(event_id for event_id, _event_spec_id in event_specs) == (
        "SOR-US-LONG-15M",
        "SOR-US-SHORT-15M",
    )
    assert members == (
        "binance-usdm:AAPLUSDT:perpetual",
        "binance-usdm:AMZNUSDT:perpetual",
        "binance-usdm:GOOGLUSDT:perpetual",
        "binance-usdm:METAUSDT:perpetual",
        "binance-usdm:MSFTUSDT:perpetual",
        "binance-usdm:NVDAUSDT:perpetual",
        "binance-usdm:SNDKUSDT:perpetual",
        "binance-usdm:TSLAUSDT:perpetual",
    )
    bootstrap._validate_static_manifest("tradfi-equity-usdm-v1")


def test_bootstrap_refuses_a_registry_that_no_longer_matches_the_fixed_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "registered_strategy_contracts", lambda: ())

    with pytest.raises(bootstrap.BootstrapBlocked, match="registry_event_manifest"):
        bootstrap._validate_static_manifest()


def test_bootstrap_selects_the_installed_version_during_registry_replacement() -> None:
    member = StrategyUniverseMemberStatus(
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        certification_status="eligible",
        warm_ready=True,
        monitor_status="running",
        blocker_code=None,
    )
    status = StrategyUniverseStatusResult(
        runtime_profile_id="tiny-live-v1",
        universes=(
            StrategyUniverseVersionStatus(
                event_id="SOR-LONG",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
                universe_version_id="universe:sor-long:v2:active",
                semantic_digest="sha256:" + "1" * 64,
                lifecycle_state="active",
                current_generation=1,
                members=(member,),
            ),
            StrategyUniverseVersionStatus(
                event_id="SOR-LONG",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v3",
                universe_version_id="universe:sor-long:v3:warming",
                semantic_digest="sha256:" + "2" * 64,
                lifecycle_state="warming",
                current_generation=None,
                members=(member,),
            ),
        ),
    )

    selected = bootstrap._select_bootstrap_universe(
        status,
        event_id="SOR-LONG",
        universe_version_id="universe:sor-long:v3:warming",
    )

    assert selected.event_spec_id == "event_spec:SOR-001:SOR-LONG:v3"
    assert selected.lifecycle_state == "warming"


def test_prepare_only_cli_creates_the_batch_without_running_full_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[str, str]] = []

    async def prepare(
        database_url: str,
        *,
        runtime_profile_id: str,
        now_ms,
    ) -> str:
        assert now_ms() > 0
        calls.append((database_url, runtime_profile_id))
        return "certification-batch:test"

    async def forbidden_bootstrap(*_args, **_kwargs):
        raise AssertionError("full bootstrap must not run in prepare-only mode")

    monkeypatch.setattr(bootstrap, "prepare_certification_batch", prepare)
    monkeypatch.setattr(bootstrap, "bootstrap_strategy_universes", forbidden_bootstrap)

    result = bootstrap.main(
        [
            "--database-url",
            "postgresql+asyncpg://localhost/test",
            "--runtime-profile-id",
            "tiny-live-v1",
            "--prepare-certification-batch-only",
        ]
    )

    assert result == 0
    assert calls == [
        ("postgresql+asyncpg://localhost/test", "tiny-live-v1")
    ]
    assert capsys.readouterr().out.strip() == (
        "status=prepared certification_batch_id=certification-batch:test"
    )


def test_refresh_only_cli_uses_the_exact_active_manifest(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catches refreshing an expired Batch through Universe reinstallation."""

    calls: list[tuple[str, str]] = []

    async def refresh(
        database_url: str,
        *,
        runtime_profile_id: str,
        now_ms,
    ) -> str:
        assert now_ms() > 0
        calls.append((database_url, runtime_profile_id))
        return "certification-batch:refreshed"

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("refresh-only mode must not install a Universe")

    monkeypatch.setattr(
        bootstrap,
        "refresh_active_certification_batch",
        refresh,
        raising=False,
    )
    monkeypatch.setattr(bootstrap, "prepare_certification_batch", forbidden)
    monkeypatch.setattr(bootstrap, "bootstrap_strategy_universes", forbidden)

    result = bootstrap.main(
        [
            "--database-url",
            "postgresql+asyncpg://localhost/test",
            "--runtime-profile-id",
            "tiny-live-v1",
            "--refresh-active-certification-batch-only",
        ]
    )

    assert result == 0
    assert calls == [
        ("postgresql+asyncpg://localhost/test", "tiny-live-v1")
    ]
    assert capsys.readouterr().out.strip() == (
        "status=refreshed certification_batch_id=certification-batch:refreshed"
    )


def test_certification_batch_only_modes_are_mutually_exclusive() -> None:
    """Catches ambiguous CLI execution of prepare and Active refresh together."""

    with pytest.raises(SystemExit):
        bootstrap._parser().parse_args(
            [
                "--runtime-profile-id",
                "tiny-live-v1",
                "--prepare-certification-batch-only",
                "--refresh-active-certification-batch-only",
            ]
        )
