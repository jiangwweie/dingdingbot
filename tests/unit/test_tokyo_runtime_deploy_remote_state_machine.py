from __future__ import annotations

import ast
import hashlib
import json
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
        if tuple(command[1:4]) == ("-m", "venv", str(target)):
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


def test_bootstrap_source_can_be_supplied_in_memory_without_remote_file(tmp_path, monkeypatch, capsys):
    source = b"print('tracked state machine')\n"
    lock_path = tmp_path / "deploy-state" / "tokyo-runtime-deploy.lock"
    monkeypatch.setattr(machine, "CANONICAL_LOCK_PATH", lock_path)
    monkeypatch.setattr(machine.platform, "python_implementation", lambda: "CPython")
    monkeypatch.setattr(machine.sys, "version_info", (3, 10, 14))

    result = machine.main(
        [
            "--bootstrap-sha256",
            hashlib.sha256(source).hexdigest(),
            "--transaction-id",
            "a1b2c3d4",
            "--deploy-nonce",
            "nonce-a1b2c3d4",
            "--old-sha",
            "b" * 40,
            "--target-sha",
            "a" * 40,
        ],
        bootstrap_source=source,
        bootstrap_euid=0,
        require_root_lock_owner=False,
    )

    assert result == 0
    assert '"status": "lock_acquired"' in capsys.readouterr().out
    assert lock_path.is_file()


def test_mutation_child_inherits_exact_lock_fd_and_rejects_escape_commands(
    tmp_path, monkeypatch
):
    lock_path = tmp_path / "deploy-state" / "tokyo-runtime-deploy.lock"
    lock = machine.acquire_deploy_lock(lock_path, require_root_owner=False)
    assert lock is not None
    expected_fd = lock.fileno()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return machine.ChildResult(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(machine, "_subprocess_run_locked", fake_run)
    try:
        result = machine.spawn_locked_mutation_child(
            ["/usr/bin/true"],
            lock_handle=lock,
            canonical_lock_path=lock_path,
            require_root_owner=False,
            cwd=tmp_path,
            timeout=5,
        )
        with pytest.raises(ValueError, match="mutation_child_escape_forbidden"):
            machine.spawn_locked_mutation_child(
                ["/usr/bin/systemd-run", "true"],
                lock_handle=lock,
                canonical_lock_path=lock_path,
                require_root_owner=False,
                cwd=tmp_path,
                timeout=5,
            )
    finally:
        lock.close()

    assert result.returncode == 0
    assert captured["pass_fds"] == (expected_fd,)
    assert captured["start_new_session"] is False
    assert captured["timeout"] == 5


def test_candidate_staging_exports_exact_sha_and_writes_manifest_atomically(
    tmp_path
):
    deploy_root = tmp_path / "brc-deploy"
    source_repo = deploy_root / "source" / "dingdingbot"
    release = deploy_root / "releases" / "candidate"
    lock_path = tmp_path / "deploy-state" / "tokyo-runtime-deploy.lock"
    lock = machine.acquire_deploy_lock(lock_path, require_root_owner=False)
    assert lock is not None
    commands = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        if command[:2] == ["/usr/bin/git", "clone"]:
            (source_repo / ".git").mkdir(parents=True)
        if command[:3] == ["/usr/bin/git", "rev-parse", "FETCH_HEAD"]:
            return machine.ChildResult(returncode=0, stdout="a" * 40 + "\n", stderr="")
        if command[:2] == ["/usr/bin/tar", "-xf"]:
            (release.parent / "candidate.tmp" / "src").mkdir(parents=True)
        return machine.ChildResult(returncode=0, stdout="", stderr="")

    try:
        result = machine.stage_candidate_release(
            deploy_root=deploy_root,
            repo_url="https://example.invalid/repo.git",
            git_ref="codex/release",
            target_sha="a" * 40,
            release_name="candidate",
            lock_handle=lock,
            canonical_lock_path=lock_path,
            require_root_owner=False,
            runner=runner,
        )
    finally:
        lock.close()

    manifest = release / ".brc-release-manifest.json"
    assert result["status"] == "candidate_release_staged"
    assert release.is_dir()
    assert manifest.is_file()
    assert json.loads(manifest.read_text(encoding="utf-8"))["target_sha"] == "a" * 40
    assert any(command[:2] == ("/usr/bin/git", "fetch") for command in commands)
    assert any(command[:2] == ("/usr/bin/git", "archive") for command in commands)
    assert any(command[:2] == ("/usr/bin/tar", "-xf") for command in commands)
