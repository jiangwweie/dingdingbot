#!/usr/bin/env python3
"""Stopped-flat manual upgrade: same schema or exact 0017-to-0018 notice migration."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
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
    require_stopped_upgrade,
    require_upgrade_schema,
    run,
    validate_certificates,
    write_private,
)


async def activate(receipt: dict, source: dict, dsn: str) -> dict:
    from hashlib import sha256

    from pydantic import SecretStr
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
        read_preserved_runtime_state,
    )
    from src.trading_kernel.infrastructure.manual_account_setup import (
        BinanceManualAccountReader,
        ManualAccountCredentials,
        verify_manual_account,
    )
    from src.trading_kernel.infrastructure.pg_models import metadata
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )
    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        RuntimeAuthoritySeedRequest,
        deploy_compatible_upgrade_identity,
        deploy_runtime_identity,
    )

    require_upgrade_schema(source["schema"], receipt["schema_revision"])
    forward = source["schema"] != receipt["schema_revision"]

    secret = json.loads((ROOT / "exchange-credentials.json").read_text())
    enrolled = json.loads((ROOT / "verified-account.json").read_text())
    facts = await verify_manual_account(
        BinanceManualAccountReader(
            ManualAccountCredentials(
                expected_uid=secret["expected_uid"],
                api_key=secret["api_key"],
                api_secret=secret["api_secret"],
                owner_username="readonly-upgrade",
                owner_password=SecretStr("unused"),
            )
        ),
        ManualAccountCredentials(
            expected_uid=secret["expected_uid"],
            api_key=secret["api_key"],
            api_secret=secret["api_secret"],
            owner_username="readonly-upgrade",
            owner_password=SecretStr("unused"),
        ),
    )
    if (
        not facts["account_ready"]
        or facts["credential_fingerprint"] != enrolled["credential_fingerprint"]
    ):
        raise ValueError("fresh stopped exchange account identity or flatness differs")

    engine = create_async_engine(dsn)

    async def snapshot():
        async with engine.connect() as c:
            await c.execute(text("SET TRANSACTION READ ONLY"))
            await c.execute(text("SET LOCAL statement_timeout='5s'"))
            result = await read_preserved_runtime_state(c)
            history = {}
            for table in metadata.sorted_tables:
                if table.name in {
                    "brc_schema_metadata",
                    "brc_runtime_capabilities_current",
                }:
                    continue
                if table.name == "brc_notice_outbox" and forward:
                    continue
                # One-off stopped fresh-account deployment audit, never runtime cadence.
                rows = (
                    (
                        await c.execute(
                            text(
                                'SELECT to_jsonb(t)::text FROM "'
                                + table.name
                                + '" t ORDER BY to_jsonb(t)::text LIMIT 100001'
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if len(rows) > 100000:
                    raise ValueError(
                        "fresh-account preservation exceeds bounded upgrade scope"
                    )
                history[table.name] = {
                    "rows": len(rows),
                    "sha256": sha256(
                        json.dumps(rows, separators=(",", ":")).encode()
                    ).hexdigest(),
                }
            result["preserved_table_rows"] = history
            for key, table in [
                ("policy", "brc_owner_policy_current"),
                ("controls", "brc_strategy_entry_controls_current"),
                ("selection", "brc_strategy_selection_control_current"),
            ]:
                result[key] = [
                    dict(r)
                    for r in (
                        await c.execute(text("SELECT * FROM " + table))
                    ).mappings()
                ]
            return result

    try:
        before = await snapshot()
        if before["policy"][0]["new_entry_submit_enabled"] is not False:
            raise ValueError("Owner ENTRY must remain paused for stopped upgrade")
        write_private(
            ROOT / "same-schema-source-preservation.json",
            json.dumps(before, default=str, sort_keys=True) + "\n",
            overwrite=True,
        )
        if forward:
            migration_env = os.environ.copy()
            migration_env["TRADING_KERNEL_DATABASE_URL"] = dsn
            run(
                [
                    str(REPO_ROOT / ".venv/bin/python"),
                    str(REPO_ROOT / "scripts/trading_kernel/bootstrap_schema.py"),
                ],
                env=migration_env,
            )
        account = json.loads((ROOT / "verified-account.json").read_text())["account_id"]
        async with PostgresKernelUnitOfWork(engine) as uow:
            await (
                deploy_compatible_upgrade_identity
                if forward
                else deploy_runtime_identity
            )(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id=account,
                    runtime_commit=receipt["commit"],
                    schema_revision=receipt["schema_revision"],
                    seeded_at_ms=int(time.time() * 1000),
                ),
            )
        if forward:
            async with engine.connect() as c:
                if not await c.scalar(text("SELECT has_table_privilege('brc_kernel','brc_notice_outbox','SELECT,INSERT,UPDATE') AND has_sequence_privilege('brc_kernel','brc_notice_outbox_sequence_seq','USAGE,SELECT') AND has_table_privilege('brc_owner_console','brc_notice_outbox','SELECT')")):
                    raise ValueError("notice runtime/read role privileges differ")
                if await c.scalar(text("SELECT count(*) FROM brc_notice_outbox")) != 0:
                    raise ValueError(
                        "new notice outbox must be empty before writers start"
                    )
        after = await snapshot()
        if before != after:
            raise ValueError(
                "current Universe/history or Owner controls changed during upgrade"
            )
    finally:
        await engine.dispose()
    env_path = Path("/etc/brc/trading-kernel.env")
    values = {
        k: json.loads(v)
        for k, v in (line.split("=", 1) for line in env_path.read_text().splitlines())
    }
    if values["TRADING_KERNEL_RUNTIME_COMMIT"] != source["commit"]:
        raise ValueError("source Worker environment commit differs")
    values["TRADING_KERNEL_RUNTIME_COMMIT"] = receipt["commit"]
    values["TRADING_KERNEL_SCHEMA_REVISION"] = receipt["schema_revision"]
    write_private(
        env_path,
        "".join(k + "=" + json.dumps(v) + "\n" for k, v in values.items()),
        overwrite=True,
    )
    for kind, path in [
        ("kernel", "/opt/brc/current"),
        ("api", "/opt/brc/owner-console-api/current"),
        ("static", "/opt/brc/owner-console/current"),
    ]:
        current = Path(path)
        if not current.is_symlink() or (
            kind != "static"
            and (current / ".brc-runtime-commit").read_text().strip()
            != source["commit"]
        ):
            raise ValueError("source surface differs during stopped activation")
        pending = current.with_name(current.name + ".pending-manual-upgrade")
        if os.path.lexists(pending):
            raise ValueError("unexpected pending release link")
        pending.symlink_to(receipt[kind + "_release"], target_is_directory=True)
        os.replace(pending, current)
    # Publish only the certified canonical Console routes. Authentication and TOTP remain unchanged.
    canonical = REPO_ROOT / "deploy/owner-console/nginx/owner-console.locations.conf"
    Path("/etc/nginx/snippets/brc-manual-owner.locations.conf").write_text(
        canonical.read_text()
    )
    run(["nginx", "-t"])
    # Notification routing has no trading authority. Use the existing startup-only
    # environment boundary, keeping runtime cadence free of file reads.
    if receipt["schema_revision"] == "0018_notice_outbox_v1":
        credential = Path("/etc/brc/notification-credentials/feishu_webhook")
        private_env = Path("/etc/brc/notification-credentials/feishu.env")
        if credential.is_file():
            from src.trading_kernel.infrastructure.feishu_notice import FeishuChannel

            webhook = credential.read_text().strip()
            if (
                credential.is_symlink()
                or credential.stat().st_mode & 0o077
                or not FeishuChannel(webhook).configured
            ):
                raise ValueError("notification credential permissions or route differ")
            write_private(
                private_env,
                "TRADING_KERNEL_SEOUL_FEISHU_WEBHOOK_URL=" + json.dumps(webhook) + "\n",
                overwrite=True,
            )
            credential.unlink()
        dropin = Path(
            "/etc/systemd/system/brc-trading-kernel-reconciliation-worker.service.d/notifications.conf"
        )
        dropin.parent.mkdir(parents=True, exist_ok=True)
        dropin.write_text(
            "[Service]\nEnvironmentFile=-/etc/brc/notification-credentials/feishu.env\n"
        )
    run(["systemctl", "daemon-reload"])
    run(
        [
            "systemctl",
            "start",
            "brc-owner-console-api.service",
            "brc-trading-kernel-observation-worker.service",
            "brc-trading-kernel-lifecycle-worker.service",
            "brc-trading-kernel-reconciliation-worker.service",
        ]
    )
    run(["systemctl", "reload", "nginx"])
    result = {
        "status": "notice_schema_upgraded_entry_fenced"
        if forward
        else "same_schema_upgraded_entry_fenced",
        "schema_revision": receipt["schema_revision"],
        "source_commit": source["commit"],
        "commit": receipt["commit"],
        "preservation_pass": True,
        "owner_policy_changed": False,
        "entry_worker_started": False,
    }
    write_private(
        ROOT / "same-schema-upgrade.json",
        json.dumps(result, sort_keys=True) + "\n",
        overwrite=True,
    )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=["activate-upgrade"], required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--machine-id", required=True)
    p.add_argument("--public-ip", required=True)
    a = p.parse_args()
    if os.geteuid() != 0:
        raise ValueError("root required")
    check_host_identity(
        host_facts(), {"machine_id": a.machine_id, "public_ip": a.public_ip}
    )
    receipt = json.loads((ROOT / "staged-release.json").read_text())
    prepared = json.loads((ROOT / "upgrade-source.json").read_text())
    if (
        receipt["commit"] != a.commit
        or prepared["target_commit"] != a.commit
        or REPO_ROOT != Path(receipt["kernel_release"])
    ):
        raise ValueError("exact upgrade candidate binding differs")
    validate_certificates(
        json.loads((ROOT / "certifications.json").read_text()), a.commit
    )
    with open("/run/brc-manual-install.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = require_stopped_upgrade()
        if source != prepared["source"]:
            raise ValueError("stopped upgrade source changed after staging")
        print(
            json.dumps(
                asyncio.run(
                    activate(receipt, source, (ROOT / "admin-dsn").read_text().strip())
                )
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - credentials never appear in failure output.
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_type": type(error).__name__,
                    "message": "manual upgrade failed; all ENTRY fences retained; sensitive output withheld",
                }
            )
        )
        raise SystemExit(1) from None
