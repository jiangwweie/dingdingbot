#!/usr/bin/env python3
"""Bound manual-account initialization and Console installation; no ENTRY activation."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trading_kernel.manual_host_bootstrap import (
    ROOT,
    check_host_identity,
    host_facts,
    run,
    validate_certificates,
    write_private,
)

ORIGIN = "https://manual.jiaoyingpan.cloud"


def check_installation_binding(expected: dict, actual: dict) -> None:
    keys = (
        "product_id",
        "account_id",
        "exchange_uid",
        "system_identifier",
        "database",
        "schema_revision",
        "commit",
    )
    if any(
        not expected.get(key) or expected.get(key) != actual.get(key) for key in keys
    ):
        raise ValueError("manual installation binding differs")


def install_console_files(release: Path, *, etc: Path = Path("/etc")) -> None:
    """Install certified canonical units; no service is enabled or started here."""
    units = etc / "systemd/system"
    units.mkdir(parents=True, exist_ok=True)
    for source in (release / "deploy/systemd").glob("*"):
        shutil.copyfile(source, units / source.name)
    for source in (release / "deploy/owner-console/systemd").glob("*.service"):
        shutil.copyfile(source, units / source.name)
    shutil.copyfile(
        release / "deploy/owner-console/systemd/brc-owner-console.slice",
        units / "brc-owner-console.slice",
    )
    dropin = units / "brc-owner-console-api.service.d"
    dropin.mkdir(exist_ok=True)
    (dropin / "manual-origin.conf").write_text(
        "[Service]\nEnvironment=OWNER_CONSOLE_PUBLIC_ORIGIN=" + ORIGIN + "\n"
    )
    snippets = etc / "nginx/snippets"
    snippets.mkdir(parents=True, exist_ok=True)
    # Read-only presentation until actual App coverage and trading gates pass.
    locations = (
        release / "deploy/owner-console/nginx/owner-console.locations.conf"
    ).read_text()
    marker = "location ^~ /api/owner/v1/ {"
    if marker not in locations:
        raise ValueError("canonical Console API location missing")
    locations = locations.replace(
        marker, marker + "\n    limit_except GET { deny all; }", 1
    )
    locations += """
location = /api/owner/v1/auth/logout {
    proxy_pass http://unix:/run/brc-owner-console/api.sock;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For "";
    proxy_set_header X-Forwarded-Proto "";
    proxy_set_header Connection "";
    proxy_cache off;
    add_header Cache-Control "no-store" always;
}
"""
    (snippets / "brc-manual-owner.locations.conf").write_text(locations)
    conf = etc / "nginx/conf.d"
    conf.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        release / "deploy/owner-console/nginx/00-brc-owner-console-limit.conf",
        conf / "00-brc-owner-console-limit.conf",
    )


async def database_state(dsn: str) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            await connection.execute(text("SET LOCAL statement_timeout='5s'"))
            raw = await connection.scalar(
                text("""SELECT json_build_object(
                'system_identifier',(SELECT system_identifier::text FROM pg_control_system()),
                'database',current_database(),
                'schema_revision',(SELECT version_num FROM alembic_version),
                'metadata',(SELECT json_object_agg(metadata_key,metadata_value) FROM brc_schema_metadata
                    WHERE metadata_key IN ('runtime_commit','schema_revision','seed_identity')),
                'accounts',(SELECT json_agg(account_id) FROM (SELECT DISTINCT account_id FROM brc_runtime_profiles LIMIT 3) p),
                'entry_enabled',(SELECT new_entry_submit_enabled FROM brc_owner_policy_current WHERE owner_policy_id='policy-main'),
                'exchange_writes',(SELECT enabled FROM brc_runtime_capabilities_current WHERE capability_key='exchange_commands'),
                'capability_commit',(SELECT certified_commit FROM brc_runtime_capabilities_current WHERE capability_key='exchange_commands'),
                'retired_control',(SELECT entry_state FROM brc_strategy_entry_controls_current WHERE strategy_group_id='SOR-001'),
                'retired_install_event',EXISTS(SELECT 1 FROM brc_owner_authorizations WHERE idempotency_key='manual-initialization:retired-sor'),
                'has_tickets',EXISTS(SELECT 1 FROM brc_trade_tickets),
                'has_commands',EXISTS(SELECT 1 FROM brc_exchange_commands),
                'has_positions',EXISTS(SELECT 1 FROM brc_positions_current),
                'has_reservations',EXISTS(SELECT 1 FROM brc_budget_reservations)
            )""")
            )
            return dict(raw)
    finally:
        await engine.dispose()


def require_fresh_state(
    state: dict, *, receipt: dict, foundation: dict, account_id: str
) -> None:
    if (
        state["system_identifier"] != foundation["system_identifier"]
        or state["database"] != foundation["database"]
        or state["schema_revision"] != receipt["schema_revision"]
        or any(
            state[key]
            for key in (
                "has_tickets",
                "has_commands",
                "has_positions",
                "has_reservations",
            )
        )
    ):
        raise ValueError("fresh database identity or flatness differs")
    if state["accounts"] is not None and (
        state["accounts"] != [account_id]
        or state["entry_enabled"] is not False
        or state["exchange_writes"] is not False
        or state["capability_commit"] != receipt["commit"]
        or state["metadata"]["runtime_commit"] != receipt["commit"]
        or state["retired_control"] != "paused"
        or not state["retired_install_event"]
    ):
        raise ValueError("existing manual authority binding differs")


async def initialize(receipt: dict, foundation: dict, account: dict, dsn: str) -> dict:
    from pydantic import SecretStr
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.trading_kernel.infrastructure.manual_account_setup import (
        BinanceManualAccountReader,
        ManualAccountCredentials,
        verify_manual_account,
    )
    from src.trading_kernel.infrastructure.manual_runtime_initialization import (
        initialize_manual_runtime,
    )
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )
    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        RuntimeAuthoritySeedRequest,
        build_runtime_seed_identity,
    )

    secret = json.loads((ROOT / "exchange-credentials.json").read_text())
    if (
        secret["expected_uid"] != account["exchange_uid"]
        or account["account_id"] != "binance-manual-" + secret["expected_uid"]
    ):
        raise ValueError("enrolled account identity differs")
    credentials = ManualAccountCredentials(
        expected_uid=secret["expected_uid"],
        api_key=secret["api_key"],
        api_secret=secret["api_secret"],
        owner_username="installation-readonly",
        owner_password=SecretStr("unused-readonly-input"),
    )
    facts = await verify_manual_account(
        BinanceManualAccountReader(credentials), credentials
    )
    if (
        not facts["account_ready"]
        or facts["credential_fingerprint"] != account["credential_fingerprint"]
    ):
        raise ValueError("fresh account is not ready for inactive installation")
    state = await database_state(dsn)
    require_fresh_state(
        state, receipt=receipt, foundation=foundation, account_id=account["account_id"]
    )
    request = RuntimeAuthoritySeedRequest(
        account_id=account["account_id"],
        runtime_commit=receipt["commit"],
        schema_revision=receipt["schema_revision"],
        seeded_at_ms=int(time.time() * 1000),
    )
    if state["accounts"] is None:
        engine = create_async_engine(dsn)
        try:
            async with PostgresKernelUnitOfWork(engine) as uow:
                await initialize_manual_runtime(uow, request)
        finally:
            await engine.dispose()
    state = await database_state(dsn)
    require_fresh_state(
        state, receipt=receipt, foundation=foundation, account_id=account["account_id"]
    )
    if state["metadata"]["seed_identity"] != build_runtime_seed_identity(request):
        raise ValueError("manual seed identity differs")
    binding = {
        "product_id": receipt["product_id"],
        "account_id": account["account_id"],
        "exchange_uid": account["exchange_uid"],
        "system_identifier": state["system_identifier"],
        "database": state["database"],
        "schema_revision": state["schema_revision"],
        "commit": receipt["commit"],
    }
    write_private(
        ROOT / "initialized-runtime.json", json.dumps(binding, sort_keys=True) + "\n"
    )
    return {
        "binding": binding,
        "entry_enabled": False,
        "exchange_commands_enabled": False,
        "retired_sor_paused": True,
        "account_observed_at_ms": facts["observed_at_ms"],
    }


def link_release(target: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(destination):
        if not destination.is_symlink() or destination.resolve() != target.resolve():
            raise ValueError("existing current release differs")
        return
    destination.symlink_to(target, target_is_directory=True)


def install(receipt: dict, foundation: dict, account: dict, dsn: str) -> dict:
    state = asyncio.run(database_state(dsn))
    require_fresh_state(
        state, receipt=receipt, foundation=foundation, account_id=account["account_id"]
    )
    binding = {
        "product_id": receipt["product_id"],
        "account_id": account["account_id"],
        "exchange_uid": account["exchange_uid"],
        "system_identifier": state["system_identifier"],
        "database": state["database"],
        "schema_revision": state["schema_revision"],
        "commit": receipt["commit"],
    }
    check_installation_binding(
        json.loads((ROOT / "initialized-runtime.json").read_text()), binding
    )
    if state["accounts"] is None:
        raise ValueError("manual account has not been seeded")
    kernel = Path(receipt["kernel_release"])
    for kind in ("kernel", "api", "static"):
        link_release(
            Path(receipt[kind + "_release"]),
            Path(
                {
                    "kernel": "/opt/brc/current",
                    "api": "/opt/brc/owner-console-api/current",
                    "static": "/opt/brc/owner-console/current",
                }[kind]
            ),
        )
    install_console_files(kernel)
    # No exchange credentials are given to these stopped units at this stage.
    # Console uses only independent systemd-loaded database and Owner credentials.
    site = Path("/etc/nginx/sites-available/brc-manual-maintenance")
    if not site.exists():
        raise ValueError("expected independent HTTPS site is absent")
    original = site.read_text()
    marker = '    location ^~ /api/ {\n        default_type application/json;\n        return 503 \'{"status":"maintenance"}\';\n    }'
    replacement = "    include /etc/nginx/snippets/brc-manual-owner.locations.conf;\n    location = / { return 302 /trading/; }"
    if marker in original:
        write_private(ROOT / "nginx-before-console.conf", original)
        site.write_text(original.replace(marker, replacement, 1))
    elif replacement not in original:
        raise ValueError("HTTPS maintenance site shape differs")
    try:
        run(["nginx", "-t"])
    except Exception:
        site.write_text(original)
        raise
    run(["systemctl", "daemon-reload"])
    # Start only the independent Console; all four trade workers stay stopped.
    run(["systemctl", "enable", "--now", "brc-owner-console-api.service"])
    run(["systemctl", "reload", "nginx"])
    result = {
        "binding": binding,
        "console_installed": True,
        "entry_enabled": False,
        "trade_workers_started": False,
        "remaining": [
            "market_instrument_certification",
            "real_app_protocol_acceptance",
            "owner_entry_authority",
        ],
    }
    write_private(
        ROOT / "console-installation.json",
        json.dumps(result, sort_keys=True) + "\n",
        overwrite=True,
    )
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", required=True, choices=("initialize", "install-console")
    )
    parser.add_argument("--commit", required=True)
    parser.add_argument("--machine-id", required=True)
    parser.add_argument("--public-ip", required=True)
    args = parser.parse_args(argv)
    if (
        os.geteuid() != 0
        or Path("/etc/brc/product-id").read_text().strip() != "brc-app-manual-v1"
    ):
        raise ValueError("root manual-product installation required")
    if not Path("/etc/brc/trading-kernel.write-fenced").is_file():
        raise ValueError("manual installation requires ENTRY fence")
    check_host_identity(
        host_facts(), {"machine_id": args.machine_id, "public_ip": args.public_ip}
    )
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0 or ROOT.stat().st_mode & 0o077:
        raise ValueError("untrusted installation directory")
    for name in (
        "staged-release.json",
        "database-complete.json",
        "verified-account.json",
        "certifications.json",
        "admin-dsn",
        "exchange-credentials.json",
    ):
        p = ROOT / name
        if p.is_symlink() or p.stat().st_uid != 0 or p.stat().st_mode & 0o077:
            raise ValueError("untrusted protected installation file")
    receipt = json.loads((ROOT / "staged-release.json").read_text())
    if receipt["commit"] != args.commit or not re.fullmatch(
        "[a-f0-9]{40}", args.commit
    ):
        raise ValueError("staged commit differs")
    validate_certificates(
        json.loads((ROOT / "certifications.json").read_text()), args.commit
    )
    kernel = Path(receipt["kernel_release"])
    if (
        kernel.resolve() != REPO_ROOT
        or (kernel / ".brc-runtime-commit").read_text().strip() != args.commit
    ):
        raise ValueError("installation source differs from exact staged candidate")
    for role in ("observation", "entry", "lifecycle", "reconciliation"):
        import subprocess

        if (
            subprocess.run(
                [
                    "systemctl",
                    "is-active",
                    "brc-trading-kernel-" + role + "-worker.service",
                ],
                capture_output=True,
                timeout=10,
                check=False,
            ).returncode
            == 0
        ):
            raise ValueError("trade worker must remain stopped during installation")
    if (
        args.phase == "initialize"
        and subprocess.run(
            ["systemctl", "is-active", "brc-owner-console-api.service"],
            capture_output=True,
            timeout=10,
            check=False,
        ).returncode
        == 0
    ):
        raise ValueError("Owner API must be stopped before fresh initialization")
    foundation = json.loads((ROOT / "database-complete.json").read_text())
    account = json.loads((ROOT / "verified-account.json").read_text())
    dsn = (ROOT / "admin-dsn").read_text().strip()
    with open("/run/brc-manual-install.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = (
            asyncio.run(initialize(receipt, foundation, account, dsn))
            if args.phase == "initialize"
            else install(receipt, foundation, account, dsn)
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - no credential-bearing exception output.
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_type": type(error).__name__,
                    "message": "manual runtime installation failed; sensitive output withheld",
                }
            )
        )
        raise SystemExit(1) from None
