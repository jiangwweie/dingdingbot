import pytest

from scripts.trading_kernel.tokyo_clean_manual import require_clean_source


def source(**changes):
    return {
        "machine_id": "1c3442ab300e405e945a469ed8a12593",
        "source_commit": "574f5cf3642ca652798b552ba1269d0ae3db1b55",
        "source_schema": "0016_exit_regime_v1",
        "account_id": "owner-subaccount-runtime-v0",
        "entry_enabled": False,
        "positions": 0,
        "orders": 0,
        "commands": 0,
        "active_tickets": 0,
        "incidents": 0,
        "reservations": 0,
        "writers_active": False,
        "backup_verified": True,
        **changes,
    }


@pytest.mark.parametrize(
    "fault",
    [
        "machine_id",
        "source_commit",
        "source_schema",
        "account_id",
        "entry_enabled",
        "positions",
        "orders",
        "commands",
        "active_tickets",
        "incidents",
        "reservations",
        "writers_active",
        "backup_verified",
    ],
)
def test_clean_replacement_rejects_every_binding_activity_or_backup_fault(fault):
    bad = (
        "wrong"
        if fault in {"machine_id", "source_commit", "source_schema", "account_id"}
        else False
        if fault == "backup_verified"
        else 1
    )
    with pytest.raises(ValueError):
        require_clean_source(source(**{fault: bad}))


def test_clean_replacement_requires_explicit_paused_stopped_flat_backup():
    require_clean_source(source())


def test_notification_binding_rejects_nonapproved_site_or_origin(monkeypatch):
    from src.trading_kernel.infrastructure.pg_notice_outbox import (
        notice_console_url,
        notice_site_label,
    )

    monkeypatch.setenv("TRADING_KERNEL_NOTICE_SITE", "东京")
    monkeypatch.setenv("TRADING_KERNEL_CONSOLE_ORIGIN", "https://jiaoyingpan.cloud")
    assert (
        notice_site_label() == "东京"
        and notice_console_url() == "https://jiaoyingpan.cloud/trading/"
    )
    monkeypatch.setenv("TRADING_KERNEL_CONSOLE_ORIGIN", "https://unrelated.example")
    with pytest.raises(ValueError):
        notice_console_url()
    monkeypatch.setenv("TRADING_KERNEL_NOTICE_SITE", "arbitrary")
    with pytest.raises(ValueError):
        notice_site_label()
