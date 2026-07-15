#!/usr/bin/env python3
"""Stdlib-only, crash-safe Tokyo runtime deployment state machine."""

from __future__ import annotations

import argparse
import ctypes
import errno
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
        "__future__", "argparse", "ctypes", "errno", "fcntl", "hashlib", "json", "os",
        "pathlib", "platform", "stat", "sys", "tempfile", "time", "typing",
        "uuid", "shutil", "shlex", "signal", "subprocess",
    }
)
CANONICAL_LOCK_PATH = Path(
    "/var/lib/brc-deploy/deploy-state/tokyo-runtime-deploy.lock"
)
MAX_JOURNAL_ENTRIES = 48
DEPLOY_PHASES = (
    "bootstrap_locked",
    "candidate_staged",
    "immutable_venv_ready",
    "previous_release_venv_compatible",
    "production_writers_fenced",
    "pre_migration",
    "migration_in_progress",
    "schema_migrated",
    "pointer_active",
    "release_activation_recorded",
    "pre_canary_facts",
    "pre_canary_certified",
    "pre_canary_projection",
    "pre_canary_sentinel",
    "readonly_canary_complete",
    "post_canary_sentinel",
    "post_canary_facts",
    "post_canary_certified",
    "post_canary_projection",
    "activation_machine_facts_verified",
    "lifecycle_proof_persisted",
    "runtime_activation_committed",
    "policy_applied",
    "terminal_manifest_consumed",
)
PRODUCTION_WRITER_UNITS = (
    "brc-owner-console-backend.service",
    "brc-runtime-signal-watcher.service",
    "brc-runtime-signal-watcher.timer",
    "brc-runtime-monitor.service",
    "brc-runtime-monitor.timer",
    "brc-ticket-lifecycle-maintenance.service",
    "brc-ticket-lifecycle-maintenance.timer",
)
DEPLOY_STOP_UNITS = PRODUCTION_WRITER_UNITS + (
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
    if require_root_owner and path == CANONICAL_LOCK_PATH:
        return _acquire_lock_beneath_root(
            root=Path("/var/lib"),
            directory_components=("brc-deploy", "deploy-state"),
            lock_name="tokyo-runtime-deploy.lock",
            expected_uid=0,
        )
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


def _acquire_lock_beneath_root(
    *,
    root: Path,
    directory_components: tuple[str, ...],
    lock_name: str,
    expected_uid: int,
):
    """Open the canonical lock using only no-follow dirfd-relative operations."""

    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | os.O_CLOEXEC
    )
    current_fd = os.open(root, directory_flags)
    owned_fds = [current_fd]
    try:
        _validate_directory_fd(current_fd, expected_uid=expected_uid, exact_0700=False)
        for component in directory_components:
            if not component or "/" in component or component in {".", ".."}:
                raise ValueError("deploy_lock_component_invalid")
            created = False
            try:
                os.mkdir(component, 0o700, dir_fd=current_fd)
                created = True
            except FileExistsError:
                pass
            child_fd = os.open(component, directory_flags, dir_fd=current_fd)
            owned_fds.append(child_fd)
            _validate_directory_fd(child_fd, expected_uid=expected_uid, exact_0700=True)
            if created:
                os.fsync(current_fd)
            current_fd = child_fd
        create_flags = (
            os.O_RDWR | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC
        )
        created_lock = False
        try:
            lock_fd = os.open(lock_name, create_flags, 0o600, dir_fd=current_fd)
            created_lock = True
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
            lock_fd = os.open(
                lock_name,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC,
                dir_fd=current_fd,
            )
        if created_lock:
            os.fsync(lock_fd)
            os.fsync(current_fd)
        fd_info = os.fstat(lock_fd)
        path_info = os.stat(lock_name, dir_fd=current_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(fd_info.st_mode)
            or fd_info.st_uid != expected_uid
            or stat.S_IMODE(fd_info.st_mode) != 0o600
            or fd_info.st_nlink != 1
            or (fd_info.st_dev, fd_info.st_ino) != (path_info.st_dev, path_info.st_ino)
        ):
            os.close(lock_fd)
            raise ValueError("deploy_lock_identity_invalid")
        handle = os.fdopen(lock_fd, "r+b", closefd=True)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        return handle
    finally:
        for fd in reversed(owned_fds):
            os.close(fd)


def _validate_directory_fd(
    fd: int,
    *,
    expected_uid: int,
    exact_0700: bool,
) -> None:
    info = os.fstat(fd)
    mode = stat.S_IMODE(info.st_mode)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != expected_uid
        or info.st_nlink < 1
        or (mode != 0o700 if exact_0700 else bool(mode & 0o022))
    ):
        raise ValueError("deploy_lock_parent_unsafe")


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


def install_and_verify_shared_readiness_helper(
    *,
    release_path: Path,
    previous_release_path: Path,
    env_path: Path,
    deploy_root: Path,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    release = Path(release_path).resolve(strict=True)
    previous = Path(previous_release_path).resolve(strict=True)
    source = release / "scripts/check_runtime_postgres_ready.py"
    if not source.is_file():
        raise ValueError("readiness_helper_source_missing")
    raw = source.read_bytes()
    destination = Path(deploy_root) / "control-plane/check_runtime_postgres_ready.py"
    _atomic_bytes_write(destination, raw, mode=0o755)
    environment = load_runtime_environment(Path(env_path))
    environment["PYTHONPATH"] = str(previous)
    result = _run_candidate_command(
        [
            str(previous / ".venv/bin/python"), str(destination),
            "--require-database-url", "--timeout-seconds", "10", "--json",
        ],
        release=previous,
        timeout=20,
        env=environment,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    payload = _json_receipt(result, "previous_readiness_probe_receipt_invalid")
    if payload.get("status") != "ready" or payload.get("select_one") != 1:
        raise RuntimeError("previous_readiness_probe_failed")
    return {
        "status": "shared_readiness_helper_verified",
        "readiness_helper_sha256": hashlib.sha256(raw).hexdigest(),
        "path": str(destination),
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
    run(["/usr/bin/systemctl", "stop", *DEPLOY_STOP_UNITS], timeout=180)
    states = run(
        ["/usr/bin/systemctl", "show", "--property=ActiveState", "--value", *DEPLOY_STOP_UNITS]
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
    role_preflight = run(["scripts/verify_canary_readonly_role_preflight.py"])
    role_payload = _json_receipt(role_preflight, "canary_role_preflight_receipt_invalid")
    if (
        role_payload.get("status") != "canary_readonly_role_preflight_passed"
        or role_payload.get("current_user") != "pg_read_all_data"
        or role_payload.get("exchange_write_called") is not False
    ):
        raise RuntimeError("canary_role_preflight_receipt_mismatch")
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
        rendered = source.read_bytes().replace(
            b"/home/ubuntu/brc-deploy/releases/__BRC_CANDIDATE_SHA__",
            str(release).encode("utf-8"),
        )
        if b"__BRC_CANDIDATE_SHA__" in rendered:
            raise ValueError("candidate_systemd_placeholder_unresolved")
        _atomic_bytes_write(destination, rendered, mode=0o644)
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


def refresh_candidate_account_facts(
    *,
    release_path: Path,
    env_path: Path,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    release = Path(release_path).resolve(strict=True)
    python = release / ".venv/bin/python"
    environment = load_runtime_environment(Path(env_path))
    environment["PYTHONPATH"] = str(release)
    result = _run_candidate_command(
        [
            str(python), "scripts/build_runtime_account_safe_facts.py",
            "--require-database-url", "--env-file", str(env_path),
            "--allow-blocked-current-projection",
        ],
        release=release,
        timeout=90,
        env=environment,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    try:
        payload = json.loads(result.stdout)
        ids = tuple(sorted(str(value) for value in payload["pg_fact_snapshot_ids"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("account_fact_refresh_receipt_invalid") from exc
    if (
        payload.get("status") not in {
            "runtime_account_safe_facts_ready",
            "runtime_account_safe_facts_blocked",
        }
        or not isinstance(payload.get("account_safe_facts_ready"), bool)
        or not ids
        or len(ids) > 128
        or len(ids) != len(set(ids))
    ):
        raise RuntimeError("account_fact_refresh_not_certifiable")
    return {
        "status": "candidate_account_facts_refreshed",
        "fact_snapshot_ids": ids,
        "account_safe_facts_ready": payload["account_safe_facts_ready"],
    }


def run_five_readonly_canaries(
    *,
    release_path: Path,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    release = Path(release_path).resolve(strict=True)

    def run(command: list[str], timeout: int = 180) -> ChildResult:
        return _run_candidate_command(
            command,
            release=release,
            timeout=timeout,
            env=None,
            runner=runner,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
        )

    api = "brc-owner-console-canary-readonly.service"
    watcher = "brc-runtime-signal-watcher-canary.service"
    run(["/usr/bin/systemctl", "start", api], timeout=60)
    run(["/usr/bin/systemctl", "is-active", api], timeout=30)
    successful = 0
    try:
        for _ in range(5):
            run(["/usr/bin/systemctl", "start", watcher], timeout=180)
            result = run(
                ["/usr/bin/systemctl", "show", watcher, "--property=Result", "--value"],
                timeout=30,
            )
            if result.stdout.strip() != "success":
                raise RuntimeError("readonly_canary_unit_result_invalid")
            successful += 1
    finally:
        run(["/usr/bin/systemctl", "stop", watcher], timeout=30)
        run(["/usr/bin/systemctl", "stop", api], timeout=30)
    return {"status": "readonly_canary_complete", "successful_ticks": successful}


def record_candidate_release_activation(
    *,
    release_path: Path,
    env_path: Path,
    target_sha: str,
    release_name: str,
    transaction_id: str,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    result = _run_release_python_script(
        release_path=release_path,
        env_path=env_path,
        arguments=[
            "scripts/record_runtime_release_activation.py",
            "--runtime-head", _sha(target_sha, "target_sha"),
            "--release-name", _required(release_name, "release_name"),
            "--verification-ref", f"deploy:{_required(transaction_id, 'transaction_id')}",
        ],
        timeout=60,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    payload = _json_receipt(result, "release_activation_receipt_invalid")
    if (
        payload.get("status") != "runtime_release_activation_completed"
        or payload.get("runtime_head") != target_sha
        or payload.get("exchange_write_called") is not False
    ):
        raise RuntimeError("release_activation_receipt_mismatch")
    return payload


def certify_candidate_action_time(
    *,
    release_path: Path,
    env_path: Path,
    target_sha: str,
    stage: str,
    deploy_nonce: str,
    fact_snapshot_ids: tuple[str, ...],
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    if stage not in {"pre_canary", "post_canary"}:
        raise ValueError("action_time_certification_stage_invalid")
    ids = tuple(sorted(set(str(value) for value in fact_snapshot_ids)))
    if not ids or ids != fact_snapshot_ids or len(ids) > 128:
        raise ValueError("action_time_certification_fact_ids_invalid")
    arguments = [
        "scripts/certify_action_time_capability.py",
        "--runtime-head", _sha(target_sha, "target_sha"),
        "--stage", stage,
        "--deploy-nonce", _required(deploy_nonce, "deploy_nonce"),
        "--expected-lane-count", "22",
    ]
    for fact_id in ids:
        arguments.extend(["--fact-snapshot-id", fact_id])
    result = _run_release_python_script(
        release_path=release_path,
        env_path=env_path,
        arguments=arguments,
        timeout=120,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    payload = _json_receipt(result, "action_time_certification_receipt_invalid")
    if (
        payload.get("status") != "action_time_capability_certified"
        or payload.get("certified_lane_count") != 22
        or payload.get("exchange_write_called") is not False
        or not str(payload.get("certification_ref") or "").startswith("action-time-cert:v2:")
        or not isinstance(payload.get("certification_reference"), dict)
    ):
        raise RuntimeError("action_time_certification_receipt_mismatch")
    return payload


def publish_candidate_current_projections(
    *,
    release_path: Path,
    env_path: Path,
    target_sha: str,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    result = _run_release_python_script(
        release_path=release_path,
        env_path=env_path,
        arguments=[
            "scripts/publish_runtime_control_current_projections.py",
            "--require-database-url", "--target-runtime-head",
            _sha(target_sha, "target_sha"), "--json",
        ],
        timeout=120,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    payload = _json_receipt(result, "projection_publish_receipt_invalid")
    if (
        payload.get("status") != "current_projections_published"
        or payload.get("runtime_head") != target_sha
        or (payload.get("safety_invariants") or {}).get("calls_exchange_write") is not False
    ):
        raise RuntimeError("projection_publish_receipt_mismatch")
    return payload


def read_candidate_schema_revision(
    *,
    release_path: Path,
    env_path: Path,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> str:
    result = _run_release_python_script(
        release_path=release_path,
        env_path=env_path,
        arguments=["-m", "alembic", "current"],
        timeout=60,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    tokens = result.stdout.replace("(", " ").split()
    revisions = [token for token in tokens if token.isdigit()]
    if len(revisions) != 1:
        raise RuntimeError("schema_revision_read_invalid")
    return revisions[0]


def verify_candidate_phase_two_ready(
    *,
    release_path: Path,
    env_path: Path,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    result = _run_release_python_script(
        release_path=release_path,
        env_path=env_path,
        arguments=[
            "scripts/verify_ticket_lifecycle_phase_two_readiness.py",
            "--require-database-url", "--json",
        ],
        timeout=60,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    payload = _json_receipt(result, "phase_two_readiness_receipt_invalid")
    if (
        payload.get("status") != "phase_two_ready"
        or payload.get("exchange_write_called") is not False
    ):
        raise RuntimeError("phase_two_readiness_receipt_mismatch")
    return payload


def capture_candidate_mutation_sentinel(
    *,
    release_path: Path,
    env_path: Path,
    target_sha: str,
    scope: Mapping[str, Any] | None = None,
    canary_window_floor_ms: int | None = None,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    arguments = [
        "scripts/capture_canary_mutation_sentinel.py",
        "--target-runtime-head", _sha(target_sha, "target_sha"),
    ]
    if scope is not None:
        arguments.extend([
            "--scope-json",
            json.dumps(dict(scope), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ])
    if canary_window_floor_ms is not None:
        arguments.extend(["--canary-window-floor-ms", str(int(canary_window_floor_ms))])
    result = _run_release_python_script(
        release_path=release_path,
        env_path=env_path,
        arguments=arguments,
        timeout=60,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    payload = _json_receipt(result, "canary_sentinel_receipt_invalid")
    if (
        payload.get("status") != "canary_mutation_sentinel_captured"
        or not str(payload.get("digest") or "").startswith("sha256:")
        or not isinstance(payload.get("scope"), dict)
    ):
        raise RuntimeError("canary_sentinel_receipt_mismatch")
    return payload


def restore_lifecycle_mutation_policy(
    *,
    release_path: Path,
    env_path: Path,
    target_sha: str,
    was_enabled: bool,
    post_certification_ref: str,
    post_certification_reference: Mapping[str, Any],
    post_projection_slice_digests: Mapping[str, str],
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    target_sha = _sha(target_sha, "target_sha")
    if was_enabled:
        lane_payload = {
            "schema": "brc.lane_identity_digest.v1",
            "lane_source_watermarks": list(
                post_certification_reference.get("lane_source_watermarks") or []
            ),
        }
        projection_payload = {
            "schema": "brc.certification_projection_digest.v1",
            "slice_digests": {
                key: post_projection_slice_digests[key]
                for key in sorted(post_projection_slice_digests)
            },
        }
        proof = {
            "schema": "brc.lifecycle_mutation_enablement_proof.v2",
            "target_runtime_head": target_sha,
            "lane_identity_digest": _digest(lane_payload),
            "action_time_certification_ref": _required(
                post_certification_ref, "post_certification_ref"
            ),
            "action_time_certification_payload": dict(post_certification_reference),
            "certification_projection_digest_schema": (
                "brc.certification_projection_digest.v1"
            ),
            "certification_projection_digest": _digest(projection_payload),
        }
        proof_ref = "lifecycle-cert:v2:" + hashlib.sha256(
            _canonical_bytes(proof)
        ).hexdigest()
        arguments = [
            "scripts/set_ticket_lifecycle_mutation_capability.py",
            "--enable", "--require-database-url",
            "--certification-ref", proof_ref,
            "--proof-json", json.dumps(
                proof, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            "--json",
        ]
    else:
        proof = None
        proof_ref = f"deploy-policy-disabled:{target_sha}"
        arguments = [
            "scripts/set_ticket_lifecycle_mutation_capability.py",
            "--disable", "--require-database-url",
            "--certification-ref", proof_ref, "--json",
        ]
    result = _run_release_python_script(
        release_path=release_path,
        env_path=env_path,
        arguments=arguments,
        timeout=60,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    payload = _json_receipt(result, "lifecycle_policy_restore_receipt_invalid")
    if (
        payload.get("status") != ("ready" if was_enabled else "not_ready")
        or payload.get("enabled") is not was_enabled
        or (was_enabled and payload.get("blockers") != [])
    ):
        raise RuntimeError("lifecycle_policy_restore_receipt_mismatch")
    return {
        "status": "lifecycle_policy_restored",
        "enabled": was_enabled,
        "lifecycle_proof_ref": proof_ref if was_enabled else None,
        "proof": proof,
    }


def capture_production_unit_prepolicy(
    *,
    release_path: Path,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, dict[str, Any]]:
    release = Path(release_path).resolve(strict=True)
    policy: dict[str, dict[str, Any]] = {}
    for unit in PRODUCTION_WRITER_UNITS:
        result = _run_candidate_command(
            [
                "/usr/bin/systemctl", "show", unit,
                "--property=ActiveState", "--property=UnitFileState",
            ],
            release=release,
            timeout=30,
            env=None,
            runner=runner,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
        )
        facts = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                facts[key] = value
        if facts.get("ActiveState") not in {"active", "inactive", "failed", "activating", "deactivating"}:
            raise RuntimeError("unit_prepolicy_active_state_invalid:" + unit)
        policy[unit] = {
            "active": facts["ActiveState"] == "active",
            "active_state": facts["ActiveState"],
            "unit_file_state": facts.get("UnitFileState", ""),
        }
    return policy


def apply_committed_activation(
    *,
    release_path: Path,
    env_path: Path,
    activation_commit: Mapping[str, Any],
    unit_prepolicy: Mapping[str, Mapping[str, Any]],
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
    fence_marker: Path = Path(
        "/home/ubuntu/brc-deploy/control-plane/production-writers.blocked"
    ),
) -> dict[str, Any]:
    release = Path(release_path).resolve(strict=True)
    python = release / ".venv/bin/python"
    environment = load_runtime_environment(Path(env_path))
    environment["PYTHONPATH"] = str(release)
    if Path(fence_marker).exists() or runner is not None:
        removal = _run_candidate_command(
            [
                str(python), "scripts/set_production_writer_fence.py", "--remove",
                "--activation-commit-json",
                json.dumps(dict(activation_commit), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ],
            release=release,
            timeout=30,
            env=environment,
            runner=runner,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
        )
        if _json_receipt(removal, "fence_removal_receipt_invalid").get("status") != "fence_removed":
            raise RuntimeError("fence_removal_receipt_mismatch")
    elif (
        activation_commit.get("schema") != "brc.runtime_activation_commit.v1"
        or activation_commit.get("status") != "runtime_activation_committed"
    ):
        raise RuntimeError("activation_commit_invalid_after_fence_removal")
    for canary in (
        "brc-runtime-signal-watcher-canary.service",
        "brc-owner-console-canary-readonly.service",
    ):
        _run_candidate_command(
            ["/usr/bin/systemctl", "stop", canary],
            release=release,
            timeout=30,
            env=None,
            runner=runner,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
        )
    restore_order = [
        unit for unit in PRODUCTION_WRITER_UNITS
        if unit != "brc-runtime-signal-watcher.timer"
    ] + ["brc-runtime-signal-watcher.timer"]
    restored: list[str] = []
    for unit in restore_order:
        if not bool((unit_prepolicy.get(unit) or {}).get("active")):
            continue
        _run_candidate_command(
            ["/usr/bin/systemctl", "start", unit],
            release=release,
            timeout=90,
            env=None,
            runner=runner,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
        )
        active = _run_candidate_command(
            ["/usr/bin/systemctl", "is-active", unit],
            release=release,
            timeout=30,
            env=None,
            runner=runner,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
        )
        if active.stdout.strip() != "active":
            raise RuntimeError("restored_unit_not_active:" + unit)
        restored.append(unit)
    return {"status": "activation_applied", "restored_units": restored}


def collect_activation_machine_facts(
    *,
    release_path: Path,
    env_path: Path,
    target_sha: str,
    expected_revision: str,
    bootstrap_sha256: str,
    deploy_root: Path,
    runner: Callable[..., ChildResult] | None = None,
    lock_handle: Any | None = None,
    canonical_lock_path: Path = CANONICAL_LOCK_PATH,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    release = Path(release_path).resolve(strict=True)
    target_sha = _sha(target_sha, "target_sha")
    readiness = _run_release_python_script(
        release_path=release,
        env_path=env_path,
        arguments=[
            "scripts/check_runtime_postgres_ready.py", "--require-database-url",
            "--timeout-seconds", "10", "--json",
        ],
        timeout=20,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    readiness_payload = _json_receipt(readiness, "activation_postgres_readiness_invalid")
    if readiness_payload.get("status") != "ready" or readiness_payload.get("select_one") != 1:
        raise RuntimeError("activation_postgres_not_ready")
    revision = read_candidate_schema_revision(
        release_path=release,
        env_path=env_path,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    if revision != str(expected_revision):
        raise RuntimeError("activation_schema_revision_mismatch")
    environment = load_runtime_environment(Path(env_path))
    environment["PYTHONPATH"] = str(release)

    def run(command: list[str], timeout: int = 30) -> ChildResult:
        return _run_candidate_command(
            command,
            release=release,
            timeout=timeout,
            env=environment,
            runner=runner,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
        )

    versions = run([
        str(release / ".venv/bin/python"), "-c",
        "import json,ccxt,platform,sys;print(json.dumps({"
        "'ccxt':ccxt.__version__,'python':platform.python_implementation(),"
        "'cache_tag':sys.implementation.cache_tag,'platform':sys.platform,"
        "'machine':platform.machine()}))",
    ])
    version_payload = _json_receipt(versions, "activation_dependency_versions_invalid")
    if version_payload != {
        "ccxt": "4.5.56",
        "python": "CPython",
        "cache_tag": "cpython-310",
        "platform": "linux",
        "machine": "x86_64",
    }:
        raise RuntimeError("activation_dependency_versions_mismatch")
    app_current = Path(deploy_root) / "app/current"
    if app_current.resolve(strict=True) != release:
        raise RuntimeError("activation_release_pointer_mismatch")
    manifest = json.loads((release / ".brc-release-manifest.json").read_text("utf-8"))
    if manifest.get("target_commit") != target_sha:
        raise RuntimeError("activation_release_manifest_head_mismatch")
    restart_policy = run([
        "/usr/bin/docker", "inspect", "--format={{.HostConfig.RestartPolicy.Name}}",
        "dingdingbot-pg",
    ]).stdout.strip()
    if restart_policy != "unless-stopped":
        raise RuntimeError("postgres_restart_policy_invalid")
    watcher = run([
        "/usr/bin/systemctl", "show", "brc-runtime-signal-watcher.service",
        "--property=MemoryHigh", "--property=MemoryMax", "--property=TimeoutStartUSec",
    ]).stdout
    watcher_facts = dict(
        line.split("=", 1) for line in watcher.splitlines() if "=" in line
    )
    if (
        watcher_facts.get("MemoryHigh") != "402653184"
        or watcher_facts.get("MemoryMax") != "536870912"
        or watcher_facts.get("TimeoutStartUSec") not in {"5min", "300000000"}
    ):
        raise RuntimeError("watcher_resource_facts_mismatch")
    backend_exec = run([
        "/usr/bin/systemctl", "show", "brc-owner-console-backend.service",
        "--property=ExecStart", "--value",
    ]).stdout.strip()
    if "/home/ubuntu/brc-deploy/app/current/.venv/bin/python" not in backend_exec:
        raise RuntimeError("backend_execstart_not_current_venv")
    audit = _run_release_python_script(
        release_path=release,
        env_path=env_path,
        arguments=["scripts/audit_production_runtime_file_io.py", "--json"],
        timeout=120,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )
    audit_payload = _json_receipt(audit, "activation_file_io_audit_invalid")
    if (audit_payload.get("performance_risk") or {}).get("status") != "clear":
        raise RuntimeError("activation_performance_risk_not_clear")
    state_machine_sha = hashlib.sha256(
        (release / "scripts/tokyo_runtime_deploy_remote_state_machine.py").read_bytes()
    ).hexdigest()
    if state_machine_sha != bootstrap_sha256:
        raise RuntimeError("activation_state_machine_sha_mismatch")
    helper_sha = hashlib.sha256(
        (release / "scripts/check_runtime_postgres_ready.py").read_bytes()
    ).hexdigest()
    installed_helper = Path(deploy_root) / "control-plane/check_runtime_postgres_ready.py"
    if not installed_helper.is_file():
        raise RuntimeError("installed_readiness_helper_missing")
    installed_helper_sha = hashlib.sha256(installed_helper.read_bytes()).hexdigest()
    if installed_helper_sha != helper_sha:
        raise RuntimeError("installed_readiness_helper_sha_mismatch")
    return {
        "status": "activation_machine_facts_verified",
        "postgres_ready": "ready",
        "alembic_current": revision,
        "dependency_lock_sha256": hashlib.sha256(
            (release / "requirements-runtime.lock").read_bytes()
        ).hexdigest(),
        "python_abi_platform": (
            f"{version_payload['cache_tag']}-{version_payload['platform']}-"
            f"{version_payload['machine']}"
        ),
        "ccxt_version": version_payload["ccxt"],
        "readiness_helper_sha256": helper_sha,
        "installed_readiness_helper_sha256": installed_helper_sha,
        "remote_state_machine_sha256": state_machine_sha,
        "remote_state_machine_launcher": (
            "/usr/bin/systemd-run:transient_service:/usr/bin/python3:stdlib_hash_loader"
        ),
        "remote_state_machine_runtime_max_sec": 3600,
        "remote_state_machine_kill_mode": "control-group",
        "repository_command_python": str(release / ".venv/bin/python"),
        "postgres_container_restart_policy": restart_policy,
        "watcher_memory_high": watcher_facts["MemoryHigh"],
        "watcher_memory_max": watcher_facts["MemoryMax"],
        "watcher_timeout_start_usec": watcher_facts["TimeoutStartUSec"],
        "backend_exec_start": backend_exec,
        "performance_risk": audit_payload["performance_risk"],
    }


def _run_release_python_script(
    *,
    release_path: Path,
    env_path: Path,
    arguments: list[str],
    timeout: int,
    runner: Callable[..., ChildResult] | None,
    lock_handle: Any | None,
    canonical_lock_path: Path,
    require_root_owner: bool,
) -> ChildResult:
    release = Path(release_path).resolve(strict=True)
    environment = load_runtime_environment(Path(env_path))
    environment["PYTHONPATH"] = str(release)
    return _run_candidate_command(
        [str(release / ".venv/bin/python"), *arguments],
        release=release,
        timeout=timeout,
        env=environment,
        runner=runner,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock_path,
        require_root_owner=require_root_owner,
    )


def _json_receipt(result: ChildResult, error: str) -> dict[str, Any]:
    try:
        payload = json.loads(result.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(error) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(error)
    return payload


def execute_deploy_transaction(
    *,
    config: Mapping[str, Any],
    lock_handle: Any,
    journal_path: Path,
) -> dict[str, Any]:
    """Execute or resume the one journaled deployment transaction."""

    transaction_id = _required(str(config.get("transaction_id") or ""), "transaction_id")
    deploy_nonce = _required(str(config.get("deploy_nonce") or ""), "deploy_nonce")
    old_sha = _sha(str(config.get("old_sha") or ""), "old_sha")
    target_sha = _sha(str(config.get("target_sha") or ""), "target_sha")
    deploy_root = Path(str(config.get("deploy_root") or "/home/ubuntu/brc-deploy"))
    release_name = _required(str(config.get("release_name") or ""), "release_name")
    release = deploy_root / "releases" / release_name
    app_current = deploy_root / "app/current"
    env_path = Path(str(config.get("env_path") or deploy_root / "env/live-readonly.env"))
    previous_release = Path(_required(
        str(config.get("previous_release_path") or ""), "previous_release_path"
    ))
    legacy_venv = Path(str(
        config.get("legacy_venv_path")
        or deploy_root / "venvs/brc-bnb-prelive-20260601"
    ))
    expected_revision = _required(
        str(config.get("expected_revision") or "124"), "expected_revision"
    )
    bootstrap_sha256 = _required(
        str(config.get("bootstrap_sha256") or ""), "bootstrap_sha256"
    )
    if len(bootstrap_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in bootstrap_sha256
    ):
        raise ValueError("bootstrap_sha256_invalid")
    canonical_lock = Path(str(config.get("canonical_lock_path") or CANONICAL_LOCK_PATH))
    require_root = bool(config.get("require_root_owner", True))
    journal_path = Path(journal_path)
    if journal_path.exists():
        journal = DeployJournal.load(journal_path)
        if (
            journal.transaction_id != transaction_id
            or journal.deploy_nonce != deploy_nonce
            or journal.old_sha != old_sha
            or journal.target_sha != target_sha
        ):
            raise ValueError("deploy_journal_lineage_mismatch")
    else:
        journal = DeployJournal(
            journal_path,
            transaction_id=transaction_id,
            deploy_nonce=deploy_nonce,
            old_sha=old_sha,
            target_sha=target_sha,
        )

    def phase(name: str, action: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
        index = DEPLOY_PHASES.index(name)
        if len(journal.entries) > index:
            result = journal.entries[index]["facts"].get("result")
            if not isinstance(result, dict):
                raise ValueError("deploy_journal_phase_result_invalid")
            return dict(result)
        if len(journal.entries) != index:
            raise ValueError("deploy_journal_resume_phase_invalid")
        result = dict(action())
        journal.append(name, {"result": result})
        return result

    lock_info = os.fstat(lock_handle.fileno())
    phase("bootstrap_locked", lambda: {
        "status": "bootstrap_locked",
        "host": platform.node(),
        "lock_device": lock_info.st_dev,
        "lock_inode": lock_info.st_ino,
    })
    phase("candidate_staged", lambda: stage_candidate_release(
        deploy_root=deploy_root,
        repo_url=str(config["repo_url"]),
        git_ref=str(config["git_ref"]),
        target_sha=target_sha,
        release_name=release_name,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    phase("immutable_venv_ready", lambda: build_immutable_venv(
        release_path=release,
        lock_path=release / "requirements-runtime.lock",
        venv_root=deploy_root / "venvs/immutable",
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    def previous_compatibility_action() -> Mapping[str, Any]:
        compatibility = ensure_previous_release_venv_compatibility(
            previous_release_path=previous_release,
            deployed_venv_path=legacy_venv,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )
        readiness = install_and_verify_shared_readiness_helper(
            release_path=release,
            previous_release_path=previous_release,
            env_path=env_path,
            deploy_root=deploy_root,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )
        return {**compatibility, **readiness}

    phase("previous_release_venv_compatible", previous_compatibility_action)

    def fence_action() -> Mapping[str, Any]:
        prepolicy = capture_production_unit_prepolicy(
            release_path=release,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )
        fence = engage_production_writer_fence(
            release_path=release,
            transaction_id=transaction_id,
            deploy_nonce=deploy_nonce,
            target_sha=target_sha,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )
        return {"status": "production_writers_fenced", "fence": fence, "unit_prepolicy": prepolicy}

    fenced = phase("production_writers_fenced", fence_action)
    phase("pre_migration", lambda: {
        "status": "pre_migration",
        "actual_revision": read_candidate_schema_revision(
            release_path=release,
            env_path=env_path,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        ),
    })
    phase("migration_in_progress", lambda: {
        "status": "migration_in_progress",
        "old_code_rollback_allowed": False,
    })
    migrated = phase("schema_migrated", lambda: run_fenced_schema_migration(
        release_path=release,
        env_path=env_path,
        transaction_id=transaction_id,
        expected_revision=expected_revision,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    phase("pointer_active", lambda: install_candidate_units_and_switch_pointer(
        release_path=release,
        app_current=app_current,
        target_sha=target_sha,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    phase("release_activation_recorded", lambda: record_candidate_release_activation(
        release_path=release,
        env_path=env_path,
        target_sha=target_sha,
        release_name=release_name,
        transaction_id=transaction_id,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    pre_facts = phase("pre_canary_facts", lambda: refresh_candidate_account_facts(
        release_path=release,
        env_path=env_path,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    pre_cert = phase("pre_canary_certified", lambda: certify_candidate_action_time(
        release_path=release,
        env_path=env_path,
        target_sha=target_sha,
        stage="pre_canary",
        deploy_nonce=deploy_nonce,
        fact_snapshot_ids=tuple(pre_facts["fact_snapshot_ids"]),
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    phase("pre_canary_projection", lambda: publish_candidate_current_projections(
        release_path=release,
        env_path=env_path,
        target_sha=target_sha,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    pre_sentinel = phase("pre_canary_sentinel", lambda: capture_candidate_mutation_sentinel(
        release_path=release,
        env_path=env_path,
        target_sha=target_sha,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    phase("readonly_canary_complete", lambda: run_five_readonly_canaries(
        release_path=release,
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))

    def post_sentinel_action() -> Mapping[str, Any]:
        post = capture_candidate_mutation_sentinel(
            release_path=release,
            env_path=env_path,
            target_sha=target_sha,
            scope=pre_sentinel["scope"],
            canary_window_floor_ms=int(pre_sentinel["canary_window_floor_ms"]),
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )
        if (
            post.get("digest") != pre_sentinel.get("digest")
            or post.get("slice_digests") != pre_sentinel.get("slice_digests")
            or post.get("slice_counts") != pre_sentinel.get("slice_counts")
        ):
            raise RuntimeError("readonly_canary_mutation_sentinel_changed")
        return post

    phase("post_canary_sentinel", post_sentinel_action)

    def post_fact_action() -> Mapping[str, Any]:
        refreshed = refresh_candidate_account_facts(
            release_path=release,
            env_path=env_path,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )
        readiness = verify_candidate_phase_two_ready(
            release_path=release,
            env_path=env_path,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )
        return {**refreshed, "phase_two_readiness": readiness}

    post_facts = phase("post_canary_facts", post_fact_action)
    post_cert = phase("post_canary_certified", lambda: certify_candidate_action_time(
        release_path=release,
        env_path=env_path,
        target_sha=target_sha,
        stage="post_canary",
        deploy_nonce=deploy_nonce,
        fact_snapshot_ids=tuple(post_facts["fact_snapshot_ids"]),
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))

    def post_projection_action() -> Mapping[str, Any]:
        published = publish_candidate_current_projections(
            release_path=release,
            env_path=env_path,
            target_sha=target_sha,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )
        sentinel = capture_candidate_mutation_sentinel(
            release_path=release,
            env_path=env_path,
            target_sha=target_sha,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )
        return {**published, "sentinel": sentinel}

    post_projection = phase("post_canary_projection", post_projection_action)
    machine_facts = phase(
        "activation_machine_facts_verified",
        lambda: collect_activation_machine_facts(
            release_path=release,
            env_path=env_path,
            target_sha=target_sha,
            expected_revision=expected_revision,
            bootstrap_sha256=bootstrap_sha256,
            deploy_root=deploy_root,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        ),
    )
    reference = dict(post_cert["certification_reference"])

    def lifecycle_action() -> Mapping[str, Any]:
        now_ms = int(time.time() * 1000)
        if int(reference.get("fact_min_valid_until_ms") or 0) - now_ms < 30_000:
            raise RuntimeError("final_fact_freshness_remaining_insufficient")
        return restore_lifecycle_mutation_policy(
            release_path=release,
            env_path=env_path,
            target_sha=target_sha,
            was_enabled=bool(migrated["lifecycle_capability_was_enabled"]),
            post_certification_ref=str(post_cert["certification_ref"]),
            post_certification_reference=reference,
            post_projection_slice_digests=post_projection["sentinel"]["slice_digests"],
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock,
            require_root_owner=require_root,
        )

    lifecycle = phase("lifecycle_proof_persisted", lifecycle_action)
    fence_info = dict(fenced["fence"])
    activation_commit = phase("runtime_activation_committed", lambda: {
        "schema": "brc.runtime_activation_commit.v1",
        "status": "runtime_activation_committed",
        "deploy_transaction_id": transaction_id,
        "deploy_nonce": deploy_nonce,
        "target_runtime_head": target_sha,
        "fence_inode": int(fence_info["fence_inode"]),
        "lifecycle_policy_enabled": bool(lifecycle["enabled"]),
        "lifecycle_proof_ref": lifecycle.get("lifecycle_proof_ref"),
        "release_pointer": str(app_current),
        "schema_revision": expected_revision,
        "dependency_identity": dependency_identity(release / "requirements-runtime.lock"),
        "pre_canary_sentinel_digest": pre_sentinel["digest"],
        "post_projection_sentinel_digest": post_projection["sentinel"]["digest"],
        "action_time_certification_ref": post_cert["certification_ref"],
        "activation_machine_facts": machine_facts,
        "zero_deployment_exchange_side_effect": True,
    })
    phase("policy_applied", lambda: apply_committed_activation(
        release_path=release,
        env_path=env_path,
        activation_commit=activation_commit,
        unit_prepolicy=fenced["unit_prepolicy"],
        lock_handle=lock_handle,
        canonical_lock_path=canonical_lock,
        require_root_owner=require_root,
    ))
    terminal = phase("terminal_manifest_consumed", lambda: {
        "status": "deploy_transaction_terminal",
        "target_runtime_head": target_sha,
        "journal_digest": journal.entries[-1]["entry_digest"],
    })
    return {
        "status": "tokyo_runtime_deploy_applied",
        "transaction_id": transaction_id,
        "target_runtime_head": target_sha,
        "terminal": terminal,
    }


def _run_candidate_command(
    command: list[str],
    *,
    release: Path,
    timeout: int,
    env: Mapping[str, str] | None,
    runner: Callable[..., ChildResult] | None,
    lock_handle: Any | None,
    canonical_lock_path: Path,
    require_root_owner: bool,
) -> ChildResult:
    if runner is not None:
        result = runner(command, cwd=release, timeout=timeout, env=env)
    elif lock_handle is not None:
        result = spawn_locked_mutation_child(
            command,
            lock_handle=lock_handle,
            canonical_lock_path=canonical_lock_path,
            require_root_owner=require_root_owner,
            cwd=release,
            timeout=timeout,
            env=env,
        )
    else:
        raise ValueError("candidate_command_lock_required")
    if result.returncode != 0:
        raise RuntimeError("candidate_command_failed:" + Path(command[0]).name)
    return result


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
        expected_index = len(self.entries)
        if expected_index >= len(DEPLOY_PHASES) or phase != DEPLOY_PHASES[expected_index]:
            raise ValueError("deploy_journal_phase_transition_invalid")
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
                or entry.get("phase") != DEPLOY_PHASES[index - 1]
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
    _atomic_bytes_write(path, raw, mode=0o600)


def _atomic_bytes_write(path: Path, raw: bytes, *, mode: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
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
    parser.add_argument("--legacy-venv-path")
    parser.add_argument("--expected-revision", default="124")
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
        if not args.deploy_root:
            print(json.dumps({"status": "lock_acquired", "transaction_id": args.transaction_id}))
            return 0
        journal_path = (
            CANONICAL_LOCK_PATH.parent
            / f"tokyo-runtime-deploy-{args.transaction_id}.json"
        )
        try:
            result = execute_deploy_transaction(
                config={
                    "transaction_id": args.transaction_id,
                    "deploy_nonce": args.deploy_nonce,
                    "old_sha": args.old_sha,
                    "target_sha": args.target_sha,
                    "deploy_root": args.deploy_root,
                    "repo_url": args.repo_url,
                    "git_ref": args.git_ref,
                    "release_name": args.release_name,
                    "previous_release_path": args.previous_release_path,
                    "legacy_venv_path": args.legacy_venv_path,
                    "service_name": args.service_name,
                    "env_path": args.env_path,
                    "expected_revision": args.expected_revision,
                    "bootstrap_sha256": args.bootstrap_sha256,
                },
                lock_handle=lock,
                journal_path=journal_path,
            )
        except Exception as exc:
            marker = Path(
                "/home/ubuntu/brc-deploy/control-plane/production-writers.blocked"
            )
            print(
                json.dumps(
                    {
                        "status": (
                            "failed_contained" if marker.exists()
                            else "pre_maintenance_abort"
                        ),
                        "transaction_id": args.transaction_id,
                        "error_code": str(exc).split(":", 1)[0],
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(result, sort_keys=True))
        return 0
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
