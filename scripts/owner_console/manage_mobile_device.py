#!/usr/bin/env python3
"""Independent Owner terminal binding/revocation; no trade or Resume authority."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.domain.product_identity import PRODUCT_ID
from src.trading_kernel.infrastructure.pg_owner_device_repository import (
    PostgresOwnerDeviceRepository,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


def require_private_destination(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or path.exists():
        raise ValueError("new absolute private output path required")
    if not path.parent.is_dir() or path.parent.stat().st_mode & 0o077:
        raise ValueError("private output directory required")


async def execute(args) -> dict:
    if (
        os.geteuid() != 0
        or Path("/etc/brc/product-id").read_text().strip() != PRODUCT_ID
    ):
        raise ValueError("independent Owner terminal required")
    current = Path("/opt/brc/current").resolve()
    if current != ROOT or not (ROOT / ".brc-runtime-commit").is_file():
        raise ValueError("installed release required")
    if args.command == "bind":
        require_private_destination(args.output)
    e = create_async_engine(
        Path("/etc/brc/manual-install/admin-dsn").read_text().strip()
    )
    try:
        async with e.begin() as c:
            schema = await c.scalar(text("SELECT version_num FROM alembic_version"))
            commit = await c.scalar(
                text(
                    "SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='runtime_commit'"
                )
            )
            if (
                schema != CURRENT_SCHEMA_REVISION
                or commit != (ROOT / ".brc-runtime-commit").read_text().strip()
            ):
                raise ValueError("installed authority mismatch")
            now = int(time.time() * 1000)
            r = PostgresOwnerDeviceRepository(c)
            if args.command == "revoke":
                await r.revoke(device_id=args.device_id, now_ms=now)
                return {
                    "status": "revoked",
                    "device_id": args.device_id,
                    "exchange_writes": 0,
                }
            # Only an independent admin process creates a binding grant. Never
            # print the bearer into command output or accept it on argv.
            token = await r.issue_binding(
                owner_identity=args.owner, replace_device=args.replace, now_ms=now
            )
            fd = os.open(
                args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "w") as stream:
                stream.write(token + "\n")
        return {
            "status": "binding_written",
            "expires_in_seconds": 600,
            "output": str(args.output),
            "exchange_writes": 0,
        }
    finally:
        await e.dispose()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("bind")
    b.add_argument("--owner", required=True)
    b.add_argument("--replace", action="store_true")
    b.add_argument("--output", required=True, type=Path)
    r = sub.add_parser("revoke")
    r.add_argument("--device-id", required=True)
    args = p.parse_args()
    with open("/run/brc-owner-device-admin.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(asyncio.run(execute(args))))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - protected credential paths never print traces.
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
