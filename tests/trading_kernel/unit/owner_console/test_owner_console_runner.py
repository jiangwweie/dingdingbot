"""Focused systemd credential and Unix Socket runner contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.owner_console import run_api as runner

_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=1$lMxt0+Hd+L/ssBunZuF9wQ$"
    "fDYQ0aYM1T1UUssc0yd0nvsClUtTkI9JNZpfOCt4C5o"
)
_CREDENTIAL_VALUES = {
    "owner_username": "owner",
    "owner_password_hash": _PASSWORD_HASH,
    "owner_totp_seed": "JBSWY3DPEHPK3PXP",
    "session_signing_key": "s" * 64,
    "database_dsn": "postgresql+asyncpg://owner:secret@127.0.0.1/brc",
    "control_database_dsn": "postgresql+asyncpg://owner_control:secret@127.0.0.1/brc",
    "account_id": "subaccount-test",
}


def test_runner_reads_only_exact_systemd_credentials(tmp_path: Path) -> None:
    _write_credentials(tmp_path)

    settings = runner.load_settings(
        {"CREDENTIALS_DIRECTORY": str(tmp_path)},
    )

    assert settings.auth.username == "owner"
    assert settings.account_id == "subaccount-test"
    assert settings.market_timeout_seconds == 5.0


@pytest.mark.parametrize(
    "mutation",
    (
        "missing",
        "unexpected",
        "symlink",
        "group_readable",
        "empty",
    ),
)
def test_runner_rejects_credential_authority_boundary_violations(
    tmp_path: Path,
    mutation: str,
) -> None:
    _write_credentials(tmp_path)
    target = tmp_path / "account_id"
    if mutation == "missing":
        target.unlink()
    elif mutation == "unexpected":
        (tmp_path / "TRADING_KERNEL_API_SECRET").write_text("forbidden")
    elif mutation == "symlink":
        target.unlink()
        target.symlink_to(tmp_path / "owner_username")
    elif mutation == "group_readable":
        target.chmod(0o640)
    elif mutation == "empty":
        target.write_text("")
    else:  # pragma: no cover - parameter values are static above
        raise AssertionError(f"unknown test mutation: {mutation}")

    with pytest.raises(ValueError):
        runner.load_settings({"CREDENTIALS_DIRECTORY": str(tmp_path)})


def test_runner_rechecks_opened_credential_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_credentials(tmp_path)
    original_open = runner.os.open

    def open_then_make_group_readable(
        path: str | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
        if path == "account_id":
            (tmp_path / "account_id").chmod(0o640)
        return descriptor

    monkeypatch.setattr(runner.os, "open", open_then_make_group_readable)

    with pytest.raises(ValueError):
        runner.load_settings({"CREDENTIALS_DIRECTORY": str(tmp_path)})


@pytest.mark.parametrize(
    ("value", "expected"),
    ((None, 5.0), ("0.5", 0.5), ("60", 60.0)),
)
def test_runner_allows_only_bounded_valid_market_timeout(
    tmp_path: Path,
    value: str | None,
    expected: float,
) -> None:
    _write_credentials(tmp_path)
    environ = {"CREDENTIALS_DIRECTORY": str(tmp_path)}
    if value is not None:
        environ["OWNER_CONSOLE_MARKET_TIMEOUT_SECONDS"] = value

    assert runner.load_settings(environ).market_timeout_seconds == expected


@pytest.mark.parametrize("value", ("0", "61", "nan", "unexpected"))
def test_runner_rejects_invalid_market_timeout(tmp_path: Path, value: str) -> None:
    _write_credentials(tmp_path)

    with pytest.raises(ValueError):
        runner.load_settings(
            {
                "CREDENTIALS_DIRECTORY": str(tmp_path),
                "OWNER_CONSOLE_MARKET_TIMEOUT_SECONDS": value,
            }
        )


def test_runner_requires_unix_socket_and_one_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        runner.uvicorn,
        "run",
        lambda app, **kwargs: captured.update(app=app, **kwargs),
    )

    runner.run(_settings_fixture(), uds="/run/brc-owner-console/api.sock")

    assert captured["uds"] == "/run/brc-owner-console/api.sock"
    assert captured["workers"] == 1
    assert captured["proxy_headers"] is False
    assert captured["access_log"] is True
    assert "host" not in captured
    assert "port" not in captured


def test_runner_main_honors_explicit_unix_socket_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    settings = _settings_fixture()
    monkeypatch.setattr(
        runner.sys,
        "argv",
        ["run_api.py", "--uds", "/tmp/owner.sock"],
    )
    monkeypatch.setattr(runner, "load_settings", lambda environ: settings)

    def capture_run(
        supplied_settings: runner.OwnerConsoleSettings,
        *,
        uds: str,
    ) -> None:
        captured.update(settings=supplied_settings, uds=uds)

    monkeypatch.setattr(runner, "run", capture_run)

    runner.main()

    assert captured == {"settings": settings, "uds": "/tmp/owner.sock"}


def _write_credentials(directory: Path) -> None:
    for name, value in _CREDENTIAL_VALUES.items():
        credential = directory / name
        credential.write_text(value, encoding="utf-8")
        credential.chmod(0o600)


def _settings_fixture() -> runner.OwnerConsoleSettings:
    return runner.OwnerConsoleSettings(
        database_dsn=_CREDENTIAL_VALUES["database_dsn"],
        control_database_dsn=_CREDENTIAL_VALUES["control_database_dsn"],
        account_id=_CREDENTIAL_VALUES["account_id"],
        auth=runner.OwnerAuthSettings(
            username=_CREDENTIAL_VALUES["owner_username"],
            password_hash=_CREDENTIAL_VALUES["owner_password_hash"],
            totp_seed=_CREDENTIAL_VALUES["owner_totp_seed"],
            session_signing_key=_CREDENTIAL_VALUES["session_signing_key"],
        ),
    )
