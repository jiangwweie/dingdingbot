#!/usr/bin/env python3
"""Stdlib-only, crash-safe Tokyo runtime deployment state machine."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping
import uuid


STDLIB_IMPORT_ALLOWLIST = frozenset(
    {
        "__future__", "argparse", "ctypes", "fcntl", "hashlib", "json", "os",
        "pathlib", "platform", "stat", "sys", "tempfile", "time", "typing",
        "uuid", "shutil", "shlex", "signal", "subprocess",
    }
)
CANONICAL_LOCK_PATH = Path(
    "/var/lib/brc-deploy/deploy-state/tokyo-runtime-deploy.lock"
)
MAX_JOURNAL_ENTRIES = 48
PRODUCTION_WRITER_UNITS = (
    "brc-owner-console-backend.service",
    "brc-runtime-signal-watcher.service",
    "brc-runtime-signal-watcher.timer",
    "brc-runtime-monitor.service",
    "brc-runtime-monitor.timer",
    "brc-ticket-lifecycle-maintenance.service",
    "brc-ticket-lifecycle-maintenance.timer",
    "brc-runtime-signal-watcher-canary.service",
    "brc-owner-console-canary-readonly.service",
)
REPOSITORY_SYSTEMD_FILES = (
    Path("deploy/systemd/brc-owner-console-backend.service.d/10-runtime-bound.conf"),
    Path("deploy/systemd/brc-owner-console-backend.service.d/30-runtime-order-capable-identity.conf"),
    Path("deploy/systemd/brc-owner-console-backend.service.d/40-runtime-stability.conf"),
    Path("deploy/systemd/brc-owner-console-canary-readonly.service"),
    Path("deploy/systemd/brc-runtime-monitor.service"),
    Path("deploy/systemd/brc-runtime-monitor.timer"),
    Path("deploy/systemd/brc-runtime-signal-watcher-canary.service"),
    Path("deploy/systemd/brc-runtime-signal-watcher.service"),
    Path("deploy/systemd/brc-runtime-signal-watcher.service.d/80-product-state-refresh.conf"),
    Path("deploy/systemd/brc-runtime-signal-watcher.service.d/85-action-time-refresh-if-needed.conf"),
    Path("deploy/systemd/brc-runtime-signal-watcher.service.d/90-resume-dispatcher-after-refresh.conf"),
    Path("deploy/systemd/brc-runtime-signal-watcher.timer"),
    Path("deploy/systemd/brc-ticket-lifecycle-maintenance.service"),
    Path("deploy/systemd/brc-ticket-lifecycle-maintenance.timer"),
)


class ChildResult:
    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = int(returncode)
        self.stdout = str(stdout)
        self.stderr = str(stderr)


_subprocess_run_locked = subprocess.run


def spawn_locked_mutation_child(
    command: list[str],
    *,
    lock_handle: Any,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
    cwd: Path,
    timeout: int,
    env: Mapping[str, str] | None = None,
) -> ChildResult:
    """Run one bounded mutation while retaining and revalidating the deploy lock."""

    forbidden = {"systemd-run", "setsid", "daemonize"}
    if not command or any(Path(token).name in forbidden for token in command):
        raise ValueError("mutation_child_escape_forbidden")
    lock_fd = int(lock_handle.fileno())
    expected_uid = 0 if require_root_owner else os.geteuid()
    identity = _verify_lock_identity(
        lock_fd,
        Path(canonical_lock_path),
        expected_uid=expected_uid,
    )
    parent_pid = os.getpid()

    def child_guard() -> None:
        if os.getppid() != parent_pid:
            os._exit(125)
        _verify_lock_identity(
            lock_fd,
            Path(canonical_lock_path),
            expected_uid=expected_uid,
            expected_identity=identity,
        )
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
            os._exit(126)
        if os.getppid() != parent_pid:
            os._exit(125)

    completed = _subprocess_run_locked(
        command,
        cwd=Path(cwd),
        timeout=int(timeout),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=(lock_fd,),
        start_new_session=False,
        preexec_fn=child_guard,
        env=dict(env) if env is not None else None,
    )
    return ChildResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _verify_lock_identity(
    lock_fd: int,
    canonical_lock_path: Path,
    *,
    expected_uid: int,
    expected_identity: tuple[int, int] | None = None,
) -> tuple[int, int]:
    fd_info = os.fstat(lock_fd)
    path_info = Path(canonical_lock_path).lstat()
    identity = (fd_info.st_dev, fd_info.st_ino)
    if (
        not stat.S_ISREG(fd_info.st_mode)
        or fd_info.st_uid != expected_uid
        or stat.S_IMODE(fd_info.st_mode) != 0o600
        or fd_info.st_nlink != 1
        or identity != (path_info.st_dev, path_info.st_ino)
        or (expected_identity is not None and identity != expected_identity)
    ):
        raise ValueError("deploy_lock_identity_invalid")
    return identity


def validate_bootstrap_environment(
    *,
    source: bytes,
    expected_sha256: str,
    version_info: tuple[int, ...] | None = None,
    euid: int | None = None,
    state_initializer: Callable[[], Any] | None = None,
) -> None:
    actual = hashlib.sha256(source).hexdigest()
    if actual != expected_sha256:
        raise ValueError("bootstrap_sha256_mismatch")
    version = tuple(version_info or sys.version_info[:3])
    if version[:2] != (3, 10) or platform.python_implementation() != "CPython":
        raise ValueError("bootstrap_python_abi_mismatch")
    if int(os.geteuid() if euid is None else euid) != 0:
        raise ValueError("bootstrap_root_required")
    if state_initializer is not None:
        state_initializer()


def acquire_deploy_lock(
    path: Path = CANONICAL_LOCK_PATH,
    *,
    require_root_owner: bool = True,
):
    path = Path(path)
    _ensure_safe_lock_parent(path.parent, require_root_owner=require_root_owner)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC
    fd = os.open(path, flags, 0o600)
    handle = os.fdopen(fd, "r+b", closefd=True)
    try:
        info = os.fstat(handle.fileno())
        lookup = path.lstat()
        expected_uid = 0 if require_root_owner else os.geteuid()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != expected_uid
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (lookup.st_dev, lookup.st_ino)
        ):
            raise ValueError("deploy_lock_identity_invalid")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        return handle
    except Exception:
        if not handle.closed:
            handle.close()
        raise


def _ensure_safe_lock_parent(path: Path, *, require_root_owner: bool) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.stat()
    expected_uid = 0 if require_root_owner else os.geteuid()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != expected_uid
        or info.st_mode & 0o022
    ):
        raise ValueError("deploy_lock_parent_unsafe")


def dependency_identity(lock_path: Path) -> str:
    raw = Path(lock_path).read_bytes()
    if not raw:
        raise ValueError("runtime_dependency_lock_empty")
    return hashlib.sha256(raw).hexdigest() + "-cp310-linux_x86_64"


def stage_candidate_release(
    *,
    deploy_root: Path,
    repo_url: str,
    git_ref: str,
    target_sha: str,
    release_name: str,
    lock_handle: Any,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
    runner: Callable[..., ChildResult] | None = None,
) -> dict[str, Any]:
    """Fetch and export one exact commit without relying on candidate code."""

    target_sha = _sha(target_sha, "target_sha")
    repo_url = _required(repo_url, "repo_url")
    git_ref = _required(git_ref, "git_ref")
    release_name = _required(release_name, "release_name")
    if "/" in release_name or release_name in {".", ".."}:
        raise ValueError("release_name_invalid")
    deploy_root = Path(deploy_root)
    source_root = deploy_root / "source"
    source_repo = source_root / "dingdingbot"
    releases = deploy_root / "releases"
    release = releases / release_name
    temporary = releases / f"{release_name}.tmp"
    archive = deploy_root / "deploy-state" / f"{release_name}.{target_sha}.tar"
    manifest = release / ".brc-release-manifest.json"

    if release.exists():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("target_sha") != target_sha:
            raise ValueError("candidate_release_identity_mismatch")
        return {"status": "candidate_release_staged", "release_path": str(release)}

    source_root.mkdir(parents=True, exist_ok=True, mode=0o755)
    releases.mkdir(parents=True, exist_ok=True, mode=0o755)
    archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def run(command: list[str], *, cwd: Path, timeout: int) -> ChildResult:
        if runner is not None:
            return runner(command, cwd=cwd, timeout=timeout)
        return spawn_locked_mutation_child(
            command,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
            cwd=cwd,
            timeout=timeout,
        )

    commands: list[tuple[list[str], Path, int]] = []
    if not (source_repo / ".git").is_dir():
        commands.append(
            (["/usr/bin/git", "clone", "--no-checkout", repo_url, str(source_repo)], source_root, 300)
        )
    commands.extend(
        [
            (["/usr/bin/git", "fetch", "--prune", "origin", git_ref], source_repo, 300),
            (["/usr/bin/git", "rev-parse", "FETCH_HEAD"], source_repo, 30),
        ]
    )
    resolved = None
    for command, cwd, timeout in commands:
        result = run(command, cwd=cwd, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError("candidate_export_command_failed:" + Path(command[0]).name)
        if command[1:3] == ["rev-parse", "FETCH_HEAD"]:
            resolved = result.stdout.strip()
    if resolved != target_sha:
        raise ValueError("candidate_fetch_head_mismatch")

    if temporary.exists():
        if temporary.is_symlink():
            raise ValueError("candidate_temporary_path_unsafe")
        shutil.rmtree(temporary)
    temporary.mkdir(mode=0o755)
    for command, cwd, timeout in (
        (["/usr/bin/git", "archive", "--format=tar", "-o", str(archive), target_sha], source_repo, 120),
        (["/usr/bin/tar", "-xf", str(archive), "-C", str(temporary)], releases, 120),
    ):
        result = run(command, cwd=cwd, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError("candidate_export_command_failed:" + Path(command[0]).name)
    _atomic_json_write(
        temporary / ".brc-release-manifest.json",
        {
            "schema": "brc.runtime_release_manifest.v2",
            "target_sha": target_sha,
            "git_ref": git_ref,
            "repo_url": repo_url,
            "git_deploy": {"target_commit": target_sha},
        },
    )
    os.replace(temporary, release)
    _fsync_directory(releases)
    if archive.exists():
        archive.unlink()
        _fsync_directory(archive.parent)
    return {"status": "candidate_release_staged", "release_path": str(release)}


def build_immutable_venv(
    *,
    release_path: Path,
    lock_path: Path,
    venv_root: Path,
    base_python: str = "/usr/bin/python3",
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    release_path = Path(release_path).resolve(strict=True)
    lock_path = Path(lock_path).resolve(strict=True)
    identity = dependency_identity(lock_path)
    target = Path(venv_root) / identity
    complete = target / ".complete"
    if target.exists() and not complete.is_file():
        if target.is_symlink():
            raise ValueError("immutable_venv_partial_path_unsafe")
        shutil.rmtree(target)
    if runner is not None:
        command_runner = runner
    elif lock_handle is not None:
        def command_runner(command, *, cwd, timeout):
            return spawn_locked_mutation_child(
                command,
                lock_handle=lock_handle,
                canonical_lock_path=canonical_lock_path,
                require_root_owner=require_root_owner,
                cwd=cwd,
                timeout=timeout,
            )
    else:
        raise ValueError("immutable_venv_lock_required")
    if not complete.is_file():
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        commands = (
            ([base_python, "-m", "venv", str(target)], 120),
            (
                [
                    str(target / "bin/python"), "-m", "pip", "install",
                    "--disable-pip-version-check", "--require-hashes", "-r",
                    str(lock_path),
                ],
                900,
            ),
            ([str(target / "bin/python"), "-m", "pip", "check"], 60),
            (
                [
                    str(target / "bin/python"), "-c",
                    "import alembic,ccxt,fastapi,psycopg,sqlalchemy; "
                    "assert ccxt.__version__ == '4.5.56'",
                ],
                60,
            ),
            (
                [str(target / "bin/python"), "-m", "compileall", "-q", "src"],
                120,
            ),
        )
        for command, timeout in commands:
            result = command_runner(
                command,
                cwd=release_path,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "immutable_venv_command_failed:"
                    + Path(command[0]).name
                    + ":"
                    + result.stderr[-300:]
                )
        _atomic_json_write(
            complete,
            {
                "schema": "brc.immutable_runtime_venv.v1",
                "dependency_identity": identity,
                "ccxt_version": "4.5.56",
                "python_abi_platform": "cp310-linux_x86_64",
            },
        )
    release_link = release_path / ".venv"
    if os.path.lexists(release_link):
        if not release_link.is_symlink() or release_link.resolve() != target.resolve():
            raise ValueError("release_venv_binding_mismatch")
    else:
        temporary = release_path / f".venv.{uuid.uuid4().hex}.tmp"
        os.symlink(str(target), temporary)
        os.replace(temporary, release_link)
        _fsync_directory(release_path)
    return {
        "status": "immutable_venv_ready",
        "dependency_identity": identity,
        "venv_path": str(target),
        "release_venv": str(release_link),
    }


def ensure_previous_release_venv_compatibility(
    *,
    previous_release_path: Path,
    deployed_venv_path: Path,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    """Bind the legacy release to its existing interpreter before unit changes."""

    previous = Path(previous_release_path).resolve(strict=True)
    deployed = Path(deployed_venv_path).resolve(strict=True)
    if not (deployed / "bin/python").is_file():
        raise ValueError("previous_release_deployed_venv_invalid")
    link = previous / ".venv"
    if os.path.lexists(link):
        if not link.is_symlink() or link.resolve() != deployed:
            raise ValueError("previous_release_venv_binding_mismatch")
    else:
        temporary = previous / f".venv.{uuid.uuid4().hex}.tmp"
        os.symlink(str(deployed), temporary)
        os.replace(temporary, link)
        _fsync_directory(previous)
    command = [str(link / "bin/python"), "-c", "import src.main"]
    if runner is not None:
        result = runner(command, cwd=previous, timeout=60)
    elif lock_handle is not None:
        result = spawn_locked_mutation_child(
            command,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
            cwd=previous,
            timeout=60,
        )
    else:
        raise ValueError("previous_release_venv_lock_required")
    if result.returncode != 0:
        raise RuntimeError("previous_release_import_probe_failed")
    return {
        "status": "previous_release_venv_compatible",
        "previous_release": str(previous),
        "venv_path": str(deployed),
    }


def engage_production_writer_fence(
    *,
    release_path: Path,
    transaction_id: str,
    deploy_nonce: str,
    target_sha: str,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
    systemd_root: Path = Path("/etc/systemd/system"),
) -> dict[str, Any]:
    """Install boot-persistent interlocks, engage marker, then stop writers."""

    release = Path(release_path).resolve(strict=True)
    python = release / ".venv/bin/python"
    helper = release / "scripts/set_production_writer_fence.py"
    dropin = release / "deploy/systemd/production-writer-fence.conf"
    for required in (python, helper, dropin):
        if not required.is_file():
            raise ValueError("writer_fence_release_input_missing:" + required.name)
    target_sha = _sha(target_sha, "target_sha")

    def run(command: list[str], timeout: int = 60) -> ChildResult:
        if runner is not None:
            result = runner(command, cwd=release, timeout=timeout)
        elif lock_handle is not None:
            result = spawn_locked_mutation_child(
                command,
                lock_handle=lock_handle,
                canonical_lock_path=canonical_lock_path,
                require_root_owner=require_root_owner,
                cwd=release,
                timeout=timeout,
            )
        else:
            raise ValueError("writer_fence_lock_required")
        if result.returncode != 0:
            raise RuntimeError("writer_fence_command_failed:" + Path(command[0]).name)
        return result

    for unit in PRODUCTION_WRITER_UNITS:
        destination = Path(systemd_root) / f"{unit}.d/05-production-writer-fence.conf"
        run(["/usr/bin/install", "-D", "-m", "0644", str(dropin), str(destination)])
    run(["/usr/bin/systemctl", "daemon-reload"])
    fence = run(
        [
            str(python), str(helper), "--engage",
            "--deploy-transaction-id", _required(transaction_id, "transaction_id"),
            "--deploy-nonce", _required(deploy_nonce, "deploy_nonce"),
            "--target-runtime-head", target_sha,
        ]
    )
    try:
        fence_payload = json.loads(fence.stdout)
        fence_inode = int(fence_payload["inode"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("writer_fence_receipt_invalid") from exc
    run(["/usr/bin/systemctl", "stop", *PRODUCTION_WRITER_UNITS], timeout=180)
    states = run(
        ["/usr/bin/systemctl", "show", "--property=ActiveState", "--value", *PRODUCTION_WRITER_UNITS]
    ).stdout.splitlines()
    if states and any(state.strip() in {"active", "activating", "reloading"} for state in states):
        raise RuntimeError("production_writer_still_active")
    return {
        "status": "production_writers_fenced",
        "fence_inode": fence_inode,
        "writer_units": list(PRODUCTION_WRITER_UNITS),
    }


def load_runtime_environment(path: Path) -> dict[str, str]:
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o002:
        raise ValueError("runtime_env_file_unsafe")
    environment = dict(os.environ)
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"runtime_env_line_invalid:{line_number}")
        key, encoded = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "A").isalnum() or key[0].isdigit():
            raise ValueError(f"runtime_env_key_invalid:{line_number}")
        values = shlex.split(encoded, posix=True)
        if len(values) > 1:
            raise ValueError(f"runtime_env_value_invalid:{line_number}")
        environment[key] = values[0] if values else ""
    return environment


def run_fenced_schema_migration(
    *,
    release_path: Path,
    env_path: Path,
    transaction_id: str,
    expected_revision: str,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    """Quiesce lifecycle mutation and run schema changes with candidate Python."""

    release = Path(release_path).resolve(strict=True)
    python = release / ".venv/bin/python"
    if not python.is_file():
        raise ValueError("candidate_python_missing")
    if not str(expected_revision).isdigit():
        raise ValueError("expected_revision_invalid")
    environment = load_runtime_environment(Path(env_path))
    environment["PYTHONPATH"] = str(release)

    def run(arguments: list[str], timeout: int = 120) -> ChildResult:
        command = [str(python), *arguments]
        if runner is not None:
            result = runner(command, cwd=release, timeout=timeout, env=environment)
        elif lock_handle is not None:
            result = spawn_locked_mutation_child(
                command,
                lock_handle=lock_handle,
                canonical_lock_path=canonical_lock_path,
                require_root_owner=require_root_owner,
                cwd=release,
                timeout=timeout,
                env=environment,
            )
        else:
            raise ValueError("schema_migration_lock_required")
        if result.returncode != 0:
            raise RuntimeError("fenced_schema_command_failed:" + ":".join(arguments[:3]))
        return result

    status_result = run(
        ["scripts/set_ticket_lifecycle_mutation_capability.py", "--status", "--require-database-url", "--json"]
    )
    try:
        status_payload = json.loads(status_result.stdout)
        was_enabled = bool(status_payload["enabled"])
        if status_payload.get("exchange_write_called") is not False:
            raise ValueError("lifecycle_status_exchange_side_effect")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("lifecycle_capability_status_invalid") from exc
    run(
        [
            "scripts/verify_ticket_lifecycle_phase_two_readiness.py",
            "--require-database-url", "--deploy-quiescence", "--json",
        ]
    )
    run(
        [
            "scripts/set_ticket_lifecycle_mutation_capability.py", "--disable",
            "--require-database-url", "--certification-ref",
            f"deploy-quiesce:{_required(transaction_id, 'transaction_id')}", "--json",
        ]
    )
    run(["scripts/check_runtime_postgres_ready.py", "--require-database-url", "--json"])
    run(["-m", "alembic", "heads"])
    run(["-m", "alembic", "upgrade", "head"], timeout=300)
    run(["scripts/seed_runtime_control_state_foundation.py", "--apply", "--json"], timeout=180)
    run(["scripts/validate_runtime_control_state_repository.py", "--json"])
    current = run(["-m", "alembic", "current"]).stdout
    if str(expected_revision) not in current.split():
        raise RuntimeError("schema_revision_mismatch")
    return {
        "status": "schema_migrated",
        "revision": str(expected_revision),
        "lifecycle_capability_was_enabled": was_enabled,
    }


def install_candidate_units_and_switch_pointer(
    *,
    release_path: Path,
    app_current: Path,
    target_sha: str,
    systemd_root: Path = Path("/etc/systemd/system"),
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    """Install candidate-owned unit definitions and atomically activate its pointer."""

    release = Path(release_path).resolve(strict=True)
    python = release / ".venv/bin/python"
    helper = release / "scripts/atomic_switch_release_pointer.py"
    if not python.is_file() or not helper.is_file():
        raise ValueError("pointer_switch_release_input_missing")

    def run(command: list[str], timeout: int = 60) -> ChildResult:
        if runner is not None:
            result = runner(command, cwd=release, timeout=timeout)
        elif lock_handle is not None:
            result = spawn_locked_mutation_child(
                command,
                lock_handle=lock_handle,
                canonical_lock_path=canonical_lock_path,
                require_root_owner=require_root_owner,
                cwd=release,
                timeout=timeout,
            )
        else:
            raise ValueError("pointer_switch_lock_required")
        if result.returncode != 0:
            raise RuntimeError("pointer_switch_command_failed:" + Path(command[0]).name)
        return result

    source_root = Path("deploy/systemd")
    for relative in REPOSITORY_SYSTEMD_FILES:
        source = release / relative
        if not source.is_file():
            raise ValueError("candidate_systemd_file_missing:" + str(relative))
        destination = Path(systemd_root) / relative.relative_to(source_root)
        run(["/usr/bin/install", "-D", "-m", "0644", str(source), str(destination)])
    run(["/usr/bin/systemctl", "daemon-reload"])
    pointer = run(
        [
            str(python), str(helper),
            "--current", str(app_current),
            "--target", str(release),
            "--expected-sha", _sha(target_sha, "target_sha"),
        ]
    )
    try:
        payload = json.loads(pointer.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("pointer_switch_receipt_invalid") from exc
    if (
        payload.get("status") != "release_pointer_switched"
        or payload.get("target_runtime_head") != target_sha
        or payload.get("release_pointer") != str(app_current)
    ):
        raise RuntimeError("pointer_switch_receipt_mismatch")
    return {
        "status": "candidate_pointer_active",
        "release_pointer": str(app_current),
        "target_runtime_head": target_sha,
    }


def _run_child(command: list[str], *, cwd: Path, timeout: int) -> ChildResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        timeout=timeout,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return ChildResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class DeployJournal:
    def __init__(
        self,
        path: Path,
        *,
        transaction_id: str,
        deploy_nonce: str,
        old_sha: str,
        target_sha: str,
        entries: list[dict[str, Any]] | None = None,
    ) -> None:
        self.path = Path(path)
        self.transaction_id = _required(transaction_id, "transaction_id")
        self.deploy_nonce = _required(deploy_nonce, "deploy_nonce")
        self.old_sha = _sha(old_sha, "old_sha")
        self.target_sha = _sha(target_sha, "target_sha")
        self.entries = list(entries or [])

    def append(self, phase: str, facts: Mapping[str, Any]) -> dict[str, Any]:
        if len(self.entries) >= MAX_JOURNAL_ENTRIES:
            raise ValueError("deploy_journal_entry_limit_exceeded")
        previous = self.entries[-1] if self.entries else None
        entry = {
            "sequence": len(self.entries) + 1,
            "phase": _required(phase, "phase"),
            "previous_phase": previous["phase"] if previous else None,
            "previous_digest": previous["entry_digest"] if previous else None,
            "deploy_transaction_id": self.transaction_id,
            "deploy_nonce": self.deploy_nonce,
            "old_sha": self.old_sha,
            "target_sha": self.target_sha,
            "recorded_at_ms": int(time.time() * 1000),
            "facts": dict(facts),
        }
        entry["entry_digest"] = _digest(entry)
        self.entries.append(entry)
        self._persist()
        return entry

    def _persist(self) -> None:
        payload = {
            "schema": "brc.tokyo_runtime_deploy_journal.v1",
            "transaction_id": self.transaction_id,
            "deploy_nonce": self.deploy_nonce,
            "old_sha": self.old_sha,
            "target_sha": self.target_sha,
            "entries": self.entries,
        }
        _atomic_json_write(self.path, payload)

    @classmethod
    def load(cls, path: Path) -> "DeployJournal":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema") != "brc.tokyo_runtime_deploy_journal.v1":
            raise ValueError("deploy_journal_schema_invalid")
        entries = payload.get("entries")
        if not isinstance(entries, list) or len(entries) > MAX_JOURNAL_ENTRIES:
            raise ValueError("deploy_journal_entries_invalid")
        previous = None
        for index, entry in enumerate(entries, start=1):
            candidate = dict(entry)
            digest = candidate.pop("entry_digest", None)
            if (
                entry.get("sequence") != index
                or entry.get("previous_digest") != (
                    previous.get("entry_digest") if previous else None
                )
                or digest != _digest(candidate)
            ):
                raise ValueError("deploy_journal_hash_chain_invalid")
            previous = entry
        return cls(
            Path(path),
            transaction_id=payload["transaction_id"],
            deploy_nonce=payload["deploy_nonce"],
            old_sha=payload["old_sha"],
            target_sha=payload["target_sha"],
            entries=entries,
        )


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = _canonical_bytes(payload) + b"\n"
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(fd)
        fd = -1
        os.replace(temp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        if temp.exists():
            temp.unlink()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _required(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name}_required")
    return text


def _sha(value: str, name: str) -> str:
    text = _required(value, name)
    if len(text) != 40 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{name}_invalid")
    return text


def main(
    argv: list[str] | None = None,
    *,
    bootstrap_source: bytes | None = None,
    bootstrap_euid: int | None = None,
    require_root_lock_owner: bool = True,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-sha256", required=True)
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--deploy-nonce", required=True)
    parser.add_argument("--old-sha", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--source-path")
    parser.add_argument("--deploy-root")
    parser.add_argument("--repo-url")
    parser.add_argument("--git-ref")
    parser.add_argument("--release-name")
    parser.add_argument("--previous-release-path")
    parser.add_argument("--service-name")
    parser.add_argument("--env-path")
    parser.add_argument("--expected-latest-migration")
    args = parser.parse_args(argv)
    source = bootstrap_source
    if source is None:
        source = globals().get("__bootstrap_source__")
    if source is None and args.source_path:
        source = Path(args.source_path).read_bytes()
    if not isinstance(source, bytes):
        raise ValueError("bootstrap_source_missing")
    validate_bootstrap_environment(
        source=source,
        expected_sha256=args.bootstrap_sha256,
        euid=bootstrap_euid,
    )
    lock = acquire_deploy_lock(
        CANONICAL_LOCK_PATH,
        require_root_owner=require_root_lock_owner,
    )
    if lock is None:
        print(json.dumps({"status": "deploy_in_progress"}))
        return 3
    try:
        print(json.dumps({"status": "lock_acquired", "transaction_id": args.transaction_id}))
        return 0
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
