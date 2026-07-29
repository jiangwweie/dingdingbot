from __future__ import annotations

import pytest

import scripts.trading_kernel.bootstrap_strategy_universes as bootstrap


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


def test_bootstrap_refuses_a_registry_that_no_longer_matches_the_fixed_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "registered_strategy_contracts", lambda: ())

    with pytest.raises(bootstrap.BootstrapBlocked, match="registry_event_manifest"):
        bootstrap._validate_static_manifest()
