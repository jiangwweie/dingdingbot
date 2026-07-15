from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from scripts import tokyo_runtime_deploy_remote_state_machine as machine


def test_remote_state_machine_source_is_stdlib_only():
    source_path = Path(machine.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            roots.add(str(node.module or "").split(".", 1)[0])
    assert roots <= machine.STDLIB_IMPORT_ALLOWLIST


def test_bootstrap_identity_is_checked_before_state_initializer():
    source = b"print('candidate')\n"
    calls: list[str] = []
    with pytest.raises(ValueError, match="bootstrap_sha256_mismatch"):
        machine.validate_bootstrap_environment(
            source=source,
            expected_sha256="0" * 64,
            version_info=(3, 10, 14),
            euid=0,
            state_initializer=lambda: calls.append("mutated"),
        )
    assert calls == []


def test_deploy_lock_is_nonblocking_and_never_replaced(tmp_path):
    lock_path = tmp_path / "deploy-state" / "tokyo-runtime-deploy.lock"
    first = machine.acquire_deploy_lock(lock_path, require_root_owner=False)
    inode = lock_path.stat().st_ino
    second = machine.acquire_deploy_lock(lock_path, require_root_owner=False)
    try:
        assert first is not None
        assert second is None
        assert lock_path.stat().st_ino == inode
        assert lock_path.stat().st_mode & 0o777 == 0o600
    finally:
        if first is not None:
            first.close()


def test_journal_is_hash_chained_and_reloaded(tmp_path):
    journal = machine.DeployJournal(
        tmp_path / "journal.json",
        transaction_id="a1",
        deploy_nonce="nonce-1",
        old_sha="b" * 40,
        target_sha="a" * 40,
    )
    journal.append("pre_migration", {"revision": "120"})
    journal.append("migration_in_progress", {"revision": "120"})

    reloaded = machine.DeployJournal.load(tmp_path / "journal.json")

    assert [entry["phase"] for entry in reloaded.entries] == [
        "pre_migration",
        "migration_in_progress",
    ]
    assert reloaded.entries[1]["previous_digest"] == reloaded.entries[0]["entry_digest"]


def test_dependency_identity_binds_lock_and_abi(tmp_path):
    lock = tmp_path / "requirements-runtime.lock"
    lock.write_text("ccxt==4.5.56 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    expected = hashlib.sha256(lock.read_bytes()).hexdigest() + "-cp310-linux_x86_64"
    assert machine.dependency_identity(lock) == expected


def test_incomplete_immutable_venv_is_rebuilt_with_hashed_lock(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    (release / "src").mkdir()
    lock = release / "requirements-runtime.lock"
    lock.write_text("ccxt==4.5.56 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    root = tmp_path / "venvs"
    target = root / machine.dependency_identity(lock)
    target.mkdir(parents=True)
    (target / "partial").write_text("stale", encoding="utf-8")
    commands: list[tuple[str, ...]] = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        if command[1:4] == ("-m", "venv", str(target)):
            (target / "bin").mkdir(parents=True, exist_ok=True)
            (target / "bin/python").write_text("", encoding="utf-8")
        return machine.ChildResult(returncode=0, stdout="", stderr="")

    result = machine.build_immutable_venv(
        release_path=release,
        lock_path=lock,
        venv_root=root,
        base_python="/usr/bin/python3",
        runner=runner,
    )

    assert result["status"] == "immutable_venv_ready"
    assert not (target / "partial").exists()
    assert (target / ".complete").is_file()
    assert (release / ".venv").resolve() == target.resolve()
    assert any("--require-hashes" in command for command in commands)
    assert all("requirements.txt" not in command for command in commands)
