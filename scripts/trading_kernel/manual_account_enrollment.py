#!/usr/bin/env python3
"""Root-side fresh manual account enrollment; stdin secrets, stdout Owner-only reply."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.manual_account_setup import (
    BinanceManualAccountReader,
    ManualAccountCredentials,
    verify_manual_account,
)


def setup_local_account(credentials: ManualAccountCredentials) -> dict:
    """Root-only setup; no trading process starts and no exchange writes exist."""
    import os
    from pathlib import Path

    import pyotp
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError

    from scripts.trading_kernel.manual_host_bootstrap import ROOT, write_private

    if os.geteuid() != 0:
        raise ValueError("root setup required")
    if Path("/etc/brc/product-id").read_text().strip() != "brc-app-manual-v1":
        raise ValueError("manual product identity differs")
    if (
        not Path("/etc/brc/trading-kernel.write-fenced").is_file()
        or Path("/opt/brc/current").exists()
    ):
        raise ValueError("fresh fenced installation required")
    if not (ROOT / "database-complete.json").is_file():
        raise ValueError("database foundation is not ready")
    result = asyncio.run(
        verify_manual_account(BinanceManualAccountReader(credentials), credentials)
    )
    exchange = ROOT / "exchange-credentials.json"
    if exchange.exists():
        old = json.loads(exchange.read_text())
        if any(
            old[k] != v
            for k, v in {
                "expected_uid": credentials.expected_uid,
                "api_key": credentials.api_key.get_secret_value(),
                "api_secret": credentials.api_secret.get_secret_value(),
            }.items()
        ):
            raise ValueError(
                "existing account credentials differ; rotation is not implicit"
            )
    else:
        write_private(
            exchange,
            json.dumps(
                {
                    "expected_uid": credentials.expected_uid,
                    "api_key": credentials.api_key.get_secret_value(),
                    "api_secret": credentials.api_secret.get_secret_value(),
                },
                sort_keys=True,
            )
            + "\n",
        )
    directory = Path("/etc/brc/owner-console-credentials")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    hasher = PasswordHasher()
    existing = directory / "owner_password_hash"
    if existing.exists():
        try:
            hasher.verify(
                existing.read_text(), credentials.owner_password.get_secret_value()
            )
        except (VerificationError, InvalidHashError):
            raise ValueError("existing Owner authentication differs") from None
    else:
        write_private(
            existing, hasher.hash(credentials.owner_password.get_secret_value())
        )
    write_private(directory / "owner_username", credentials.owner_username)
    if not (directory / "owner_totp_seed").exists():
        write_private(directory / "owner_totp_seed", pyotp.random_base32())
    if not (directory / "session_signing_key").exists():
        import secrets

        write_private(directory / "session_signing_key", secrets.token_urlsafe(64))
    account_id = "binance-manual-" + credentials.expected_uid
    write_private(directory / "account_id", account_id)
    write_private(directory / "database_dsn", (ROOT / "read-dsn").read_text().strip())
    write_private(
        directory / "control_database_dsn", (ROOT / "control-dsn").read_text().strip()
    )
    write_private(
        ROOT / "verified-account.json",
        json.dumps(
            {
                "account_id": account_id,
                "exchange_uid": credentials.expected_uid,
                **result,
            },
            sort_keys=True,
        )
        + "\n",
        overwrite=True,
    )
    uri = pyotp.TOTP((directory / "owner_totp_seed").read_text()).provisioning_uri(
        name=credentials.owner_username, issuer_name="BRC Manual Seoul"
    )
    return {
        **result,
        "account_configured": True,
        "entry_enabled": False,
        "totp_enrollment_uri": uri,
    }


def main():
    import sys

    if sys.argv[1:] != ["--setup"]:
        raise ValueError("explicit setup action required")
    raw = sys.stdin.buffer.read(16385)
    if len(raw) > 16384:
        raise ValueError("setup input exceeds bound")
    value = ManualAccountCredentials.model_validate_json(raw)
    if len(value.owner_password.get_secret_value()) < 12:
        raise ValueError("Owner password must contain at least 12 characters")
    print(json.dumps(setup_local_account(value), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - never echo credential-bearing tracebacks.
        allowed = type(error) is ValueError
        message = (
            str(error)
            if allowed
            else "manual account setup failed; secret output withheld"
        )
        print(json.dumps({"status": "blocked", "message": message}))
        raise SystemExit(1) from None
