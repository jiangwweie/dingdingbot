#!/usr/bin/env python3
"""Root-only, inactive installation on a fresh bound manual-product host.

No account authority, credentials, exchange access, ENTRY promotion or service
start is provided by these phases. The local exact-candidate controller owns
archive/certification validation before this transport boundary.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import ipaddress
import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

PRODUCT = "brc-app-manual-v1"
ROOT = Path("/etc/brc/manual-install")
CONTAINER = "brc-manual-runtime-pg"
DATABASE = "brc_manual_kernel"
PYTHON = "/opt/brc/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
MAX_ARCHIVE = 80 * 1024 * 1024


def check_host_identity(actual: dict, expected: dict) -> None:
    for key in ("machine_id", "public_ip"):
        if actual.get(key) != expected.get(key):
            raise ValueError("manual host identity mismatch")
    if actual.get("product_id") != PRODUCT:
        raise ValueError("manual host product identity mismatch")


def run(argv, *, input_bytes=None, env=None, timeout=300):
    result = subprocess.run(
        argv,
        input=input_bytes,
        env=env,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        # Child tracebacks can contain DSNs. Never forward raw output.
        raise RuntimeError("manual installation operation failed: " + str(argv[0]))
    return result.stdout


def write_private(path: Path, value: str, *, mode=0o600, overwrite=False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("credential symlink is forbidden")
    if path.exists() and not overwrite:
        if path.lstat().st_mode & 0o077:
            raise ValueError("private installation state has unsafe permissions")
        if path.read_text() != value:
            raise ValueError("existing private installation state differs")
        return
    fd, temp = tempfile.mkstemp(prefix=".brc-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as stream:
            stream.write(value)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def host_facts() -> dict:
    machine = Path("/etc/machine-id").read_text().strip()
    marker = Path("/etc/brc/product-id")
    st = marker.lstat()
    if marker.is_symlink() or st.st_uid != 0 or st.st_mode & 0o022:
        raise ValueError("untrusted product marker")
    import urllib.request

    with urllib.request.urlopen(
        "http://metadata.tencentyun.com/latest/meta-data/public-ipv4", timeout=5
    ) as r:
        ip = r.read(128).decode().strip()
    ipaddress.ip_address(ip)
    return {
        "machine_id": machine,
        "public_ip": ip,
        "product_id": marker.read_text().strip(),
        "runtime_present": Path("/opt/brc/current").exists(),
        "entry_fenced": Path("/etc/brc/trading-kernel.write-fenced").is_file(),
        "database_prepared": (ROOT / "database-complete.json").is_file(),
        "staged_commit": json.loads((ROOT / "staged-release.json").read_text()).get(
            "commit"
        )
        if (ROOT / "staged-release.json").is_file()
        else None,
    }


def require_inactive() -> None:
    if not Path("/etc/brc/trading-kernel.write-fenced").is_file():
        raise ValueError("manual installation requires existing write fence")
    if (
        Path("/opt/brc/current").exists()
        or Path("/etc/brc/trading-kernel.env").exists()
    ):
        raise ValueError("fresh-host installer refuses an existing runtime")
    for unit in ("observation", "entry", "lifecycle", "reconciliation"):
        result = subprocess.run(
            [
                "systemctl",
                "is-active",
                "brc-trading-kernel-" + unit + "-worker.service",
            ],
            capture_output=True,
            check=False,
            timeout=15,
        )
        if result.returncode == 0:
            raise ValueError("runtime writer active")
    if (
        subprocess.run(
            ["systemctl", "is-active", "brc-owner-console-api.service"],
            capture_output=True,
            check=False,
            timeout=15,
        ).returncode
        == 0
    ):
        raise ValueError("Owner API writer active")


def require_stopped_upgrade(*, filesystem_root: Path = Path("/")) -> dict:
    """A same-schema upgrade is explicit and stopped, never a fresh-host bypass."""
    if not (filesystem_root / "etc/brc/trading-kernel.write-fenced").is_file():
        raise ValueError("upgrade requires the ENTRY maintenance fence")
    current = filesystem_root / "opt/brc/current"
    if (
        not current.is_symlink()
        or not (filesystem_root / "etc/brc/trading-kernel.env").is_file()
    ):
        raise ValueError("upgrade requires an installed bound runtime")
    for unit in [
        f"brc-trading-kernel-{r}-worker.service"
        for r in ("observation", "entry", "lifecycle", "reconciliation")
    ] + ["brc-owner-console-api.service"]:
        if (
            subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                timeout=10,
                check=False,
            ).returncode
            == 0
        ):
            raise ValueError("all runtime and Owner writers must be stopped")
    identity = json.loads(
        read_database("""SELECT json_build_object(
        'commit',(SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='runtime_commit'),
        'schema',(SELECT version_num FROM alembic_version),
        'paused',NOT(SELECT new_entry_submit_enabled FROM brc_owner_policy_current WHERE owner_policy_id='policy-main'),
        'tickets',EXISTS(SELECT 1 FROM brc_trade_tickets),
        'commands',EXISTS(SELECT 1 FROM brc_exchange_commands),
        'positions',EXISTS(SELECT 1 FROM brc_positions_current WHERE quantity<>0),
        'incidents',EXISTS(SELECT 1 FROM brc_runtime_incidents WHERE status='open'))""")
    )
    if (
        identity["commit"] != (current / ".brc-runtime-commit").read_text().strip()
        or identity["schema"] != (current / ".brc-schema-revision").read_text().strip()
        or not identity["paused"]
        or any(identity[k] for k in ("tickets", "commands", "positions", "incidents"))
    ):
        raise ValueError("fresh-account stopped upgrade identity or flatness differs")
    return identity


def require_upgrade_schema(source: str, target: str) -> None:
    if source == target:
        return
    if (source, target) != ("0017_app_management_observation", "0018_notice_outbox_v1"):
        raise ValueError("manual upgrade requires same schema or exact 0017-to-0018 transition")


def extract_plain_archive(source, destination: Path) -> None:
    """Release archives contain only plain files/directories, never links/devices."""
    with tarfile.open(fileobj=source, mode="r:*") as archive:
        members = archive.getmembers()
        if len(members) > 20000 or sum(m.size for m in members) > 300 * 1024 * 1024:
            raise ValueError("archive exceeds installation bound")
        for m in members:
            p = PurePosixPath(m.name)
            if (
                p.is_absolute()
                or ".." in p.parts
                or not p.parts
                or not (m.isfile() or m.isdir())
            ):
                raise ValueError("unsafe release archive member")
        if destination.is_symlink():
            raise ValueError("archive destination cannot be a symlink")
        destination.mkdir(parents=True, exist_ok=True)
        for m in members:
            out = destination.joinpath(*PurePosixPath(m.name).parts)
            if out.is_symlink() or not out.resolve().is_relative_to(
                destination.resolve()
            ):
                raise ValueError("archive path traverses existing symlink")
            if m.isdir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            content = archive.extractfile(m)
            if content is None:
                raise ValueError("archive file missing")
            with out.open("wb") as stream:
                shutil.copyfileobj(content, stream)
            out.chmod(0o755 if m.mode & 0o111 else 0o644)


def validate_certificates(metadata: dict, commit: str) -> None:
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("exact release commit required")
    for surface in ("kernel", "api", "static"):
        item = metadata[surface]
        if (
            item.get("status") != "pass"
            or item.get("product_id") != PRODUCT
            or item.get("release_commit") != commit
        ):
            raise ValueError("release certification identity differs")
    if metadata["kernel"].get("release_level") != "R4":
        raise ValueError("fresh installation requires R4")
    schema = metadata["kernel"].get("schema_revision")
    if not schema or metadata["api"].get("schema_revision") != schema:
        raise ValueError("surface schema identity differs")


def receive_release(commit: str, digest: str, stream, *, expected_schema=None, source_schema=None) -> dict:
    data = stream.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("release transport digest/size differs")
    parent = Path("/opt/brc/releases")
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".manual-", dir=parent))
    try:
        extract_plain_archive(io.BytesIO(data), stage)
        if {p.name for p in stage.iterdir()} != {
            "release.tar.gz",
            "static.tar.gz",
            "certifications.json",
        }:
            raise ValueError("release envelope differs")
        metadata = json.loads((stage / "certifications.json").read_text())
        validate_certificates(metadata, commit)
        if (
            expected_schema is not None
            and metadata["kernel"]["schema_revision"] != expected_schema
        ):
            raise ValueError("manual stopped upgrade forbids a schema change")
        if source_schema is not None:
            require_upgrade_schema(source_schema, metadata["kernel"]["schema_revision"])
        kernel = Path("/opt/brc/releases/manual-kernel-" + commit)
        static = Path("/opt/brc/owner-console/releases/" + commit)
        api = Path("/opt/brc/owner-console-api/releases/" + commit)
        # Recover only our own partial destination. An unrelated tree is never erased.
        for destination in (kernel, api, static):
            marker = destination / ".brc-manual-install-owner"
            if destination.is_symlink():
                raise ValueError("release destination is a symlink")
            if destination.exists():
                if not marker.is_file() or marker.read_text().strip() != commit:
                    raise ValueError("destination is not owned by this candidate")
            else:
                destination.mkdir(parents=True)
                marker.write_text(commit + "\n")
        if not (kernel / ".brc-install-complete").exists():
            with (stage / "release.tar.gz").open("rb") as source:
                extract_plain_archive(source, kernel)
            with (stage / "release.tar.gz").open("rb") as source:
                extract_plain_archive(source, api)
            with (stage / "static.tar.gz").open("rb") as source:
                extract_plain_archive(source, static)
            for destination, name in ((kernel, ".venv"), (api, ".venv-owner-console")):
                run([PYTHON, "-m", "venv", str(destination / name)])
                python = str(destination / name / "bin/python")
                requirement = (
                    "requirements.txt"
                    if name == ".venv"
                    else "requirements-owner-console.txt"
                )
                run(
                    [
                        python,
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "--requirement",
                        str(destination / requirement),
                    ],
                    timeout=600,
                )
            for destination in (kernel, api):
                for name, value in (
                    (".brc-runtime-commit", commit),
                    (".brc-schema-revision", metadata["kernel"]["schema_revision"]),
                    (".brc-product-id", PRODUCT),
                ):
                    (destination / name).write_text(value + "\n")
                shutil.chown(destination, user="root", group="brc")
                destination.chmod(0o750)
            # Runtime code and venv must be readable but not writable by brc.
            run(["chown", "-R", "root:brc", str(kernel), str(api)])
            run(["chown", "-R", "root:www-data", str(static)])
            (kernel / ".brc-install-complete").write_text(commit + "\n")
        receipt = {
            "product_id": PRODUCT,
            "commit": commit,
            "schema_revision": metadata["kernel"]["schema_revision"],
            "kernel_release": str(kernel),
            "api_release": str(api),
            "static_release": str(static),
            "artifacts_sha256": digest,
            "installed_at_ms": int(time.time() * 1000),
            "runtime_activated": False,
        }
        write_private(
            ROOT / "staged-release.json",
            json.dumps(receipt, sort_keys=True) + "\n",
            overwrite=True,
        )
        write_private(
            ROOT / "certifications.json",
            json.dumps(metadata, sort_keys=True) + "\n",
            overwrite=True,
        )
        return receipt
    finally:
        shutil.rmtree(stage)


def read_database(query: str) -> str:
    value = run(
        [
            "docker",
            "exec",
            CONTAINER,
            "psql",
            "-XqAt",
            "-U",
            "brc_manual_admin",
            "-d",
            DATABASE,
            "-c",
            "BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; " + query + "; COMMIT",
        ]
    )
    return value.decode().strip()


def database_foundation(expected_commit: str) -> dict:
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0 or ROOT.stat().st_mode & 0o077:
        raise ValueError("unsafe protected installation directory")
    receipt = json.loads((ROOT / "staged-release.json").read_text())
    if receipt["commit"] != expected_commit or receipt["product_id"] != PRODUCT:
        raise ValueError("staged candidate identity differs")
    secret = ROOT / "database-passwords.json"
    if not secret.exists():
        write_private(
            secret,
            json.dumps(
                {
                    key: secrets.token_hex(32)
                    for key in ("admin", "runtime", "read", "control")
                }
            )
            + "\n",
        )
    passwords = json.loads(secret.read_text())
    admin_password = ROOT / "postgres-admin-password"
    write_private(admin_password, passwords["admin"] + "\n")
    existing = subprocess.run(
        ["docker", "inspect", CONTAINER], capture_output=True, check=False, timeout=15
    )
    if existing.returncode == 0:
        info = json.loads(existing.stdout)[0]
        labels = info["Config"].get("Labels") or {}
        if (
            labels.get("brc.product") != PRODUCT
            or labels.get("brc.machine") != Path("/etc/machine-id").read_text().strip()
        ):
            raise ValueError("existing database container binding differs")
        bindings = info["HostConfig"]["PortBindings"]
        if bindings != {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]}:
            raise ValueError("database port binding differs")
    else:
        volume = "brc-manual-runtime-pg-data"
        if (
            subprocess.run(
                ["docker", "volume", "inspect", volume],
                capture_output=True,
                check=False,
                timeout=15,
            ).returncode
            == 0
        ):
            raise ValueError("unbound pre-existing database volume")
        run(["docker", "pull", "postgres:16-alpine"], timeout=300)
        image = json.loads(run(["docker", "image", "inspect", "postgres:16-alpine"]))[
            0
        ]["RepoDigests"][0]
        run(["docker", "volume", "create", "--label", "brc.product=" + PRODUCT, volume])
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                CONTAINER,
                "--restart",
                "unless-stopped",
                "--label",
                "brc.product=" + PRODUCT,
                "--label",
                "brc.machine=" + Path("/etc/machine-id").read_text().strip(),
                "--publish",
                "127.0.0.1:55432:5432",
                "--memory",
                "768m",
                "--cpus",
                "0.5",
                "--mount",
                "type=volume,source=" + volume + ",target=/var/lib/postgresql/data",
                "--mount",
                "type=bind,source="
                + str(admin_password)
                + ",target=/run/secrets/postgres-password,readonly",
                "--env",
                "POSTGRES_USER=brc_manual_admin",
                "--env",
                "POSTGRES_DB=" + DATABASE,
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
                    CONTAINER,
                    "pg_isready",
                    "-U",
                    "brc_manual_admin",
                    "-d",
                    DATABASE,
                ],
                capture_output=True,
                check=False,
                timeout=15,
            ).returncode
            == 0
        ):
            break
        time.sleep(1)
    else:
        raise RuntimeError("manual PostgreSQL readiness timeout")
    # Refuse installation on any populated foreign schema, even on a labeled container.
    tables = int(
        read_database("SELECT count(*) FROM pg_tables WHERE schemaname='public'")
    )
    completed = ROOT / "database-complete.json"
    if tables and not completed.exists():
        raise ValueError("nonempty database has no completed installation binding")
    env = os.environ.copy()
    admin_dsn = f"postgresql+asyncpg://brc_manual_admin:{passwords['admin']}@127.0.0.1:55432/{DATABASE}"
    if not tables:
        env["TRADING_KERNEL_DATABASE_URL"] = admin_dsn
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        run(
            [
                receipt["kernel_release"] + "/.venv/bin/python",
                receipt["kernel_release"]
                + "/scripts/trading_kernel/bootstrap_schema.py",
            ],
            env=env,
        )
    # Idempotent, least-privilege runtime and existing Owner role definitions.
    role_sql = ""
    for name, key in (
        ("brc_kernel", "runtime"),
        ("brc_owner_console", "read"),
        ("brc_owner_control", "control"),
    ):
        role_sql += f"DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{name}') THEN CREATE ROLE {name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; END $$;\n"
        role_sql += f"ALTER ROLE {name} PASSWORD '{passwords[key]}';\n"
    role_sql += (
        "GRANT CONNECT ON DATABASE "
        + DATABASE
        + " TO brc_kernel; GRANT USAGE ON SCHEMA public TO brc_kernel; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO brc_kernel; GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO brc_kernel;\n"
    )
    for file in ("owner-console-read-role.sql", "owner-console-control-role.sql"):
        role_sql += (
            Path(receipt["kernel_release"]) / "deploy/owner-console/postgresql" / file
        ).read_text() + "\n"
    run(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER,
            "psql",
            "-U",
            "brc_manual_admin",
            "-d",
            DATABASE,
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input_bytes=role_sql.encode(),
    )
    observed = json.loads(
        read_database(
            "SELECT json_build_object('system_identifier',(SELECT system_identifier::text FROM pg_control_system()),'database',current_database(),'schema',(SELECT version_num FROM alembic_version),'profiles',(SELECT count(*) FROM brc_runtime_profiles),'tickets',(SELECT count(*) FROM brc_trade_tickets),'policy_rows',(SELECT count(*) FROM brc_owner_policy_current))"
        )
    )
    if observed["schema"] != receipt["schema_revision"] or any(
        observed[k] for k in ("profiles", "tickets", "policy_rows")
    ):
        raise ValueError("unseeded database shape differs")
    for name, key in (
        ("admin", "admin"),
        ("runtime", "runtime"),
        ("read", "read"),
        ("control", "control"),
    ):
        user = {
            "admin": "brc_manual_admin",
            "runtime": "brc_kernel",
            "read": "brc_owner_console",
            "control": "brc_owner_control",
        }[name]
        write_private(
            ROOT / (name + "-dsn"),
            f"postgresql+asyncpg://{user}:{passwords[key]}@127.0.0.1:55432/{DATABASE}\n",
        )
    result = {
        "product_id": PRODUCT,
        **observed,
        "account_bound": False,
        "entry_fenced": True,
    }
    write_private(completed, json.dumps(result, sort_keys=True) + "\n", overwrite=True)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-id", required=True)
    parser.add_argument("--public-ip", required=True)
    parser.add_argument(
        "--phase",
        choices=("inspect", "receive", "database", "receive-upgrade"),
        required=True,
    )
    parser.add_argument("--commit")
    parser.add_argument("--digest")
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        raise ValueError("manual host provisioning requires root")
    actual = host_facts()
    check_host_identity(actual, vars(args))
    if args.phase == "inspect":
        print(json.dumps(actual))
        return 0
    source = require_stopped_upgrade() if args.phase == "receive-upgrade" else None
    if source is None:
        require_inactive()
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0 or ROOT.stat().st_mode & 0o077:
        raise ValueError("unsafe protected installation directory")
    with open("/run/brc-manual-install.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.phase in {"receive", "receive-upgrade"}:
            result = receive_release(
                args.commit or "",
                args.digest or "",
                sys.stdin.buffer,
                expected_schema=None,
                source_schema=None if source is None else source["schema"],
            )
            if source is not None:
                require_upgrade_schema(source["schema"], result["schema_revision"])
                write_private(
                    ROOT / "upgrade-source.json",
                    json.dumps(
                        {"source": source, "target_commit": args.commit}, sort_keys=True
                    )
                    + "\n",
                    overwrite=True,
                )
        else:
            result = database_foundation(args.commit or "")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - never leak bootstrap credentials in tracebacks.
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_type": type(error).__name__,
                    "message": "manual host installation failed; no exchange mutation performed",
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
