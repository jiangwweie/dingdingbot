from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_controlled_exit_adapters_have_one_exchange_writer() -> None:
    native = (ROOT / "scripts/trading_kernel/request_controlled_exit.py").read_text()
    bridge = (
        ROOT / "scripts/trading_kernel/request_controlled_exit_0002_bridge.py"
    ).read_text()

    for source in (native, bridge):
        assert "CcxtVenueAdapter" not in source
        assert "build_binance_usdm_venue_adapter" not in source
        assert "create_order" not in source
        assert "cancel_order" not in source
    assert "request_exit" in bridge
    assert "UPDATE brc_trade" not in bridge
    assert "DELETE FROM brc_trade" not in bridge
    assert "INSERT INTO brc_trade" not in bridge
