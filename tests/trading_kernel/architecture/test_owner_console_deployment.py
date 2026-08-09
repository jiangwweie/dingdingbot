from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_owner_console_service_is_unix_socket_only_and_resource_bounded() -> None:
    service = _read("deploy/owner-console/systemd/brc-owner-console-api.service")
    resource_slice = _read("deploy/owner-console/systemd/brc-owner-console.slice")

    assert "--uds /run/brc-owner-console/api.sock" in service
    assert "EnvironmentFile=" not in service
    assert "TRADING_KERNEL_API_KEY" not in service
    assert "LoadCredentialEncrypted=database_dsn:" in service
    assert "LoadCredentialEncrypted=account_id:" in service
    assert "CPUQuota=25%" in resource_slice
    assert "MemoryMax=256M" in resource_slice
    assert "TasksMax=32" in resource_slice


def test_owner_console_nginx_include_is_same_origin_and_manual_cache_safe() -> None:
    source = _read("deploy/owner-console/nginx/owner-console.locations.conf")

    assert "try_files $uri $uri/ /index.html" in source
    assert "proxy_pass http://unix:/run/brc-owner-console/api.sock" in source
    assert "location = /api/owner/v1/auth/login" in source
    assert "limit_req zone=brc_owner_login burst=5 nodelay" in source
    assert "proxy_no_cache 1" in source
    assert 'Cache-Control "no-store"' in source
    assert "autoindex off" in source


def test_owner_console_postgresql_role_is_read_only_and_select_only() -> None:
    source = _read(
        "deploy/owner-console/postgresql/owner-console-read-role.sql"
    )

    assert "default_transaction_read_only = on" in source
    assert "statement_timeout = '3s'" in source
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA public" in source
    assert "GRANT INSERT" not in source
    assert "GRANT UPDATE" not in source
    assert "GRANT DELETE" not in source


def test_owner_console_units_do_not_change_kernel_worker_membership() -> None:
    kernel_units = {
        path.name
        for path in (REPO_ROOT / "deploy" / "systemd").iterdir()
        if path.is_file()
    }

    assert kernel_units == {
        "brc-trading-kernel.slice",
        "brc-trading-kernel-observation-worker.service",
        "brc-trading-kernel-entry-worker.service",
        "brc-trading-kernel-lifecycle-worker.service",
        "brc-trading-kernel-reconciliation-worker.service",
    }
