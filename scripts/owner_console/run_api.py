"""Start the Owner Console from exact systemd encrypted credentials."""

from __future__ import annotations

import math
import os
import stat
import sys
from collections.abc import Mapping
from pathlib import Path

import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.interfaces.owner_console_http.app import (
    create_owner_console_app,
)
from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    OwnerConsoleSettings,
)

_CREDENTIAL_NAMES = frozenset(
    {
        "owner_username",
        "owner_password_hash",
        "owner_totp_seed",
        "session_signing_key",
        "database_dsn",
        "account_id",
    }
)
_DEFAULT_MARKET_TIMEOUT_SECONDS = 5.0
_MAX_MARKET_TIMEOUT_SECONDS = 60.0
_DEFAULT_UNIX_SOCKET = "/run/brc-owner-console/api.sock"
_MAX_CREDENTIAL_BYTES = 16_384


def load_settings(environ: Mapping[str, str]) -> OwnerConsoleSettings:
    """Load only the declared systemd credentials and bounded timeout setting."""

    credentials_directory = environ.get("CREDENTIALS_DIRECTORY")
    if not isinstance(credentials_directory, str) or not credentials_directory:
        raise ValueError("CREDENTIALS_DIRECTORY is required")

    credentials = _read_credentials(Path(credentials_directory))
    return OwnerConsoleSettings(
        database_dsn=credentials["database_dsn"],
        account_id=credentials["account_id"],
        market_timeout_seconds=_market_timeout_seconds(environ),
        auth=OwnerAuthSettings(
            username=credentials["owner_username"],
            password_hash=credentials["owner_password_hash"],
            totp_seed=credentials["owner_totp_seed"],
            session_signing_key=credentials["session_signing_key"],
        ),
    )


def run(settings: OwnerConsoleSettings, *, uds: str = _DEFAULT_UNIX_SOCKET) -> None:
    """Run exactly one proxy-header-disabled Uvicorn worker on the Unix Socket."""

    uvicorn.run(
        create_owner_console_app(settings),
        uds=uds,
        workers=1,
        proxy_headers=False,
        access_log=True,
    )


def _read_credentials(directory: Path) -> dict[str, str]:
    try:
        directory_status = directory.lstat()
    except OSError as error:
        raise ValueError("credential directory is unavailable") from error
    if not stat.S_ISDIR(directory_status.st_mode):
        raise ValueError("credential directory must be a directory")

    open_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(directory, open_flags)
    except OSError as error:
        raise ValueError("credential directory is unavailable") from error

    try:
        try:
            credential_names = frozenset(os.listdir(directory_fd))
        except OSError as error:
            raise ValueError("credential directory cannot be enumerated") from error
        if credential_names != _CREDENTIAL_NAMES:
            raise ValueError("credential directory names do not match the declared set")
        return {
            name: _read_credential(directory_fd, name)
            for name in _CREDENTIAL_NAMES
        }
    finally:
        os.close(directory_fd)


def _read_credential(directory_fd: int, name: str) -> str:
    try:
        before_open = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        raise ValueError("credential is unavailable") from error
    if not stat.S_ISREG(before_open.st_mode):
        raise ValueError("credential must be a regular file")
    if before_open.st_mode & (stat.S_IRGRP | stat.S_IROTH):
        raise ValueError("credential must not be group or world readable")
    if before_open.st_size > _MAX_CREDENTIAL_BYTES:
        raise ValueError("credential exceeds the permitted size")

    open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        credential_fd = os.open(name, open_flags, dir_fd=directory_fd)
    except OSError as error:
        raise ValueError("credential is unavailable") from error
    try:
        after_open = os.fstat(credential_fd)
        if (
            after_open.st_dev != before_open.st_dev
            or after_open.st_ino != before_open.st_ino
            or not stat.S_ISREG(after_open.st_mode)
        ):
            raise ValueError("credential changed while being read")
        if after_open.st_mode & (stat.S_IRGRP | stat.S_IROTH):
            raise ValueError("credential must not be group or world readable")
        if after_open.st_size > _MAX_CREDENTIAL_BYTES:
            raise ValueError("credential exceeds the permitted size")
        try:
            data = os.read(credential_fd, _MAX_CREDENTIAL_BYTES + 1)
            value = data.decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError("credential is not valid UTF-8") from error
    finally:
        os.close(credential_fd)
    if len(data) > _MAX_CREDENTIAL_BYTES or not value.strip():
        raise ValueError("credential must be nonblank and bounded")
    return value


def _market_timeout_seconds(environ: Mapping[str, str]) -> float:
    raw_value = environ.get("OWNER_CONSOLE_MARKET_TIMEOUT_SECONDS")
    if raw_value is None:
        return _DEFAULT_MARKET_TIMEOUT_SECONDS
    if not isinstance(raw_value, str):
        raise TypeError("market timeout must be a string")
    try:
        timeout_seconds = float(raw_value)
    except ValueError as error:
        raise ValueError("market timeout must be numeric") from error
    if not (
        math.isfinite(timeout_seconds)
        and 0 < timeout_seconds <= _MAX_MARKET_TIMEOUT_SECONDS
    ):
        raise ValueError("market timeout is outside its permitted range")
    return timeout_seconds


def main() -> None:
    """Load systemd credentials and start the fixed Unix Socket server."""

    run(load_settings(os.environ))


if __name__ == "__main__":
    main()
