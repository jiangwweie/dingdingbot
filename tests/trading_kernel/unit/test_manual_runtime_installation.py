import pytest

from scripts.trading_kernel.manual_runtime_installation import (
    check_installation_binding,
    install_console_files,
    require_fresh_state,
)


def binding():
    return {
        "product_id": "brc-app-manual-v1",
        "account_id": "binance-manual-12345",
        "exchange_uid": "12345",
        "system_identifier": "123456789",
        "database": "brc_manual_kernel",
        "schema_revision": "0017_app_management_observation",
        "commit": "a" * 40,
    }


@pytest.mark.parametrize(
    "changed",
    [
        {"accounts": ["other"]},
        {"entry_enabled": True},
        {"exchange_writes": True},
        {"capability_commit": "b" * 40},
        {"retired_control": "enabled"},
        {"retired_install_event": False},
        {"has_tickets": True},
        {"has_commands": True},
        {"has_positions": True},
        {"has_reservations": True},
        {"system_identifier": "wrong"},
        {"schema_revision": "old"},
    ],
)
def test_existing_account_or_writes_cannot_be_taken_over(changed):
    state = {
        "system_identifier": "123",
        "database": "manual",
        "schema_revision": "head",
        "accounts": ["account"],
        "entry_enabled": False,
        "exchange_writes": False,
        "capability_commit": "a" * 40,
        "metadata": {"runtime_commit": "a" * 40},
        "retired_control": "paused",
        "retired_install_event": True,
        "has_tickets": False,
        "has_commands": False,
        "has_positions": False,
        "has_reservations": False,
    }
    with pytest.raises(ValueError):
        require_fresh_state(
            {**state, **changed},
            receipt={"commit": "a" * 40, "schema_revision": "head"},
            foundation={"system_identifier": "123", "database": "manual"},
            account_id="account",
        )


@pytest.mark.parametrize("field", list(binding()))
def test_any_changed_binding_refuses_installation(field):
    expected = binding()
    with pytest.raises(ValueError, match="binding"):
        check_installation_binding(expected, {**expected, field: "wrong"})


def test_console_install_keeps_all_four_trade_workers_disabled(tmp_path):
    release = tmp_path / "release"
    runtime = release / "deploy/runtime"
    runtime.mkdir(parents=True)
    (runtime / "entry.env").write_text("TRADING_KERNEL_TIMEOUT_SECONDS=10\nTRADING_KERNEL_ACTION_FACT_VALIDITY_MS=30000\n")
    kernel_units = release / "deploy/systemd"
    kernel_units.mkdir(parents=True)
    for role in ("observation", "entry", "lifecycle", "reconciliation"):
        (kernel_units / f"brc-trading-kernel-{role}-worker.service").write_text(
            "[Service]\n"
        )
    (kernel_units / "brc-trading-kernel.slice").write_text("[Slice]\n")
    owner = release / "deploy/owner-console/systemd"
    owner.mkdir(parents=True)
    (owner / "brc-owner-console-api.service").write_text("[Service]\n")
    (owner / "brc-owner-console.slice").write_text("[Slice]\n")
    nginx = release / "deploy/owner-console/nginx"
    nginx.mkdir(parents=True)
    for name in ("owner-console.locations.conf", "00-brc-owner-console-limit.conf"):
        (nginx / name).write_text(
            "location ^~ /api/owner/v1/ {\n}\n"
            if name.startswith("owner-console.")
            else "# limit\n"
        )
    install_console_files(release, etc=tmp_path / "etc")
    dropin = (
        tmp_path
        / "etc/systemd/system/brc-owner-console-api.service.d/manual-origin.conf"
    ).read_text()
    assert "OWNER_CONSOLE_PUBLIC_ORIGIN=https://manual.jiaoyingpan.cloud" in dropin
    assert not list((tmp_path / "etc").rglob("multi-user.target.wants/*"))
    assert not list((tmp_path / "etc").rglob("*.timer"))
    assert "TRADING_KERNEL_API_SECRET" not in dropin
    assert (tmp_path / "etc/nginx/snippets/brc-manual-owner.locations.conf").exists()
    assert (
        "limit_except GET { deny all; }"
        in (tmp_path / "etc/nginx/snippets/brc-manual-owner.locations.conf").read_text()
    )
