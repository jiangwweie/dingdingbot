#!/usr/bin/env python3
"""Owner-authorized Tokyo clean conversion. Never use legacy alias bypasses."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MACHINE = "1c3442ab300e405e945a469ed8a12593"
SOURCE_COMMIT = "574f5cf3642ca652798b552ba1269d0ae3db1b55"
SOURCE_SCHEMA = "0016_exit_regime_v1"
ACCOUNT = "owner-subaccount-runtime-v0"
STATE = Path("/etc/brc/tokyo-manual-install")


def require_clean_source(facts: dict) -> None:
    expected = {
        "machine_id": MACHINE,
        "source_commit": SOURCE_COMMIT,
        "source_schema": SOURCE_SCHEMA,
        "account_id": ACCOUNT,
    }
    if any(facts.get(k) != v for k, v in expected.items()):
        raise ValueError("tokyo_clean_source_binding_mismatch")
    if (
        facts.get("entry_enabled") is not False
        or facts.get("writers_active") is not False
        or facts.get("backup_verified") is not True
    ):
        raise ValueError("tokyo_clean_source_requires_paused_stopped_backup")
    if any(
        facts.get(k) != 0
        for k in [
            "positions",
            "orders",
            "commands",
            "active_tickets",
            "incidents",
            "reservations",
        ]
    ):
        raise ValueError("tokyo_clean_source_not_flat")


def read_source_state() -> dict:
    """PostgreSQL facts have explicit readonly transaction and statement bound."""
    from scripts.trading_kernel.manual_host_bootstrap import run

    q = (
        """BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; SELECT json_build_object(
    'machine_id','"""
        + MACHINE
        + """',
    'source_commit',(SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='runtime_commit'),
    'source_schema',(SELECT version_num FROM alembic_version),
    'account_id',(SELECT account_id FROM brc_runtime_profiles WHERE runtime_profile_id='tiny-live-v1'),
    'entry_enabled',(SELECT new_entry_submit_enabled FROM brc_owner_policy_current WHERE owner_policy_id='policy-main'),
    'active_tickets',(SELECT count(*) FROM brc_trade_tickets WHERE terminal_at_ms IS NULL),
    'positions',(SELECT count(*) FROM brc_positions_current WHERE quantity<>0),
    'commands',(SELECT count(*) FROM brc_exchange_commands WHERE status IN ('prepared','claimed','dispatch_started','outcome_unknown')),
    'incidents',(SELECT count(*) FROM brc_runtime_incidents WHERE status='open'),
    'reservations',(SELECT count(*) FROM brc_budget_reservations WHERE status='active')); COMMIT;"""
    )
    result = json.loads(
        run(
            [
                "docker",
                "exec",
                "brc-trading-kernel-pg",
                "psql",
                "-XqAt",
                "-U",
                "brc_kernel",
                "-d",
                "brc_trading_kernel",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                q,
            ]
        )
    )
    result["machine_id"] = Path("/etc/machine-id").read_text().strip()
    result["writers_active"] = any(
        subprocess.run(
            ["systemctl", "is-active", u], capture_output=True, timeout=10, check=False
        ).returncode
        == 0
        for u in writer_units()
    )
    return result


def writer_units() -> list[str]:
    return [
        "brc-trading-kernel-" + r + "-worker.service"
        for r in ["observation", "entry", "lifecycle", "reconciliation"]
    ] + ["brc-owner-console-api.service"]


def load_source_environment() -> dict[str, str]:
    values = {}
    for line in Path("/etc/brc/trading-kernel.env").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        parsed = shlex.split(value)
        if len(parsed) != 1:
            raise ValueError("source_environment_shape")
        values[key] = parsed[0]
    return values


async def exchange_flat(env: dict) -> dict:
    """Signed GET only; never load a mutation-capable runtime into a legacy DB."""
    from decimal import Decimal

    import ccxt.async_support as ccxt

    x = ccxt.binanceusdm(
        {
            "apiKey": env["TRADING_KERNEL_API_KEY"],
            "secret": env["TRADING_KERNEL_API_SECRET"],
            "enableRateLimit": True,
            "timeout": 10000,
        }
    )
    try:
        account = await x.fapiPrivateV2GetAccount({})
        mode = await x.fapiPrivateGetPositionSideDual({})
        positions = await x.fapiPrivateV3GetPositionRisk({})
        orders = await x.fapiPrivateGetOpenOrders({})
        algos = await x.fapiPrivateGetOpenAlgoOrders({})
        if mode != {"dualSidePosition": True} or account.get("canTrade") is not True:
            raise ValueError("tokyo_account_mode_or_permission")
        if any(Decimal(p["positionAmt"]) != 0 for p in positions) or orders or algos:
            raise ValueError("tokyo_exchange_not_flat")
        uid = await x.privateGetAccount({})
        return {
            "orders": len(orders) + len(algos),
            "positions": 0,
            "uid": str(uid["uid"]),
            "wallet": account["totalWalletBalance"],
        }
    finally:
        await x.close()


def backup_source() -> dict:
    """All source writers stopped, before any irreversible removal; root-only archive."""
    import tarfile

    from scripts.trading_kernel.manual_host_bootstrap import run, write_private

    STATE.mkdir(parents=True, mode=0o700, exist_ok=True)
    dump = STATE / "source.dump"
    if not dump.exists():
        content = run(
            [
                "docker",
                "exec",
                "brc-trading-kernel-pg",
                "pg_dump",
                "-U",
                "brc_kernel",
                "-d",
                "brc_trading_kernel",
                "-Fc",
            ],
            timeout=180,
        )
        fd = os.open(dump, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(content)
    # pg_restore --list verifies the actual archive, including its catalog.
    run(
        ["docker", "exec", "-i", "brc-trading-kernel-pg", "pg_restore", "--list"],
        input_bytes=dump.read_bytes(),
        timeout=60,
    )
    # The separately identified retired BRC dry-run DB is archived as well.
    old_check = subprocess.run(
        ["docker", "inspect", "dingdingbot-pg"], capture_output=True, check=False
    )
    if old_check.returncode == 0:
        details = json.loads(old_check.stdout)[0]
        source_env = dict(v.split("=", 1) for v in details["Config"]["Env"] if "=" in v)
        if (
            source_env.get("POSTGRES_DB") != "brc_prelive_dryrun"
            or source_env.get("POSTGRES_USER") != "brc_dryrun"
        ):
            raise ValueError("legacy_database_not_brc_owned")
        legacy_dump = STATE / "legacy-dryrun.dump"
        if not legacy_dump.exists():
            content = run(
                [
                    "docker",
                    "exec",
                    "dingdingbot-pg",
                    "pg_dump",
                    "-U",
                    "brc_dryrun",
                    "-d",
                    "brc_prelive_dryrun",
                    "-Fc",
                ],
                timeout=180,
            )
            fd = os.open(legacy_dump, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(content)
        run(
            ["docker", "exec", "-i", "dingdingbot-pg", "pg_restore", "--list"],
            input_bytes=legacy_dump.read_bytes(),
            timeout=60,
        )
    archive = STATE / "source-files.tar.gz"
    if not archive.exists():
        with tarfile.open(archive, "w:gz", dereference=False) as out:
            for path in [
                "/opt/brc",
                "/etc/brc",
                "/etc/nginx",
                "/etc/systemd/system/brc-owner-console-api.service.d",
                "/etc/systemd/system/brc-trading-kernel-observation-worker.service",
                "/etc/systemd/system/brc-trading-kernel-entry-worker.service",
                "/etc/systemd/system/brc-trading-kernel-lifecycle-worker.service",
                "/etc/systemd/system/brc-trading-kernel-reconciliation-worker.service",
                "/etc/systemd/system/brc-owner-console-api.service",
            ]:
                out.add(
                    path,
                    arcname=path.lstrip("/"),
                    filter=lambda m: (
                        None
                        if any(
                            x in m.name.split("/")
                            for x in [
                                "tokyo-manual-install",
                                ".venv",
                                ".venv-owner-console",
                                "cache",
                                "python",
                            ]
                        )
                        else m
                    ),
                )
        archive.chmod(0o600)
    legacy = STATE / "legacy-dryrun.dump"
    result = {
        "backup_verified": True,
        "dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
        "legacy_dump_sha256": hashlib.sha256(legacy.read_bytes()).hexdigest()
        if legacy.exists()
        else None,
        "files_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "created_at_ms": int(time.time() * 1000),
    }
    write_private(STATE / "backup.json", json.dumps(result), overwrite=True)
    return result


def stage_artifacts(commit: str, digest: str, stream) -> dict:
    from scripts.trading_kernel import manual_host_bootstrap as bootstrap

    if Path("/etc/machine-id").read_text().strip() != MACHINE:
        raise ValueError("tokyo_stage_host_mismatch")
    facts = read_source_state()
    if facts["source_commit"] != SOURCE_COMMIT or facts["entry_enabled"] is not False:
        raise ValueError("tokyo_stage_source_not_paused")
    # Dedicated authorized target path, not an alias change to the Seoul installer.
    bootstrap.ROOT = STATE
    return bootstrap.receive_release(commit, digest, stream)


async def initialize_fresh_database(
    dsn: str, receipt: dict, configuration: dict
) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.trading_kernel.application.install_strategy_universe import (
        UniverseConfigurationRequest,
        configure_strategy_universe,
    )
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        set_strategy_entry_state,
    )
    from src.trading_kernel.domain.generic_selection_spec import (
        SpecNumericInstallationEvidence,
        generic_selection_spec,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    from src.trading_kernel.infrastructure.manual_clone_initialization import (
        initialize_tokyo_manual,
    )
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )
    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        RuntimeAuthoritySeedRequest,
    )

    now = int(time.time() * 1000)
    engine = create_async_engine(dsn)
    try:
        async with PostgresKernelUnitOfWork(engine) as u:
            await initialize_tokyo_manual(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id=ACCOUNT,
                    runtime_commit=receipt["commit"],
                    schema_revision=receipt["schema_revision"],
                    seeded_at_ms=now,
                ),
            )
        async with PostgresKernelUnitOfWork(engine) as u:
            for event, members in configuration["members"].items():
                await configure_strategy_universe(
                    u,
                    UniverseConfigurationRequest(
                        runtime_profile_id="tiny-live-v1",
                        event_id=event.split(":")[2],
                        exchange_instrument_ids=tuple(members),
                        installed_at_ms=now + 1,
                    ),
                )
            for group in ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"]:
                spec = generic_selection_spec(group)
                evidence = SpecNumericInstallationEvidence.model_validate(
                    configuration["spec_evidence"][group]
                )
                await u.instrument_selection.install_generic_spec(
                    spec, installed_at_ms=now + 2, certification=evidence
                )
            for group, state in configuration["strategy"].items():
                current = await u.owner_controls.get_strategy_control(group)
                if current is None:
                    raise ValueError("initial_strategy_control_missing")
                if current.entry_state.value != state:
                    await set_strategy_entry_state(
                        u,
                        strategy_group_id=group,
                        target_state=StrategyEntryState(state),
                        request=ControlMutationRequest(
                            expected_version=current.control_version,
                            reason="Owner approved clean Tokyo installation using Seoul parameters",
                            idempotency_key="tokyo-clean-initial:" + group,
                            owner_identity="Owner-clean-rebuild-20261120",
                            now_ms=now + 3,
                        ),
                        authentication_strength="session",
                    )
            direction = await u.directional_risk.get("binance-usdm", ACCOUNT)
            if direction is None:
                raise ValueError("fresh_direction_missing")
            if configuration["direction"] != "neutral":
                raise ValueError("clean installation snapshot expected neutral source")
            from src.trading_kernel.domain.directional_risk import (
                DirectionalChangeRequest,
            )

            await u.directional_risk.request_change(
                DirectionalChangeRequest(
                    venue_id="binance-usdm",
                    account_id=ACCOUNT,
                    expected_version=direction.version,
                    view="neutral",
                    owner_identity="Owner-clean-rebuild-20261120",
                    reason="Owner approved adopting Seoul neutral parameters at empty installation",
                    idempotency_key="tokyo-clean-direction",
                    requested_at_ms=now + 4,
                )
            )
            # This deployment initialization records its actual source; no
            # artificial Console/TOTP or ENTRY Resume event is generated.
        async with engine.connect() as c:
            if await c.scalar(text("SELECT count(*) FROM brc_trade_tickets")) != 0:
                raise ValueError("clean initial ledger not empty")
    finally:
        await engine.dispose()


def activate_clean() -> dict:
    import asyncio
    import shutil

    from sqlalchemy.engine import make_url

    from scripts.trading_kernel.manual_host_bootstrap import run, write_private

    receipt = json.loads((STATE / "staged-release.json").read_text())
    if Path(receipt["kernel_release"]).resolve() != ROOT:
        raise ValueError("clean_candidate_tree_mismatch")
    exported = json.loads((STATE / "backup-export-verified.json").read_text())
    backup = json.loads((STATE / "backup.json").read_text())
    if exported != {
        "dump_sha256": backup["dump_sha256"],
        "files_sha256": backup["files_sha256"],
        "legacy_dump_sha256": backup.get("legacy_dump_sha256"),
    }:
        raise ValueError("offline_backup_copy_unverified")
    facts = read_source_state()
    facts.update(orders=0, backup_verified=True)
    require_clean_source(facts)
    env = json.loads((STATE / "source-environment.json").read_text())
    asyncio.run(exchange_flat(env))
    configuration = json.loads((STATE / "configuration.json").read_text())
    if any(v != "static_baseline" for v in configuration["selection"].values()):
        raise ValueError("clean_source_static_snapshot_required")
    if str(configuration["baseline"]) != "0.02":
        raise ValueError("clean_source_risk_baseline_differs")
    # Byte-for-byte preserve external endpoints and credentials; no stdout secrets.
    auth = Path("/etc/brc/owner-console-credentials")
    auth_hashes = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in auth.iterdir()
        if p.is_file()
    }
    for p in Path("/etc/nginx/sites-available").glob("*"):
        if p.is_file():
            auth_hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    write_private(
        STATE / "preserved-configuration-hashes.json",
        json.dumps(auth_hashes),
        overwrite=True,
    )
    url = make_url(env["TRADING_KERNEL_DATABASE_URL"])
    if (
        url.database != "brc_trading_kernel"
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 55433
        or not url.password
    ):
        raise ValueError("unexpected_source_database_binding")
    # A genuinely new database container/volume replaces the old application PostgreSQL.
    # API/read/control passwords are restored from protected existing DSNs.
    image = json.loads(run(["docker", "inspect", "brc-trading-kernel-pg"]))[0]["Image"]
    if (
        subprocess.run(
            ["docker", "inspect", "brc-manual-runtime-pg"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    ):
        raise ValueError("new_database_container_already_exists")
    if (
        subprocess.run(
            ["docker", "volume", "inspect", "brc-tokyo-manual-pg-data"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    ):
        raise ValueError("new_database_volume_already_exists")
    run(["docker", "stop", "brc-trading-kernel-pg"])
    password_file = STATE / "postgres-password"
    assert url.password is not None
    write_private(password_file, url.password + "\n", overwrite=True)
    run(
        [
            "docker",
            "volume",
            "create",
            "--label",
            "brc.product=brc-app-manual-v1",
            "brc-tokyo-manual-pg-data",
        ]
    )
    run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "brc-manual-runtime-pg",
            "--restart",
            "unless-stopped",
            "--label",
            "brc.product=brc-app-manual-v1",
            "--label",
            "brc.machine=" + MACHINE,
            "--publish",
            "127.0.0.1:55433:5432",
            "--mount",
            "type=volume,source=brc-tokyo-manual-pg-data,target=/var/lib/postgresql/data",
            "--mount",
            "type=bind,source="
            + str(password_file)
            + ",target=/run/secrets/postgres-password,readonly",
            "--env",
            "POSTGRES_USER=brc_kernel",
            "--env",
            "POSTGRES_DB=brc_trading_kernel",
            "--env",
            "POSTGRES_PASSWORD_FILE=/run/secrets/postgres-password",
            image,
        ]
    )
    for _ in range(30):
        if (
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "brc-manual-runtime-pg",
                    "pg_isready",
                    "-U",
                    "brc_kernel",
                    "-d",
                    "brc_trading_kernel",
                ],
                capture_output=True,
                check=False,
            ).returncode
            == 0
        ):
            break
        time.sleep(1)
    else:
        raise ValueError("fresh_database_readiness_timeout")
    target_env = {
        **os.environ,
        "TRADING_KERNEL_DATABASE_URL": env["TRADING_KERNEL_DATABASE_URL"],
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/trading_kernel/bootstrap_schema.py"),
        ],
        env=target_env,
        timeout=150,
    )
    # Existing read/control passwords are retained; only exact declared grants.
    sql = ""
    for role, filename in [
        ("brc_owner_console", "database_dsn"),
        ("brc_owner_control", "control_database_dsn"),
    ]:
        preserved = make_url((auth / filename).read_text().strip())
        if preserved.username != role or not preserved.password:
            raise ValueError("preserved_database_role_binding")
        safe_password = preserved.password.replace("'", "''")
        sql += (
            "CREATE ROLE "
            + role
            + " LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '"
            + safe_password
            + "';\n"
        )
    for name in ["owner-console-read-role.sql", "owner-console-control-role.sql"]:
        sql += (ROOT / "deploy/owner-console/postgresql" / name).read_text() + "\n"
    run(
        [
            "docker",
            "exec",
            "-i",
            "brc-manual-runtime-pg",
            "psql",
            "-Xq",
            "-U",
            "brc_kernel",
            "-d",
            "brc_trading_kernel",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input_bytes=sql.encode(),
        timeout=30,
    )
    asyncio.run(
        initialize_fresh_database(
            env["TRADING_KERNEL_DATABASE_URL"], receipt, configuration
        )
    )
    runtime = dict(configuration["runtime_environment"])
    for name in [
        "TRADING_KERNEL_API_KEY",
        "TRADING_KERNEL_API_SECRET",
        "TRADING_KERNEL_DATABASE_URL",
        "TRADING_KERNEL_ACCOUNT_ID",
        "TRADING_KERNEL_POSTGRES_PASSWORD",
    ]:
        if name in env:
            runtime[name] = env[name]
    runtime.update(
        TRADING_KERNEL_PRODUCT_ID="brc-app-manual-v1",
        TRADING_KERNEL_RUNTIME_COMMIT=receipt["commit"],
        TRADING_KERNEL_SCHEMA_REVISION=receipt["schema_revision"],
        TRADING_KERNEL_NOTICE_SITE="东京",
        TRADING_KERNEL_CONSOLE_ORIGIN="https://jiaoyingpan.cloud",
    )
    write_private(
        Path("/etc/brc/trading-kernel.env"),
        "".join(k + "=" + json.dumps(v) + "\n" for k, v in runtime.items()),
        overwrite=True,
    )
    notify = Path("/etc/brc/notification-credentials")
    notify.mkdir(mode=0o700, exist_ok=True)
    write_private(
        notify / "feishu.env",
        "TRADING_KERNEL_SEOUL_FEISHU_WEBHOOK_URL="
        + json.dumps(env["TRADING_KERNEL_FEISHU_WEBHOOK_URL"])
        + "\n",
        overwrite=True,
    )
    Path("/etc/brc/product-id").write_text("brc-app-manual-v1\n")
    for kind, path in [
        ("kernel", "/opt/brc/current"),
        ("api", "/opt/brc/owner-console-api/current"),
        ("static", "/opt/brc/owner-console/current"),
    ]:
        link = Path(path)
        pending = link.with_name(link.name + ".manual-pending")
        if pending.exists() or pending.is_symlink():
            raise ValueError("unexpected_pending_release")
        pending.symlink_to(receipt[kind + "_release"])
        os.replace(pending, link)
    for p in (ROOT / "deploy/systemd").glob("*.service"):
        shutil.copyfile(p, Path("/etc/systemd/system") / p.name)
    for p in (ROOT / "deploy/systemd").glob("*.slice"):
        shutil.copyfile(p, Path("/etc/systemd/system") / p.name)
    shutil.copyfile(
        ROOT / "deploy/owner-console/systemd/brc-owner-console-api.service",
        Path("/etc/systemd/system/brc-owner-console-api.service"),
    )
    for role in ["entry", "reconciliation"]:
        private = Path("/etc/brc/trading-kernel-" + role + ".env")
        write_private(
            private,
            "".join(
                k + "=" + json.dumps(v) + "\n"
                for k, v in configuration["role_environment"][role].items()
            ),
            overwrite=True,
        )
        d = Path("/etc/systemd/system/brc-trading-kernel-" + role + "-worker.service.d")
        d.mkdir(exist_ok=True)
        (d / "read-budget.conf").write_text(
            "[Service]\nEnvironmentFile=" + str(private) + "\n"
        )
    (
        Path("/etc/systemd/system/brc-trading-kernel-reconciliation-worker.service.d")
        / "notifications.conf"
    ).write_text(
        "[Service]\nEnvironmentFile=/etc/brc/notification-credentials/feishu.env\n"
    )
    shutil.copyfile(
        ROOT / "deploy/owner-console/nginx/owner-console.locations.conf",
        Path("/etc/nginx/snippets/brc-owner-console.locations.conf"),
    )
    run(["nginx", "-t"])
    run(["systemctl", "daemon-reload"])
    for name, digest in auth_hashes.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError("Tokyo_credentials_or_site_configuration_changed")
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
        "status": "installed_entry_fenced_configuration_publication_pending",
        "commit": receipt["commit"],
        "schema": receipt["schema_revision"],
        "credentials_preserved": True,
        "entry_enabled": False,
    }
    write_private(STATE / "installed.json", json.dumps(result), overwrite=True)
    return result


def cleanup_retired() -> dict:
    import asyncio
    import shutil

    from scripts.trading_kernel.manual_host_bootstrap import run, write_private

    receipt = json.loads((STATE / "staged-release.json").read_text())
    if Path("/opt/brc/current").resolve() != Path(receipt["kernel_release"]).resolve():
        raise ValueError("cleanup_target_not_current")
    proof = json.loads((STATE / "target-verified.json").read_text())
    if (
        proof.get("commit") != receipt["commit"]
        or not proof.get("credential_preservation_pass")
        or not proof.get("new_database_verified")
    ):
        raise ValueError("cleanup_target_proof_missing")
    env = load_source_environment()
    asyncio.run(exchange_flat(env))
    q = "BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; SELECT new_entry_submit_enabled FROM brc_owner_policy_current WHERE owner_policy_id='policy-main'; COMMIT;"
    if (
        run(
            [
                "docker",
                "exec",
                "brc-manual-runtime-pg",
                "psql",
                "-XqAt",
                "-U",
                "brc_kernel",
                "-d",
                "brc_trading_kernel",
                "-c",
                q,
            ]
        )
        .decode()
        .strip()
        != "f"
    ):
        raise ValueError("cleanup_requires_entry_paused")
    deleted = []
    for container, user, db in [
        ("brc-trading-kernel-pg", "brc_kernel", "brc_trading_kernel"),
        ("dingdingbot-pg", "brc_dryrun", "brc_prelive_dryrun"),
    ]:
        inspected = subprocess.run(
            ["docker", "inspect", container], capture_output=True, check=False
        )
        if inspected.returncode:
            continue
        details = json.loads(inspected.stdout)[0]
        values = dict(v.split("=", 1) for v in details["Config"]["Env"] if "=" in v)
        if values.get("POSTGRES_USER") != user or values.get("POSTGRES_DB") != db:
            raise ValueError("cleanup_database_owner_differs")
        volumes = [m["Name"] for m in details["Mounts"] if m["Type"] == "volume"]
        run(["docker", "rm", "-f", container])
        deleted.append(container)
        for volume in volumes:
            run(["docker", "volume", "rm", volume])
            deleted.append(volume)
    keep = {
        Path(receipt[k + "_release"]).resolve() for k in ["kernel", "api", "static"]
    }
    for directory in [
        "/opt/brc/releases",
        "/opt/brc/owner-console-api/releases",
        "/opt/brc/owner-console/releases",
    ]:
        for child in Path(directory).iterdir():
            if child.resolve() in keep:
                continue
            if child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            deleted.append(str(child))
    for directory in ["/opt/brc/cutover", "/opt/brc/owner-control-grants"]:
        p = Path(directory)
        if p.exists():
            shutil.rmtree(p)
            deleted.append(directory)
    # Remove obsolete default site only; preserve the existing public-domain
    # gateway, certificate, redirects and non-BRC applications byte-for-byte.
    for name in [
        "/etc/nginx/sites-enabled/brc-owner-console",
        "/etc/nginx/sites-available/brc-owner-console",
    ]:
        p = Path(name)
        if p.is_symlink() or p.is_file():
            p.unlink()
            deleted.append(name)
    run(["nginx", "-t"])
    run(["systemctl", "reload", "nginx"])
    result = {
        "status": "retired_runtime_removed",
        "commit": receipt["commit"],
        "deleted": deleted,
        "entry_enabled": False,
        "offline_backup_required": True,
    }
    write_private(STATE / "cleanup.json", json.dumps(result), overwrite=True)
    return result


def main() -> None:
    import asyncio

    from scripts.trading_kernel.manual_host_bootstrap import run, write_private

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--phase",
        choices=["stage", "prepare-source", "activate", "cleanup"],
        required=True,
    )
    p.add_argument("--commit")
    p.add_argument("--digest")
    args = p.parse_args()
    if os.geteuid() != 0 or Path("/etc/machine-id").read_text().strip() != MACHINE:
        raise ValueError("tokyo_clean_host_binding")
    if args.phase == "stage":
        print(json.dumps(stage_artifacts(args.commit, args.digest, sys.stdin.buffer)))
        return
    if args.phase == "cleanup":
        print(json.dumps(cleanup_retired()))
        return
    if args.phase == "activate":
        print(json.dumps(activate_clean()))
        return
    if (
        ROOT != Path("/opt/brc/current").resolve()
        and not (ROOT / ".brc-runtime-commit").is_file()
    ):
        raise ValueError("certified_installation_tree_required")
    STATE.mkdir(parents=True, mode=0o700, exist_ok=True)
    with (STATE / "operation.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        env = load_source_environment()
        initial = read_source_state()
        for key, value in {
            "machine_id": MACHINE,
            "source_commit": SOURCE_COMMIT,
            "source_schema": SOURCE_SCHEMA,
            "account_id": ACCOUNT,
            "entry_enabled": False,
            "positions": 0,
            "active_tickets": 0,
            "commands": 0,
            "incidents": 0,
            "reservations": 0,
        }.items():
            if initial.get(key) != value:
                raise ValueError("source_preparation_identity_or_activity")
        venue = asyncio.run(exchange_flat(env))
        Path("/etc/brc/trading-kernel.write-fenced").touch(mode=0o600)
        run(
            ["systemctl", "disable", "--now", "brc-trading-kernel-entry-worker.service"]
        )
        run(["systemctl", "stop", *writer_units()], timeout=100)
        backup = backup_source()
        facts = read_source_state()
        facts.update(orders=venue["orders"], backup_verified=backup["backup_verified"])
        require_clean_source(facts)
        write_private(
            STATE / "source-environment.json", json.dumps(env), overwrite=True
        )
        write_private(STATE / "source-state.json", json.dumps(facts), overwrite=True)
        write_private(
            STATE / "exchange-identity.json", json.dumps(venue), overwrite=True
        )
        print(
            json.dumps(
                {
                    "status": "stopped_backed_up",
                    "source": facts,
                    "backup": backup,
                    "phase": args.phase,
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - credentials never enter stdout
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "message": "Tokyo replacement stopped; sensitive output withheld",
                }
            )
        )
        raise SystemExit(1) from None
