#!/usr/bin/env python3
"""Stdlib-only, crash-safe Tokyo runtime deployment state machine."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping
import uuid


STDLIB_IMPORT_ALLOWLIST = frozenset(
    {
        "__future__", "argparse", "fcntl", "hashlib", "json", "os",
        "pathlib", "platform", "stat", "sys", "tempfile", "time", "typing",
        "uuid", "shutil", "subprocess",
    }
)
CANONICAL_LOCK_PATH = Path(
    "/var/lib/brc-deploy/deploy-state/tokyo-runtime-deploy.lock"
)
MAX_JOURNAL_ENTRIES = 48


class ChildResult:
    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = int(returncode)
        self.stdout = str(stdout)
        self.stderr = str(stderr)


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


def build_immutable_venv(
    *,
    release_path: Path,
    lock_path: Path,
    venv_root: Path,
    base_python: str = "/usr/bin/python3",
    runner: Callable[..., ChildResult] | None = None,
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
    command_runner = runner or _run_child
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-sha256", required=True)
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--deploy-nonce", required=True)
    parser.add_argument("--old-sha", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--source-path", required=True)
    args = parser.parse_args(argv)
    source = Path(args.source_path).read_bytes()
    validate_bootstrap_environment(
        source=source,
        expected_sha256=args.bootstrap_sha256,
    )
    lock = acquire_deploy_lock()
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
