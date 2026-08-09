#!/usr/bin/env python3
"""Export one consistent Tokyo PostgreSQL data-only snapshot for local testing."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIRECTORY = REPO_ROOT / ".local" / "owner-console-snapshots"
_DATABASE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
_SSH_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,255}$")
_CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ROLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_DEFAULT_POSTGRES_CONTAINER = "brc-trading-kernel-pg"
_DEFAULT_POSTGRES_USER = "brc_kernel"
_SENSITIVE_COLUMN = re.compile(
    r"(?:password|secret|api_key|totp|credential|token)",
    re.IGNORECASE,
)
_ALLOWED_RUNTIME_TOKEN_COLUMNS = frozenset({"claim_token"})
_PARITY_KEYS = (
    "brc_signal_events",
    "brc_trade_tickets",
    "brc_trade_aggregates",
    "brc_trade_reviews",
    "open_brc_runtime_incidents",
)


def build_remote_dump_command(
    *,
    database_name: str,
    postgres_container: str = _DEFAULT_POSTGRES_CONTAINER,
    postgres_user: str = _DEFAULT_POSTGRES_USER,
) -> str:
    """Return the exact single-process data-only pg_dump command."""

    _validate_database_name(database_name)
    _validate_postgres_identity(
        postgres_container=postgres_container,
        postgres_user=postgres_user,
    )
    return shlex.join(
        (
            "sudo",
            "-n",
            "docker",
            "exec",
            postgres_container,
            "pg_dump",
            "--username",
            postgres_user,
            "--dbname",
            database_name,
            "--data-only",
            "--inserts",
            "--rows-per-insert=100",
            "--serializable-deferrable",
            "--lock-wait-timeout=3000",
            "--no-owner",
            "--no-privileges",
            "--schema=public",
            "--exclude-table=alembic_version",
        )
    )


def validate_schema_column_names(column_names: tuple[str, ...]) -> None:
    """Reject credential-like persisted columns before exporting any rows."""

    unsafe = tuple(
        name
        for name in column_names
        if name not in _ALLOWED_RUNTIME_TOKEN_COLUMNS
        and _SENSITIVE_COLUMN.search(name) is not None
    )
    if unsafe:
        raise ValueError(
            "credential-like PostgreSQL columns block Owner Console export: "
            + ", ".join(sorted(set(unsafe)))
        )


def _validate_database_name(database_name: str) -> None:
    if _DATABASE_NAME.fullmatch(database_name) is None:
        raise ValueError("remote database name is invalid")


def _validate_ssh_host(ssh_host: str) -> None:
    if _SSH_HOST.fullmatch(ssh_host) is None:
        raise ValueError("SSH host must be one safe alias or user@host token")


def _validate_postgres_identity(
    *,
    postgres_container: str,
    postgres_user: str,
) -> None:
    if _CONTAINER_NAME.fullmatch(postgres_container) is None:
        raise ValueError("remote PostgreSQL container name is invalid")
    if _ROLE_NAME.fullmatch(postgres_user) is None:
        raise ValueError("remote PostgreSQL user name is invalid")


def _validated_output_directory(output_dir: Path) -> Path:
    root = DEFAULT_OUTPUT_DIRECTORY.resolve()
    resolved = output_dir.expanduser().resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("snapshot output must stay under .local/owner-console-snapshots")
    resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(resolved, 0o700)
    return resolved


def _remote_psql_command(
    *,
    database_name: str,
    postgres_container: str,
    postgres_user: str,
    sql: str,
) -> tuple[str, ...]:
    return (
        "sudo",
        "-n",
        "docker",
        "exec",
        postgres_container,
        "psql",
        "--no-psqlrc",
        "--set",
        "ON_ERROR_STOP=1",
        "--tuples-only",
        "--no-align",
        "--username",
        postgres_user,
        "--dbname",
        database_name,
        "--command",
        sql,
    )


def _run_remote_text(
    *,
    ssh_host: str,
    remote_command: tuple[str, ...],
    timeout_seconds: float = 30.0,
) -> str:
    completed = subprocess.run(
        ("ssh", "--", ssh_host, shlex.join(remote_command)),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "readonly Tokyo PostgreSQL preflight failed: "
            + completed.stderr.strip()[-2_000:]
        )
    return completed.stdout.strip()


def _read_remote_snapshot_facts(
    *,
    ssh_host: str,
    database_name: str,
    postgres_container: str,
    postgres_user: str,
) -> tuple[str, str, dict[str, int]]:
    column_output = _run_remote_text(
        ssh_host=ssh_host,
        remote_command=_remote_psql_command(
            database_name=database_name,
            postgres_container=postgres_container,
            postgres_user=postgres_user,
            sql=(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY table_schema, table_name, ordinal_position"
            ),
        ),
    )
    validate_schema_column_names(
        tuple(line for line in column_output.splitlines() if line)
    )
    version = _run_remote_text(
        ssh_host=ssh_host,
        remote_command=_remote_psql_command(
            database_name=database_name,
            postgres_container=postgres_container,
            postgres_user=postgres_user,
            sql="SHOW server_version",
        ),
    )
    revision = _run_remote_text(
        ssh_host=ssh_host,
        remote_command=_remote_psql_command(
            database_name=database_name,
            postgres_container=postgres_container,
            postgres_user=postgres_user,
            sql="SELECT version_num FROM alembic_version",
        ),
    )
    count_payload = _run_remote_text(
        ssh_host=ssh_host,
        remote_command=_remote_psql_command(
            database_name=database_name,
            postgres_container=postgres_container,
            postgres_user=postgres_user,
            sql=_parity_count_sql(),
        ),
    )
    try:
        counts = json.loads(count_payload)
    except json.JSONDecodeError as error:
        raise RuntimeError("Tokyo parity-count preflight returned invalid JSON") from error
    if not isinstance(counts, dict) or set(counts) != set(_PARITY_KEYS):
        raise RuntimeError("Tokyo parity-count preflight returned invalid keys")
    normalized_counts = {
        key: _require_nonnegative_count(counts[key], key=key)
        for key in _PARITY_KEYS
    }
    return version, revision, normalized_counts


def _parity_count_sql() -> str:
    return (
        "SELECT json_build_object("
        "'brc_signal_events', (SELECT count(*) FROM brc_signal_events), "
        "'brc_trade_tickets', (SELECT count(*) FROM brc_trade_tickets), "
        "'brc_trade_aggregates', (SELECT count(*) FROM brc_trade_aggregates), "
        "'brc_trade_reviews', (SELECT count(*) FROM brc_trade_reviews), "
        "'open_brc_runtime_incidents', "
        "(SELECT count(*) FROM brc_runtime_incidents WHERE status = 'open')"
        ")::text"
    )


def _require_nonnegative_count(value: Any, *, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(f"Tokyo parity count is invalid: {key}")
    return value


def _stream_remote_dump(
    *,
    ssh_host: str,
    database_name: str,
    postgres_container: str,
    postgres_user: str,
    temporary_path: Path,
) -> None:
    process = subprocess.Popen(
        (
            "ssh",
            "--",
            ssh_host,
            build_remote_dump_command(
                database_name=database_name,
                postgres_container=postgres_container,
                postgres_user=postgres_user,
            ),
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("SSH dump stream could not be opened")
    try:
        with temporary_path.open("xb") as compressed_file:
            os.chmod(temporary_path, 0o600)
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=compressed_file,
                mtime=0,
            ) as gzip_file:
                shutil.copyfileobj(process.stdout, gzip_file, length=1024 * 1024)
        process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        returncode = process.wait(timeout=300)
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        process.stderr.close()
    if returncode != 0:
        raise RuntimeError("remote pg_dump failed: " + stderr.strip()[-2_000:])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomically(path: Path, payload: dict[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def export_snapshot(
    *,
    ssh_host: str,
    database_name: str,
    output_dir: Path,
    postgres_container: str = _DEFAULT_POSTGRES_CONTAINER,
    postgres_user: str = _DEFAULT_POSTGRES_USER,
) -> tuple[Path, Path, str]:
    _validate_ssh_host(ssh_host)
    _validate_database_name(database_name)
    _validate_postgres_identity(
        postgres_container=postgres_container,
        postgres_user=postgres_user,
    )
    target_directory = _validated_output_directory(output_dir)
    captured_at = datetime.now(UTC).replace(microsecond=0)
    timestamp = captured_at.strftime("%Y%m%dT%H%M%SZ")
    artifact = target_directory / f"{timestamp}-{database_name}.sql.gz"
    metadata = artifact.with_suffix("").with_suffix(".json")
    temporary_artifact = target_directory / f".{artifact.name}.tmp"
    if artifact.exists() or metadata.exists() or temporary_artifact.exists():
        raise FileExistsError("snapshot target already exists")

    version, revision, counts_before = _read_remote_snapshot_facts(
        ssh_host=ssh_host,
        database_name=database_name,
        postgres_container=postgres_container,
        postgres_user=postgres_user,
    )
    try:
        _stream_remote_dump(
            ssh_host=ssh_host,
            database_name=database_name,
            postgres_container=postgres_container,
            postgres_user=postgres_user,
            temporary_path=temporary_artifact,
        )
        _, revision_after, counts_after = _read_remote_snapshot_facts(
            ssh_host=ssh_host,
            database_name=database_name,
            postgres_container=postgres_container,
            postgres_user=postgres_user,
        )
        if revision_after != revision:
            raise RuntimeError("Tokyo Alembic revision changed during snapshot export")
        if counts_after != counts_before:
            raise RuntimeError("Tokyo parity counts changed during snapshot export")
        os.replace(temporary_artifact, artifact)
        os.chmod(artifact, 0o600)
        digest = _sha256(artifact)
        _write_json_atomically(
            metadata,
            {
                "captured_at_utc": captured_at.isoformat().replace("+00:00", "Z"),
                "ssh_host": ssh_host,
                "database_name": database_name,
                "postgresql_version": version,
                "alembic_revision": revision,
                "compressed_bytes": artifact.stat().st_size,
                "sha256": digest,
                "parity_counts": counts_before,
            },
        )
    except BaseException:
        temporary_artifact.unlink(missing_ok=True)
        artifact.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)
        raise
    return artifact, metadata, digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--remote-database", required=True)
    parser.add_argument(
        "--postgres-container",
        default=_DEFAULT_POSTGRES_CONTAINER,
    )
    parser.add_argument("--postgres-user", default=_DEFAULT_POSTGRES_USER)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    artifact, metadata, digest = export_snapshot(
        ssh_host=args.ssh_host,
        database_name=args.remote_database,
        output_dir=args.output_dir,
        postgres_container=args.postgres_container,
        postgres_user=args.postgres_user,
    )
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "metadata": str(metadata),
                "sha256": digest,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
