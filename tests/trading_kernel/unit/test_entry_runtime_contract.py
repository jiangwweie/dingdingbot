from pathlib import Path

import pytest

from src.trading_kernel.infrastructure.entry_runtime_contract import (
    ENTRY_ACTION_FACT_VALIDITY_MS,
    ENTRY_TIMEOUT_SECONDS,
    require_entry_runtime_contract,
)


@pytest.mark.parametrize("timeout,validity", [(5, 5000), (10, 5000), (5, 30000), (20, 30000)])
def test_live_entry_refuses_uncertified_read_budget(timeout, validity):
    with pytest.raises(ValueError, match="Entry runtime"):
        require_entry_runtime_contract(timeout_seconds=timeout, validity_ms=validity)


def test_entry_contract_keeps_send_authority_separate():
    from src.trading_kernel.domain.directional_risk import ENTRY_SEND_WINDOW_MS

    require_entry_runtime_contract(timeout_seconds=10, validity_ms=30000)
    assert ENTRY_TIMEOUT_SECONDS == 10
    assert ENTRY_ACTION_FACT_VALIDITY_MS == 30000
    assert ENTRY_SEND_WINDOW_MS == 5000


def test_manual_install_loads_entry_budget_after_shared_environment(tmp_path):
    from scripts.trading_kernel.manual_runtime_installation import (
        install_entry_runtime_config,
    )

    release = Path(__file__).resolve().parents[3]
    install_entry_runtime_config(release, etc=tmp_path)
    values = (tmp_path / "brc/trading-kernel-entry.env").read_text()
    assert values == "TRADING_KERNEL_TIMEOUT_SECONDS=10\nTRADING_KERNEL_ACTION_FACT_VALIDITY_MS=30000\n"
    dropin = (tmp_path / "systemd/system/brc-trading-kernel-entry-worker.service.d/entry-runtime.conf").read_text()
    assert "EnvironmentFile=/etc/brc/trading-kernel-entry.env" in dropin
    assert not list((tmp_path / "systemd/system").glob("*lifecycle*.service.d/*"))

