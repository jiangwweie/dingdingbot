from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import stat

import pytest

from scripts import tokyo_runtime_deploy_remote_state_machine as machine
from src.application.readmodels.lifecycle_mutation_enablement_proof import (
    ActionTimeCertificationReferenceV2,
    LaneSourceWatermarkV1,
    LifecycleMutationEnablementProof,
)


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


def test_dirfd_lock_initializer_creates_durable_single_inode_and_rejects_symlink(tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    first = machine._acquire_lock_beneath_root(
        root=root,
        directory_components=("brc-deploy", "deploy-state"),
        lock_name="tokyo-runtime-deploy.lock",
        expected_uid=machine.os.geteuid(),
    )
    lock_path = root / "brc-deploy/deploy-state/tokyo-runtime-deploy.lock"
    inode = lock_path.stat().st_ino
    second = machine._acquire_lock_beneath_root(
        root=root,
        directory_components=("brc-deploy", "deploy-state"),
        lock_name="tokyo-runtime-deploy.lock",
        expected_uid=machine.os.geteuid(),
    )
    try:
        assert first is not None
        assert second is None
        assert lock_path.stat().st_ino == inode
        assert lock_path.stat().st_mode & 0o777 == 0o600
    finally:
        if first is not None:
            first.close()

    unsafe_root = tmp_path / "unsafe"
    unsafe_root.mkdir(mode=0o700)
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    machine.os.symlink(target, unsafe_root / "brc-deploy")
    with pytest.raises(OSError):
        machine._acquire_lock_beneath_root(
            root=unsafe_root,
            directory_components=("brc-deploy", "deploy-state"),
            lock_name="tokyo-runtime-deploy.lock",
            expected_uid=machine.os.geteuid(),
        )


def test_journal_is_hash_chained_and_reloaded(tmp_path):
    journal = machine.DeployJournal(
        tmp_path / "journal.json",
        transaction_id="a1",
        deploy_nonce="nonce-1",
        old_sha="b" * 40,
        target_sha="a" * 40,
    )
    journal.append("bootstrap_locked", {"revision": "120"})
    journal.append("candidate_staged", {"revision": "120"})

    reloaded = machine.DeployJournal.load(tmp_path / "journal.json")

    assert [entry["phase"] for entry in reloaded.entries] == [
        "bootstrap_locked",
        "candidate_staged",
    ]
    assert reloaded.entries[1]["previous_digest"] == reloaded.entries[0]["entry_digest"]


def test_journal_rejects_skipped_or_regressed_phase(tmp_path):
    journal = machine.DeployJournal(
        tmp_path / "journal.json",
        transaction_id="a1",
        deploy_nonce="nonce-1",
        old_sha="b" * 40,
        target_sha="a" * 40,
    )
    with pytest.raises(ValueError, match="deploy_journal_phase_transition_invalid"):
        journal.append("candidate_staged", {})
    journal.append("bootstrap_locked", {})
    journal.append("candidate_staged", {})
    with pytest.raises(ValueError, match="deploy_journal_phase_transition_invalid"):
        journal.append("bootstrap_locked", {})


def test_dependency_identity_binds_lock_and_abi(tmp_path):
    lock = tmp_path / "requirements-runtime.lock"
    lock.write_text("ccxt==4.5.56 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    expected = hashlib.sha256(lock.read_bytes()).hexdigest() + "-cp310-linux_x86_64"
    assert machine.dependency_identity(lock) == expected


def test_canonical_release_tree_digest_binds_path_mode_and_content(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    source = release / "src.py"
    source.write_text("value = 1\n", encoding="utf-8")
    source.chmod(0o644)
    original = machine.canonical_release_tree_digest(release)
    source.chmod(0o755)
    assert machine.canonical_release_tree_digest(release) != original
    source.chmod(0o644)
    source.write_text("value = 2\n", encoding="utf-8")
    assert machine.canonical_release_tree_digest(release) != original
    source.unlink()
    source.write_text("value = 1\n", encoding="utf-8")
    source.chmod(0o644)
    (release / "extra.py").write_text("extra\n", encoding="utf-8")
    assert machine.canonical_release_tree_digest(release) != original
    (release / "extra.py").unlink()
    (release / "link").symlink_to(source)
    with pytest.raises(ValueError, match="symlink_forbidden"):
        machine.canonical_release_tree_digest(release)


def test_canonical_release_tree_digest_ignores_runtime_bytecode_only(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    source = release / "src.py"
    source.write_text("value = 1\n", encoding="utf-8")
    original = machine.canonical_release_tree_digest(release)

    cache = release / "__pycache__"
    cache.mkdir()
    (cache / "src.cpython-310.pyc").write_bytes(b"runtime-cache")
    (release / "generated.pyo").write_bytes(b"runtime-cache")

    assert machine.canonical_release_tree_digest(release) == original
    source.write_text("value = 2\n", encoding="utf-8")
    assert machine.canonical_release_tree_digest(release) != original


def test_certification_generation_journal_appends_superseding_pair_proof_and_commit(
    tmp_path,
):
    path = tmp_path / "certification-generations.jsonl"
    journal = machine.CertificationGenerationJournal.load_or_create(
        path,
        transaction_id="a1b2c3d4",
        deploy_nonce="nonce-a1b2c3d4",
        target_sha="a" * 40,
    )
    for generation in (1, 2):
        journal.append(
            cert_pair={
                "ref": f"cert:{generation}",
                "payload": {"fact_min_valid_until_ms": 9_999_999_999_999},
                "generation": generation,
            },
            lifecycle={"lifecycle_proof_ref": f"proof:{generation}", "enabled": True},
            activation_commit={
                "action_time_certification_ref": f"cert:{generation}",
                "certification_generation": generation,
                "lifecycle_proof_ref": f"proof:{generation}",
            },
        )

    reloaded = machine.CertificationGenerationJournal.load_or_create(
        path,
        transaction_id="a1b2c3d4",
        deploy_nonce="nonce-a1b2c3d4",
        target_sha="a" * 40,
    )

    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert reloaded.latest is not None
    assert reloaded.latest["cert_pair"]["ref"] == "cert:2"
    assert reloaded.latest["activation_commit"]["lifecycle_proof_ref"] == "proof:2"


def test_incomplete_immutable_venv_is_rebuilt_with_hashed_lock(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    (release / "src").mkdir()
    lock = release / "requirements-runtime.lock"
    lock.write_text("ccxt==4.5.56 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    (release / ".brc-release-manifest.json").write_text(
        json.dumps({"source_tree_digest": machine.canonical_release_tree_digest(release)}),
        encoding="utf-8",
    )
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
            "--expected-revision",
            "136",
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
    command_environments = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        command_environments.append((tuple(command), kwargs.get("env")))
        if command[:2] == ["/usr/bin/git", "clone"]:
            (source_repo / ".git").mkdir(parents=True)
        if command[-2:] == ["rev-parse", "FETCH_HEAD"]:
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
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o644
    assert json.loads(manifest.read_text(encoding="utf-8"))["target_sha"] == "a" * 40
    git_repo_commands = [
        command
        for command in commands
        if command[0] == "/usr/bin/git" and command[1] != "clone"
    ]
    assert git_repo_commands
    expected_owner_uid = str(source_repo.stat().st_uid)
    assert all(
        environment is not None and environment["SUDO_UID"] == expected_owner_uid
        for command, environment in command_environments
        if command in git_repo_commands
    )
    assert any("fetch" in command for command in git_repo_commands)
    assert any("archive" in command for command in git_repo_commands)
    assert any(command[:2] == ("/usr/bin/tar", "-xf") for command in commands)


def test_candidate_reuse_rejects_coherent_tree_and_manifest_rewrite(tmp_path):
    deploy_root = tmp_path / "brc-deploy"
    source_repo = deploy_root / "source" / "dingdingbot"
    release = deploy_root / "releases" / "candidate"
    lock_path = tmp_path / "deploy-state" / "tokyo-runtime-deploy.lock"
    lock = machine.acquire_deploy_lock(lock_path, require_root_owner=False)
    assert lock is not None

    def runner(command, **kwargs):
        if command[:2] == ["/usr/bin/git", "clone"]:
            (source_repo / ".git").mkdir(parents=True)
        if command[-2:] == ["rev-parse", "FETCH_HEAD"]:
            return machine.ChildResult(returncode=0, stdout="a" * 40 + "\n", stderr="")
        if command[:2] == ["/usr/bin/tar", "-xf"]:
            destination = Path(command[command.index("-C") + 1])
            (destination / "src").mkdir(parents=True)
            (destination / "src" / "tracked.py").write_text(
                "value = 'target'\n", encoding="utf-8"
            )
        return machine.ChildResult(returncode=0, stdout="", stderr="")

    try:
        machine.stage_candidate_release(
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
        (release / "src" / "tracked.py").write_text(
            "value = 'rewritten'\n", encoding="utf-8"
        )
        manifest = release / ".brc-release-manifest.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["source_tree_digest"] = machine.canonical_release_tree_digest(release)
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="candidate_release_target_tree_digest_mismatch"):
            machine.stage_candidate_release(
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


def test_previous_release_gets_compatible_venv_before_unit_mutation(tmp_path):
    previous = tmp_path / "releases" / "old"
    previous.mkdir(parents=True)
    deployed_venv = tmp_path / "venvs" / "legacy"
    (deployed_venv / "bin").mkdir(parents=True)
    python = deployed_venv / "bin" / "python"
    python.write_text("", encoding="utf-8")
    commands = []

    def runner(command, **kwargs):
        commands.append((tuple(command), kwargs["cwd"]))
        return machine.ChildResult(returncode=0, stdout="", stderr="")

    result = machine.ensure_previous_release_venv_compatibility(
        previous_release_path=previous,
        deployed_venv_path=deployed_venv,
        runner=runner,
    )

    assert result["status"] == "previous_release_venv_compatible"
    assert (previous / ".venv").resolve() == deployed_venv.resolve()
    assert commands == [
        (
            (str(previous / ".venv/bin/python"), "-c", "import src.main"),
            previous,
        )
    ]


def test_previous_immutable_release_keeps_its_existing_venv_binding(tmp_path):
    previous = tmp_path / "releases/old"
    previous.mkdir(parents=True)
    immutable = tmp_path / "venvs/immutable/runtime"
    (immutable / "bin").mkdir(parents=True)
    (immutable / "bin/python").write_text("", encoding="utf-8")
    fallback = tmp_path / "venvs/legacy"
    (fallback / "bin").mkdir(parents=True)
    (fallback / "bin/python").write_text("", encoding="utf-8")
    (previous / ".venv").symlink_to(immutable)

    result = machine.ensure_previous_release_venv_compatibility(
        previous_release_path=previous,
        deployed_venv_path=fallback,
        runner=lambda command, **kwargs: machine.ChildResult(
            returncode=0, stdout="", stderr=""
        ),
    )

    assert (previous / ".venv").resolve() == immutable.resolve()
    assert result["venv_path"] == str(immutable.resolve())


def test_writer_fence_installs_all_interlocks_before_stopping_writers(tmp_path):
    release = tmp_path / "candidate"
    (release / ".venv/bin").mkdir(parents=True)
    (release / ".venv/bin/python").write_text("", encoding="utf-8")
    (release / "scripts").mkdir()
    (release / "scripts/set_production_writer_fence.py").write_text("", encoding="utf-8")
    dropin = release / "deploy/systemd/production-writer-fence.conf"
    dropin.parent.mkdir(parents=True)
    dropin.write_text("[Unit]\nConditionPathExists=!/marker\n", encoding="utf-8")
    commands = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        return machine.ChildResult(
            returncode=0,
            stdout='{"status":"fence_engaged","inode":77}',
            stderr="",
        )

    result = machine.engage_production_writer_fence(
        release_path=release,
        transaction_id="a1b2c3d4",
        deploy_nonce="nonce-a1b2c3d4",
        target_sha="a" * 40,
        runner=runner,
    )

    install_indexes = [
        index for index, command in enumerate(commands) if command[0] == "/usr/bin/install"
    ]
    engage_index = next(
        index for index, command in enumerate(commands) if "--engage" in command
    )
    stop_index = next(
        index for index, command in enumerate(commands) if command[1] == "stop"
    )
    assert len(install_indexes) == len(machine.PRODUCTION_WRITER_UNITS)
    assert max(install_indexes) < engage_index < stop_index
    assert result["status"] == "production_writers_fenced"
    assert result["fence_inode"] == 77


def test_writer_fence_treats_not_yet_installed_canary_units_as_stopped(tmp_path):
    release = tmp_path / "candidate"
    (release / ".venv/bin").mkdir(parents=True)
    (release / ".venv/bin/python").write_text("", encoding="utf-8")
    (release / "scripts").mkdir()
    (release / "scripts/set_production_writer_fence.py").write_text("", encoding="utf-8")
    dropin = release / "deploy/systemd/production-writer-fence.conf"
    dropin.parent.mkdir(parents=True)
    dropin.write_text("[Unit]\nConditionPathExists=!/marker\n", encoding="utf-8")
    missing = {
        "brc-runtime-signal-watcher-canary.service",
        "brc-owner-console-canary-readonly.service",
    }

    def runner(command, **kwargs):
        if command[1] == "stop" and command[2] in missing:
            return machine.ChildResult(returncode=5, stdout="", stderr="not found")
        if command[1:4] == ["show", "--property=LoadState", "--value"]:
            state = "not-found" if command[4] in missing else "loaded"
            return machine.ChildResult(returncode=0, stdout=state + "\n", stderr="")
        if "--engage" in command:
            return machine.ChildResult(
                returncode=0,
                stdout='{"status":"fence_engaged","inode":77}',
                stderr="",
            )
        return machine.ChildResult(returncode=0, stdout="inactive\n", stderr="")

    result = machine.engage_production_writer_fence(
        release_path=release,
        transaction_id="a1b2c3d4",
        deploy_nonce="nonce-a1b2c3d4",
        target_sha="a" * 40,
        runner=runner,
    )

    assert result["status"] == "production_writers_fenced"
    assert sorted(result["units_not_installed"]) == sorted(missing)


def _write_migration_in_progress_predecessor_journal(
    path: Path,
    *,
    old_sha: str,
    target_sha: str,
    transaction_id: str = "deadbeef",
    deploy_nonce: str = "old-nonce",
) -> dict[str, dict[str, object]]:
    journal = machine.DeployJournal(
        path,
        transaction_id=transaction_id,
        deploy_nonce=deploy_nonce,
        old_sha=old_sha,
        target_sha=target_sha,
    )
    prepolicy = {
        unit: {"active": unit.endswith("watcher.timer")}
        for unit in machine.PRODUCTION_WRITER_UNITS
    }
    for phase in machine.DEPLOY_PHASES:
        result: dict[str, object] = {"status": phase}
        if phase == "production_writers_fenced":
            result["unit_prepolicy"] = prepolicy
        if phase == "pre_migration":
            result["actual_revision"] = "125"
        journal.append(phase, {"result": result})
        if phase == "migration_in_progress":
            break
    return prepolicy


def test_forward_fix_fence_supersession_requires_exact_stranded_predecessor(tmp_path):
    old_sha = "b" * 40
    failed_target = "a" * 40
    new_target = "c" * 40
    previous = tmp_path / "releases/old"
    previous.mkdir(parents=True)
    (previous / ".brc-release-manifest.json").write_text(
        json.dumps({"target_sha": old_sha}), encoding="utf-8"
    )
    current = tmp_path / "app/current"
    current.parent.mkdir(parents=True)
    current.symlink_to(previous)
    release = tmp_path / "releases/new"
    release.mkdir()
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql://example.invalid/db\n")
    journal_dir = tmp_path / "deploy-state"
    journal_dir.mkdir()
    prepolicy = _write_migration_in_progress_predecessor_journal(
        journal_dir / "tokyo-runtime-deploy-deadbeef.json",
        old_sha=old_sha,
        target_sha=failed_target,
    )
    marker = tmp_path / "production-writers.blocked"
    marker.write_text(
        json.dumps(
            {
                "schema": "brc.production_writer_fence.v1",
                "deploy_transaction_id": "deadbeef",
                "deploy_nonce": "old-nonce",
                "target_runtime_head": failed_target,
            }
        ),
        encoding="utf-8",
    )
    marker.chmod(0o600)

    def runner(command, **kwargs):
        if command[-2:] == ["alembic", "current"]:
            return machine.ChildResult(returncode=0, stdout="125 (head)\n", stderr="")
        if command[0] == "/usr/bin/systemctl":
            return machine.ChildResult(returncode=0, stdout="inactive\n", stderr="")
        if any(str(item).endswith("set_ticket_lifecycle_mutation_capability.py") for item in command):
            return machine.ChildResult(
                returncode=0,
                stdout='{"enabled":false,"exchange_write_called":false}',
                stderr="",
            )
        raise AssertionError(command)

    result = machine.validate_forward_fix_fence_supersession(
        predecessor_transaction_id="deadbeef",
        predecessor_deploy_nonce="old-nonce",
        old_sha=old_sha,
        target_sha=new_target,
        previous_release_path=previous,
        app_current=current,
        expected_revision="136",
        release_path=release,
        env_path=env_file,
        deploy_journal_directory=journal_dir,
        runner=runner,
        require_root_owner=False,
        fence_marker=marker,
    )

    assert result["status"] == "forward_fix_fence_supersession_authorized"
    assert result["predecessor_fence"]["target_runtime_head"] == failed_target
    assert result["unit_prepolicy"] == prepolicy


def test_forward_fix_fence_supersession_allows_post_migration_pre_activation_only(tmp_path):
    old_sha, predecessor_sha, successor_sha = "b" * 40, "a" * 40, "c" * 40
    previous = tmp_path / "releases/current"
    previous.mkdir(parents=True)
    (previous / ".brc-release-manifest.json").write_text(
        json.dumps({"target_sha": old_sha}), encoding="utf-8"
    )
    current = tmp_path / "app/current"
    current.parent.mkdir(parents=True)
    current.symlink_to(previous)
    release = tmp_path / "releases/successor"
    release.mkdir()
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql://example.invalid/db\n")
    journal_dir = tmp_path / "deploy-state"
    journal_dir.mkdir()
    journal_path = journal_dir / "tokyo-runtime-deploy-deadbeef.json"
    _write_migration_in_progress_predecessor_journal(
        journal_path, old_sha=old_sha, target_sha=predecessor_sha
    )
    journal = machine.DeployJournal.load(journal_path)
    schema_index = machine.DEPLOY_PHASES.index("schema_migrated")
    projection_index = machine.DEPLOY_PHASES.index("pre_canary_projection")
    for phase in machine.DEPLOY_PHASES[schema_index:projection_index + 1]:
        result = {"status": phase}
        if phase == "schema_migrated":
            result["revision"] = "136"
        journal.append(phase, {"result": result})
    marker = tmp_path / "production-writers.blocked"
    marker.write_text(json.dumps({
        "schema": "brc.production_writer_fence.v1", "deploy_transaction_id": "deadbeef",
        "deploy_nonce": "old-nonce", "target_runtime_head": predecessor_sha,
    }), encoding="utf-8")
    marker.chmod(0o600)

    def runner(command, **kwargs):
        if command[-2:] == ["alembic", "current"]:
            return machine.ChildResult(returncode=0, stdout="136 (head)\n", stderr="")
        if command[0] == "/usr/bin/systemctl":
            return machine.ChildResult(returncode=0, stdout="inactive\n", stderr="")
        return machine.ChildResult(returncode=0, stdout='{"enabled":false,"exchange_write_called":false}', stderr="")

    result = machine.validate_forward_fix_fence_supersession(
        predecessor_transaction_id="deadbeef", predecessor_deploy_nonce="old-nonce",
        old_sha=old_sha, target_sha=successor_sha,
        previous_release_path=previous, app_current=current, expected_revision="136",
        release_path=release, env_path=env_file, deploy_journal_directory=journal_dir,
        runner=runner, require_root_owner=False, fence_marker=marker,
    )
    assert result["mode"] == "post_migration_pre_activation"


def test_forward_fix_fence_supersession_recovers_committed_but_unjournaled_migration(
    tmp_path,
):
    old_sha, predecessor_sha, successor_sha = "b" * 40, "a" * 40, "c" * 40
    previous = tmp_path / "releases/current"
    previous.mkdir(parents=True)
    (previous / ".brc-release-manifest.json").write_text(
        json.dumps({"target_sha": old_sha}), encoding="utf-8"
    )
    current = tmp_path / "app/current"
    current.parent.mkdir(parents=True)
    current.symlink_to(previous)
    release = tmp_path / "releases/successor"
    release.mkdir()
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql://example.invalid/db\n")
    journal_dir = tmp_path / "deploy-state"
    journal_dir.mkdir()
    _write_migration_in_progress_predecessor_journal(
        journal_dir / "tokyo-runtime-deploy-deadbeef.json",
        old_sha=old_sha,
        target_sha=predecessor_sha,
    )
    marker = tmp_path / "production-writers.blocked"
    marker.write_text(json.dumps({
        "schema": "brc.production_writer_fence.v1", "deploy_transaction_id": "deadbeef",
        "deploy_nonce": "old-nonce", "target_runtime_head": predecessor_sha,
    }), encoding="utf-8")
    marker.chmod(0o600)

    def runner(command, **kwargs):
        if command[-2:] == ["alembic", "current"]:
            return machine.ChildResult(returncode=0, stdout="136 (head)\n", stderr="")
        if command[0] == "/usr/bin/systemctl":
            return machine.ChildResult(returncode=0, stdout="inactive\n", stderr="")
        return machine.ChildResult(
            returncode=0,
            stdout='{"enabled":false,"exchange_write_called":false}',
            stderr="",
        )

    result = machine.validate_forward_fix_fence_supersession(
        predecessor_transaction_id="deadbeef", predecessor_deploy_nonce="old-nonce",
        old_sha=old_sha, target_sha=successor_sha,
        previous_release_path=previous, app_current=current, expected_revision="136",
        release_path=release, env_path=env_file, deploy_journal_directory=journal_dir,
        runner=runner, require_root_owner=False, fence_marker=marker,
    )

    assert result["mode"] == "post_migration_unjournaled_pre_activation"


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        ("marker", "fence_supersession_marker_journal_mismatch"),
        ("schema", "fence_supersession_schema_revision_mismatch"),
        ("writer", "fence_supersession_writer_not_inactive"),
    ],
)
def test_forward_fix_fence_supersession_rejects_any_changed_containment_fact(
    tmp_path, mutate, error
):
    old_sha = "b" * 40
    failed_target = "a" * 40
    previous = tmp_path / "releases/old"
    previous.mkdir(parents=True)
    (previous / ".brc-release-manifest.json").write_text(
        json.dumps({"target_sha": old_sha}), encoding="utf-8"
    )
    current = tmp_path / "app/current"
    current.parent.mkdir(parents=True)
    current.symlink_to(previous)
    release = tmp_path / "releases/new"
    release.mkdir()
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql://example.invalid/db\n")
    journal_dir = tmp_path / "deploy-state"
    journal_dir.mkdir()
    _write_migration_in_progress_predecessor_journal(
        journal_dir / "tokyo-runtime-deploy-deadbeef.json",
        old_sha=old_sha,
        target_sha=failed_target,
    )
    marker = tmp_path / "production-writers.blocked"
    marker_payload = {
        "schema": "brc.production_writer_fence.v1",
        "deploy_transaction_id": "deadbeef",
        "deploy_nonce": "old-nonce",
        "target_runtime_head": failed_target,
    }
    if mutate == "marker":
        marker_payload["deploy_nonce"] = "wrong"
    marker.write_text(json.dumps(marker_payload), encoding="utf-8")
    marker.chmod(0o600)

    def runner(command, **kwargs):
        if command[-2:] == ["alembic", "current"]:
            revision = "124" if mutate == "schema" else "125"
            return machine.ChildResult(returncode=0, stdout=revision + " (head)\n", stderr="")
        if command[0] == "/usr/bin/systemctl":
            state = "active" if mutate == "writer" else "inactive"
            return machine.ChildResult(returncode=0, stdout=state + "\n", stderr="")
        if any(str(item).endswith("set_ticket_lifecycle_mutation_capability.py") for item in command):
            return machine.ChildResult(
                returncode=0,
                stdout='{"enabled":false,"exchange_write_called":false}',
                stderr="",
            )
        raise AssertionError(command)

    with pytest.raises((RuntimeError, ValueError), match=error):
        machine.validate_forward_fix_fence_supersession(
            predecessor_transaction_id="deadbeef",
            predecessor_deploy_nonce="old-nonce",
            old_sha=old_sha,
            target_sha="c" * 40,
            previous_release_path=previous,
            app_current=current,
            expected_revision="136",
            release_path=release,
            env_path=env_file,
            deploy_journal_directory=journal_dir,
            runner=runner,
            require_root_owner=False,
            fence_marker=marker,
        )


def test_fenced_migration_uses_only_candidate_python_and_reaches_exact_revision(
    tmp_path
):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text("DATABASE_URL='postgresql://example.invalid/db'\n", encoding="utf-8")
    commands = []

    def runner(command, **kwargs):
        commands.append((tuple(command), kwargs))
        if "--status" in command:
            return machine.ChildResult(
                returncode=0,
                stdout='{"enabled":true,"exchange_write_called":false}',
                stderr="",
            )
        if any(str(item).endswith("verify_canary_readonly_role_preflight.py") for item in command):
            return machine.ChildResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": "canary_readonly_role_preflight_passed",
                        "current_user": "brc_runtime_app",
                        "exchange_write_called": False,
                    }
                ),
                stderr="",
            )
        if any(str(item).endswith("project_instrument_rule_snapshots.py") for item in command):
            return machine.ChildResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": "instrument_rules_projected",
                        "target_count": 6,
                        "current_rule_ids": [f"rule:{index}" for index in range(6)],
                        "exchange_write_called": False,
                        "order_created": False,
                    }
                ),
                stderr="",
            )
        if any(str(item).endswith("verify_canonical_instrument_identity_readiness.py") for item in command):
            return machine.ChildResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": "canonical_instrument_identity_readiness_certified",
                        "active_lane_count": 22,
                        "canonical_instrument_count": 6,
                        "current_v2_rule_count": 6,
                        "exchange_write_called": False,
                        "order_created": False,
                    }
                ),
                stderr="",
            )
        if command[-2:] == ["alembic", "current"]:
            return machine.ChildResult(returncode=0, stdout="124 (head)\n", stderr="")
        return machine.ChildResult(returncode=0, stdout='{"status":"ok"}', stderr="")

    result = machine.run_fenced_schema_migration(
        release_path=release,
        env_path=env_file,
        transaction_id="a1b2c3d4",
        expected_revision="124",
        runner=runner,
    )

    assert result == {
        "status": "schema_migrated",
        "revision": "124",
        "lifecycle_capability_was_enabled": True,
        "instrument_rule_projection": {
            "status": "instrument_rules_projected",
            "target_count": 6,
            "current_rule_ids": [f"rule:{index}" for index in range(6)],
            "exchange_write_called": False,
            "order_created": False,
        },
        "canonical_instrument_readiness": {
            "status": "canonical_instrument_identity_readiness_certified",
            "active_lane_count": 22,
            "canonical_instrument_count": 6,
            "current_v2_rule_count": 6,
            "exchange_write_called": False,
            "order_created": False,
        },
    }
    assert all(command[0] == str(python) for command, _ in commands)
    migration_index = next(index for index, (command, _) in enumerate(commands) if "upgrade" in command)
    assert any(command[-3:] == ("-m", "alembic", "upgrade") or "upgrade" in command for command, _ in commands)
    projector_index = next(index for index, (command, _) in enumerate(commands) if any(str(item).endswith("project_instrument_rule_snapshots.py") for item in command))
    readiness_index = next(index for index, (command, _) in enumerate(commands) if any(str(item).endswith("verify_canonical_instrument_identity_readiness.py") for item in command))
    assert migration_index < projector_index < readiness_index
    assert all(
        item["env"]["DATABASE_URL"] == "postgresql://example.invalid/db"
        for _, item in commands
    )


def test_application_role_preflight_uses_application_environment_only(tmp_path):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime-application.env"
    env_file.write_text(
        "PG_DATABASE_URL='postgresql://application.invalid/db'\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return machine.ChildResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "canary_readonly_role_preflight_passed",
                    "current_user": "brc_runtime_app",
                    "exchange_write_called": False,
                }
            ),
            stderr="",
        )

    result = machine.verify_runtime_application_role_preflight(
        release_path=release,
        env_path=env_file,
        runner=runner,
    )

    assert result["current_user"] == "brc_runtime_app"
    assert calls[0][0][-1] == "scripts/verify_canary_readonly_role_preflight.py"
    assert calls[0][1]["env"]["PG_DATABASE_URL"] == "postgresql://application.invalid/db"


def test_fenced_migration_reports_only_bounded_terminal_stderr_line(tmp_path):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text("DATABASE_URL='postgresql://example.invalid/db'\n", encoding="utf-8")

    def runner(command, **kwargs):
        if "upgrade" in command:
            return machine.ChildResult(
                returncode=1,
                stdout="",
                stderr="verbose internal context\npsycopg.errors.UndefinedColumn: missing_column",
            )
        if "--status" in command:
            return machine.ChildResult(
                returncode=0,
                stdout='{"enabled":false,"exchange_write_called":false}',
                stderr="",
            )
        if any(str(item).endswith("verify_canary_readonly_role_preflight.py") for item in command):
            return machine.ChildResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": "canary_readonly_role_preflight_passed",
                        "current_user": "brc_runtime_app",
                        "exchange_write_called": False,
                    }
                ),
                stderr="",
            )
        return machine.ChildResult(returncode=0, stdout='{"status":"ok"}', stderr="")

    with pytest.raises(
        RuntimeError,
        match="fenced_schema_command_failed:-m:alembic:upgrade:psycopg.errors.UndefinedColumn: missing_column",
    ):
        machine.run_fenced_schema_migration(
            release_path=release,
            env_path=env_file,
            transaction_id="a1b2c3d4",
            expected_revision="124",
            runner=runner,
        )


def test_fenced_migration_omits_sqlalchemy_context_link_from_failure_summary(tmp_path):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text("DATABASE_URL='postgresql://example.invalid/db'\n", encoding="utf-8")

    def runner(command, **kwargs):
        if "upgrade" in command:
            return machine.ChildResult(
                returncode=1,
                stdout="",
                stderr="psycopg.errors.UniqueViolation: duplicate identity\n(Background on this error at: https://sqlalche.me/e/20/gkpj)",
            )
        if "--status" in command:
            return machine.ChildResult(
                returncode=0,
                stdout='{"enabled":false,"exchange_write_called":false}',
                stderr="",
            )
        if any(str(item).endswith("verify_canary_readonly_role_preflight.py") for item in command):
            return machine.ChildResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": "canary_readonly_role_preflight_passed",
                        "current_user": "brc_runtime_app",
                        "exchange_write_called": False,
                    }
                ),
                stderr="",
            )
        return machine.ChildResult(returncode=0, stdout='{"status":"ok"}', stderr="")

    with pytest.raises(
        RuntimeError,
        match="fenced_schema_command_failed:-m:alembic:upgrade:psycopg.errors.UniqueViolation: duplicate identity",
    ):
        machine.run_fenced_schema_migration(
            release_path=release,
            env_path=env_file,
            transaction_id="a1b2c3d4",
            expected_revision="124",
            runner=runner,
        )


def test_fenced_migration_prefers_database_error_to_sql_statement(tmp_path):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text("DATABASE_URL='postgresql://example.invalid/db'\n", encoding="utf-8")

    def runner(command, **kwargs):
        if "upgrade" in command:
            return machine.ChildResult(
                returncode=1,
                stdout="",
                stderr="sqlalchemy.exc.IntegrityError: foreign key violation\n[SQL: ALTER TABLE brc_action_time_tickets ADD CONSTRAINT unsafe]\n(Background on this error at: https://sqlalche.me/e/20/gkpj)",
            )
        if "--status" in command:
            return machine.ChildResult(
                returncode=0,
                stdout='{"enabled":false,"exchange_write_called":false}',
                stderr="",
            )
        if any(str(item).endswith("verify_canary_readonly_role_preflight.py") for item in command):
            return machine.ChildResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": "canary_readonly_role_preflight_passed",
                        "current_user": "brc_runtime_app",
                        "exchange_write_called": False,
                    }
                ),
                stderr="",
            )
        return machine.ChildResult(returncode=0, stdout='{"status":"ok"}', stderr="")

    with pytest.raises(
        RuntimeError,
        match="fenced_schema_command_failed:-m:alembic:upgrade:sqlalchemy.exc.IntegrityError: foreign key violation",
    ):
        machine.run_fenced_schema_migration(
            release_path=release,
            env_path=env_file,
            transaction_id="a1b2c3d4",
            expected_revision="124",
            runner=runner,
        )


def test_candidate_units_install_while_fenced_then_pointer_switches_atomically(tmp_path):
    release = tmp_path / "releases" / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    helper = release / "scripts/atomic_switch_release_pointer.py"
    helper.parent.mkdir()
    helper.write_text("", encoding="utf-8")
    for relative in machine.REPOSITORY_SYSTEMD_FILES:
        source = release / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            (
                "[Service]\nEnvironment=BRC_RUNTIME_HEAD=__BRC_CANDIDATE_SHA__\n"
                if relative.name == "50-runtime-release-identity.conf"
                else "unit"
            ),
            encoding="utf-8",
        )
    commands = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        if str(helper) in command:
            return machine.ChildResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": "release_pointer_switched",
                        "release_pointer": str(tmp_path / "app/current"),
                        "target_runtime_head": "a" * 40,
                    }
                ),
                stderr="",
            )
        return machine.ChildResult(returncode=0, stdout="", stderr="")

    result = machine.install_candidate_units_and_switch_pointer(
        release_path=release,
        app_current=tmp_path / "app/current",
        target_sha="a" * 40,
        systemd_root=tmp_path / "systemd",
        runner=runner,
    )

    pointer_index = next(
        index for index, command in enumerate(commands) if str(helper) in command
    )
    assert commands[pointer_index - 1] == ("/usr/bin/systemctl", "daemon-reload")
    assert all(
        (tmp_path / "systemd" / relative.relative_to("deploy/systemd")).is_file()
        for relative in machine.REPOSITORY_SYSTEMD_FILES
    )
    identity_dropins = [
        relative
        for relative in machine.REPOSITORY_SYSTEMD_FILES
        if relative.name == "50-runtime-release-identity.conf"
    ]
    assert len(identity_dropins) == 4
    for relative in identity_dropins:
        rendered = (
            tmp_path / "systemd" / relative.relative_to("deploy/systemd")
        ).read_text(encoding="utf-8")
        assert rendered == "[Service]\nEnvironment=BRC_RUNTIME_HEAD=" + "a" * 40 + "\n"
        assert "__BRC_CANDIDATE_SHA__" not in rendered
    assert result["status"] == "candidate_pointer_active"


def test_five_readonly_canaries_never_start_production_writer(tmp_path):
    release = tmp_path / "candidate"
    release.mkdir()
    commands = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        return machine.ChildResult(returncode=0, stdout="success\n", stderr="")

    result = machine.run_five_readonly_canaries(
        release_path=release,
        runner=runner,
    )

    joined = "\n".join(" ".join(command) for command in commands)
    assert joined.count("systemctl start brc-runtime-signal-watcher-canary.service") == 5
    assert "systemctl start brc-owner-console-canary-readonly.service" in joined
    assert "socket.create_connection" in joined
    assert "systemctl stop brc-owner-console-canary-readonly.service" in joined
    assert "systemctl start brc-owner-console-backend.service" not in joined
    assert "systemctl start brc-runtime-signal-watcher.service" not in joined
    assert result == {"status": "readonly_canary_complete", "successful_ticks": 5}


def test_shared_readiness_helper_parent_is_traversable_but_not_listable_or_writable(tmp_path):
    deploy_root = tmp_path / "deploy"
    release = deploy_root / "releases/candidate"
    release.mkdir(parents=True)
    parent = deploy_root / "control-plane"
    parent.mkdir(mode=0o700)
    helper = parent / "check_runtime_postgres_ready.py"
    helper.write_text("print('ready')\n", encoding="utf-8")
    helper.chmod(0o755)

    machine._ensure_shared_readiness_helper_access(
        release_path=release,
        require_root_owner=False,
    )

    assert stat.S_IMODE(parent.stat().st_mode) == 0o711


def test_canary_runtime_environment_is_derived_from_bounded_pg_scope(tmp_path):
    deploy_root = tmp_path / "deploy"
    release = deploy_root / "releases/candidate"
    release.mkdir(parents=True)
    env_file = deploy_root / "env/live-readonly.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("PG_DATABASE_URL=postgresql://example.invalid/db\n")
    runtime_ids = ["strategy-runtime-a", "strategy-runtime-b"]

    def runner(command, **kwargs):
        return machine.ChildResult(
            returncode=0,
            stdout=json.dumps({"runtime_instance_ids": runtime_ids}),
            stderr="",
        )

    machine._prepare_canary_runtime_environment(
        release_path=release,
        env_path=env_file,
        lock_handle=None,
        canonical_lock_path=tmp_path / "lock",
        require_root_owner=False,
        runner=runner,
    )

    target = deploy_root / "env/runtime-signal-watcher-canary.env"
    assert target.read_text() == (
        "BRC_CANARY_RUNTIME_INSTANCE_IDS=strategy-runtime-a,strategy-runtime-b\n"
    )
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_persistent_runtime_config_is_copied_outside_immutable_release_once(tmp_path):
    previous = tmp_path / "previous"
    source = previous / "data/v3_dev.db"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"sqlite-config-v1")
    target_dir = tmp_path / "var/lib/brc-runtime/config"

    first = machine._provision_persistent_runtime_config(
        previous_release_path=previous,
        target_dir=target_dir,
    )
    source.write_bytes(b"sqlite-config-v2")
    second = machine._provision_persistent_runtime_config(
        previous_release_path=previous,
        target_dir=target_dir,
    )

    target = target_dir / "v3_dev.db"
    assert target.read_bytes() == b"sqlite-config-v1"
    assert stat.S_IMODE(target_dir.stat().st_mode) == 0o750
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert first["status"] == second["status"] == "persistent_runtime_config_ready"


def test_existing_persistent_runtime_config_does_not_require_previous_release_copy(tmp_path):
    previous = tmp_path / "previous-without-data"
    previous.mkdir()
    target_dir = tmp_path / "var/lib/brc-runtime/config"
    target_dir.mkdir(parents=True, mode=0o750)
    target = target_dir / "v3_dev.db"
    target.write_bytes(b"existing-config")
    target.chmod(0o640)

    result = machine._provision_persistent_runtime_config(
        previous_release_path=previous,
        target_dir=target_dir,
    )

    assert result["status"] == "persistent_runtime_config_ready"
    assert result["source_sha256"] is None
    assert target.read_bytes() == b"existing-config"


def test_fact_refresh_returns_exact_ids_for_v2_certification(tmp_path):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL='postgresql://example.invalid/db'\n", encoding="utf-8")

    commands = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        if any(str(item).endswith("build_runtime_account_safe_facts.py") for item in command):
            return machine.ChildResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": "runtime_account_safe_facts_ready",
                        "account_safe_facts_ready": True,
                        "pg_fact_snapshot_ids": ["fact:2", "fact:1"],
                    }
                ),
                stderr="",
            )
        return machine.ChildResult(returncode=0, stdout='{"status":"ok"}', stderr="")

    result = machine.refresh_candidate_account_facts(
        release_path=release,
        env_path=env_file,
        runner=runner,
    )

    assert result == {
        "status": "candidate_account_facts_refreshed",
        "fact_snapshot_ids": ("fact:1", "fact:2"),
        "account_safe_facts_ready": True,
    }
    assert "--allow-blocked-current-projection" in next(
        command for command in commands
        if "scripts/build_runtime_account_safe_facts.py" in command
    )


def test_fact_refresh_persists_blocked_existing_position_without_granting_submit(
    tmp_path,
):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "PG_DATABASE_URL='postgresql://example.invalid/db'\n",
        encoding="utf-8",
    )

    def runner(command, **kwargs):
        return machine.ChildResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "runtime_account_safe_facts_blocked",
                    "account_safe_facts_ready": False,
                    "pg_fact_snapshot_ids": ["fact:existing-position"],
                }
            ),
            stderr="",
        )

    result = machine.refresh_candidate_account_facts(
        release_path=release,
        env_path=env_file,
        runner=runner,
    )

    assert result == {
        "status": "candidate_account_facts_refreshed",
        "fact_snapshot_ids": ("fact:existing-position",),
        "account_safe_facts_ready": False,
    }


def test_candidate_certification_uses_typed_stage_nonce_and_exact_fact_ids(tmp_path):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL='postgresql://example.invalid/db'\n", encoding="utf-8")
    commands = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        return machine.ChildResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "action_time_capability_certified",
                    "certification_ref": "action-time-cert:v2:" + "a" * 64,
                    "certification_reference": {"schema": "brc.action_time_certification_reference.v2"},
                    "certified_lane_count": 22,
                    "exchange_write_called": False,
                }
            ),
            stderr="",
        )

    result = machine.certify_candidate_action_time(
        release_path=release,
        env_path=env_file,
        target_sha="a" * 40,
        stage="post_canary",
        deploy_nonce="nonce-1",
        fact_snapshot_ids=("fact:1", "fact:2"),
        runner=runner,
    )

    command = commands[0]
    assert "--stage" in command and "post_canary" in command
    assert "--deploy-nonce" in command and "nonce-1" in command
    assert command.count("--fact-snapshot-id") == 2
    assert "--certification-ref" not in command
    assert result["certification_ref"].startswith("action-time-cert:v2:")


def test_lifecycle_policy_restore_persists_v2_proof_when_enablement_is_authorized(tmp_path):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL='postgresql://example.invalid/db'\n", encoding="utf-8")
    commands = []
    typed_reference = ActionTimeCertificationReferenceV2(
        stage="post_canary",
        target_runtime_head="a" * 40,
        certification_input_digest="sha256:" + "1" * 64,
        release_activation_outcome_id="process_outcome:release",
        release_activation_source_watermark="release:1",
        lane_source_watermarks=(
            LaneSourceWatermarkV1(
                lane_scope_key="lane:SOR-001:ETHUSDT:long",
                lane_identity_key="identity:1",
                source_watermark="watermark:1",
                process_outcome_id="process_outcome:1",
            ),
        ),
        fact_snapshot_ids=("fact:1",),
        fact_set_digest="sha256:" + "2" * 64,
        fact_min_valid_until_ms=1_900_000_000_000,
        deploy_nonce="nonce-1",
    )
    reference = typed_reference.model_dump(mode="json")

    def runner(command, **kwargs):
        commands.append(tuple(command))
        return machine.ChildResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "ready",
                    "enabled": True,
                    "blockers": [],
                    "capability": {"proof_schema": "brc.lifecycle_mutation_enablement_proof.v2"},
                }
            ),
            stderr="",
        )

    result = machine.restore_lifecycle_mutation_policy(
        release_path=release,
        env_path=env_file,
        target_sha="a" * 40,
        enable_after_certification=True,
        post_certification_ref=typed_reference.certification_ref(),
        post_certification_reference=reference,
        post_projection_slice_digests={"process_current": "sha256:" + "c" * 64},
        runner=runner,
    )

    command = commands[0]
    assert "--enable" in command
    assert "--proof-json" in command
    assert result["lifecycle_proof_ref"].startswith("lifecycle-cert:v2:")
    assert result["proof"]["schema"] == "brc.lifecycle_mutation_enablement_proof.v2"
    typed_proof = LifecycleMutationEnablementProof.model_validate(result["proof"])
    assert result["lifecycle_proof_ref"] == typed_proof.lifecycle_certification_ref()


def test_activation_apply_removes_fence_then_restores_timers_without_transient_services(
    tmp_path, monkeypatch,
):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL='postgresql://example.invalid/db'\n", encoding="utf-8")
    commands = []
    watcher_show_count = 0
    monkeypatch.setattr(machine.time, "sleep", lambda _seconds: None)

    def runner(command, **kwargs):
        nonlocal watcher_show_count
        commands.append(tuple(command))
        if "set_production_writer_fence.py" in " ".join(command):
            return machine.ChildResult(
                returncode=0,
                stdout='{"status":"fence_removed"}',
                stderr="",
            )
        if command[1:3] == ["show", "brc-runtime-monitor.service"]:
            return machine.ChildResult(
                returncode=0,
                stdout="ActiveState=inactive\nResult=success\nExecMainStatus=0\n",
                stderr="",
            )
        if command[1:3] == ["show", "brc-ticket-lifecycle-maintenance.service"]:
            return machine.ChildResult(
                returncode=0,
                stdout="ActiveState=inactive\nResult=success\nExecMainStatus=0\n",
                stderr="",
            )
        if command[1:3] == ["show", "brc-runtime-signal-watcher.service"]:
            watcher_show_count += 1
            if watcher_show_count == 1:
                return machine.ChildResult(
                    returncode=0,
                    stdout="ActiveState=activating\nResult=success\nExecMainStatus=0\n",
                    stderr="",
                )
            return machine.ChildResult(
                returncode=0,
                stdout="ActiveState=inactive\nResult=success\nExecMainStatus=0\n",
                stderr="",
            )
        return machine.ChildResult(returncode=0, stdout="active\n", stderr="")

    prepolicy = {
        unit: {"active": unit in {
            "brc-owner-console-backend.service",
            "brc-ticket-lifecycle-maintenance.service",
            "brc-runtime-monitor.timer",
            "brc-ticket-lifecycle-maintenance.timer",
            "brc-runtime-signal-watcher.timer",
        }}
        for unit in machine.PRODUCTION_WRITER_UNITS
    }
    result = machine.apply_committed_activation(
        release_path=release,
        env_path=env_file,
        activation_commit={
            "schema": "brc.runtime_activation_commit.v1",
            "status": "runtime_activation_committed",
        },
        unit_prepolicy=prepolicy,
        runner=runner,
    )

    starts = [command for command in commands if command[1:2] == ("start",)]
    assert starts[-1][-1] == "brc-runtime-signal-watcher.timer"
    assert not any(
        command[-1] == "brc-ticket-lifecycle-maintenance.service"
        for command in starts
    )
    reset_services = [
        command[-1]
        for command in commands
        if command[1:2] == ("reset-failed",)
    ]
    assert reset_services == [
        "brc-runtime-monitor.service",
        "brc-ticket-lifecycle-maintenance.service",
        "brc-runtime-signal-watcher.service",
    ]
    assert watcher_show_count == 2
    assert commands[0][1].endswith("set_production_writer_fence.py")
    assert result["status"] == "activation_applied"


def test_activation_restore_failure_reengages_fence_and_disables_lifecycle(
    tmp_path, monkeypatch,
):
    release = tmp_path / "candidate"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    (release / "scripts").mkdir()
    (release / "scripts/set_production_writer_fence.py").write_text(
        "", encoding="utf-8"
    )
    (release / "deploy/systemd").mkdir(parents=True)
    (release / "deploy/systemd/production-writer-fence.conf").write_text(
        "", encoding="utf-8"
    )
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL='postgresql://example.invalid/db'\n", encoding="utf-8")
    commands = []
    monkeypatch.setattr(machine.time, "sleep", lambda _seconds: None)

    def runner(command, **kwargs):
        commands.append(tuple(command))
        joined = " ".join(command)
        if "set_production_writer_fence.py" in joined:
            return machine.ChildResult(
                returncode=0,
                stdout=(
                    '{"status":"fence_removed"}'
                    if "--remove" in command
                    else '{"status":"fence_engaged","inode":42}'
                ),
                stderr="",
            )
        if "set_ticket_lifecycle_mutation_capability.py" in joined:
            return machine.ChildResult(
                returncode=0,
                stdout='{"status":"not_ready","enabled":false}',
                stderr="",
            )
        if command[1:3] == ["show", "brc-runtime-signal-watcher.service"]:
            return machine.ChildResult(
                returncode=0,
                stdout="ActiveState=inactive\nResult=exit-code\nExecMainStatus=1\n",
                stderr="",
            )
        if (
            command[1:2] == ["show"]
            and "--property=ActiveState" in command
        ):
            return machine.ChildResult(returncode=0, stdout="inactive\n", stderr="")
        return machine.ChildResult(returncode=0, stdout="active\n", stderr="")

    prepolicy = {
        unit: {"active": unit == "brc-runtime-signal-watcher.timer"}
        for unit in machine.PRODUCTION_WRITER_UNITS
    }
    activation_commit = {
        "schema": "brc.runtime_activation_commit.v1",
        "status": "runtime_activation_committed",
        "deploy_transaction_id": "a1b2c3d4",
        "deploy_nonce": "nonce-a1b2c3d4",
        "target_runtime_head": "a" * 40,
    }

    with pytest.raises(RuntimeError, match="activation_restore_failed_contained"):
        machine.apply_committed_activation(
            release_path=release,
            env_path=env_file,
            activation_commit=activation_commit,
            unit_prepolicy=prepolicy,
            runner=runner,
        )

    fence_commands = [
        command
        for command in commands
        if "set_production_writer_fence.py" in " ".join(command)
    ]
    assert "--remove" in fence_commands[0]
    assert "--engage" in fence_commands[1]
    assert any(
        "set_ticket_lifecycle_mutation_capability.py" in " ".join(command)
        and "--disable" in command
        for command in commands
    )
    stopped = [command[-1] for command in commands if command[1:2] == ("stop",)]
    assert set(machine.DEPLOY_STOP_UNITS).issubset(stopped)


def test_deploy_transaction_bootstraps_lifecycle_only_with_explicit_intent_and_is_resumable(
    tmp_path, monkeypatch
):
    deploy_root = tmp_path / "brc-deploy"
    release = deploy_root / "releases/candidate"
    previous = deploy_root / "releases/old"
    previous.mkdir(parents=True)
    legacy = deploy_root / "venvs/legacy"
    (legacy / "bin").mkdir(parents=True)
    (legacy / "bin/python").write_text("", encoding="utf-8")
    env_file = deploy_root / "env/live-readonly.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        "EXCHANGE_API_KEY='test-key'\n"
        "PG_DATABASE_URL='postgresql://example.invalid/db'\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    (env_file.parent / machine.RUNTIME_MIGRATION_ENV_NAME).write_text(
        "PG_DATABASE_URL='postgresql://migration.invalid/db'\n",
        encoding="utf-8",
    )
    (env_file.parent / machine.RUNTIME_APPLICATION_PENDING_ENV_NAME).write_text(
        "PG_DATABASE_URL='postgresql://application.invalid/db'\n",
        encoding="utf-8",
    )
    (env_file.parent / machine.RUNTIME_MIGRATION_ENV_NAME).chmod(0o600)
    (env_file.parent / machine.RUNTIME_APPLICATION_PENDING_ENV_NAME).chmod(0o600)
    lock_path = tmp_path / "deploy-state/tokyo-runtime-deploy.lock"
    lock = machine.acquire_deploy_lock(lock_path, require_root_owner=False)
    assert lock is not None
    calls = []

    def stage(**kwargs):
        calls.append("stage")
        release.mkdir(parents=True, exist_ok=True)
        (release / "requirements-runtime.lock").write_text(
            "ccxt==4.5.56 --hash=sha256:" + "a" * 64 + "\n",
            encoding="utf-8",
        )
        return {"status": "candidate_release_staged"}

    monkeypatch.setattr(machine, "stage_candidate_release", stage)
    monkeypatch.setattr(machine, "build_immutable_venv", lambda **kwargs: {"status": "immutable_venv_ready"})
    monkeypatch.setattr(machine, "ensure_previous_release_venv_compatibility", lambda **kwargs: {"status": "previous_release_venv_compatible"})
    monkeypatch.setattr(machine, "install_and_verify_shared_readiness_helper", lambda **kwargs: {"status": "shared_readiness_helper_verified", "readiness_helper_sha256": "1" * 64})
    monkeypatch.setattr(machine, "capture_production_unit_prepolicy", lambda **kwargs: {unit: {"active": False} for unit in machine.PRODUCTION_WRITER_UNITS})
    monkeypatch.setattr(machine, "engage_production_writer_fence", lambda **kwargs: {"status": "production_writers_fenced", "fence_inode": 77})
    monkeypatch.setattr(machine, "verify_runtime_application_role_preflight", lambda **kwargs: {
        "status": "canary_readonly_role_preflight_passed",
        "current_user": "brc_runtime_app",
        "exchange_write_called": False,
    })
    monkeypatch.setattr(machine, "read_candidate_schema_revision", lambda **kwargs: "120")
    migration_env_paths = []

    def migration(**kwargs):
        migration_env_paths.append(kwargs["env_path"])
        return {"status": "schema_migrated", "revision": "124", "lifecycle_capability_was_enabled": False}

    monkeypatch.setattr(machine, "run_fenced_schema_migration", migration)
    monkeypatch.setattr(machine, "install_candidate_units_and_switch_pointer", lambda **kwargs: {"status": "candidate_pointer_active"})
    monkeypatch.setattr(machine, "record_candidate_release_activation", lambda **kwargs: {"status": "runtime_release_activation_completed"})
    monkeypatch.setattr(machine, "refresh_candidate_account_facts", lambda **kwargs: {"status": "candidate_account_facts_refreshed", "fact_snapshot_ids": ("fact:1",)})
    typed_reference = ActionTimeCertificationReferenceV2(
        stage="post_canary",
        target_runtime_head="a" * 40,
        certification_input_digest="sha256:" + "1" * 64,
        release_activation_outcome_id="process:release",
        release_activation_source_watermark="release:watermark",
        lane_source_watermarks=(LaneSourceWatermarkV1(
            lane_scope_key="lane:SOR-001:ETHUSDT:long",
            lane_identity_key="identity:1",
            source_watermark="watermark:1",
            process_outcome_id="process:1",
        ),),
        fact_snapshot_ids=("fact:1",),
        fact_set_digest="sha256:" + "2" * 64,
        fact_min_valid_until_ms=int(machine.time.time() * 1000) + 120_000,
        deploy_nonce="nonce-1",
    )
    monkeypatch.setattr(machine, "certify_candidate_action_time", lambda **kwargs: {
        "status": "action_time_capability_certified",
        "certification_ref": typed_reference.certification_ref(),
        "certification_reference": typed_reference.model_dump(mode="json"),
    })
    monkeypatch.setattr(machine, "publish_candidate_current_projections", lambda **kwargs: {"status": "current_projections_published"})
    sentinel_calls = {"count": 0}

    def sentinel(**kwargs):
        sentinel_calls["count"] += 1
        final = sentinel_calls["count"] == 3
        digest = "sha256:" + ("f" if final else "d") * 64
        return {
            "status": "canary_mutation_sentinel_captured",
            "digest": digest,
            "scope": {"schema_id": "scope"},
            "canary_window_floor_ms": 1000,
            "slice_digests": {"process_current": digest},
            "slice_counts": {"process_current": 1},
        }

    monkeypatch.setattr(machine, "capture_candidate_mutation_sentinel", sentinel)
    monkeypatch.setattr(machine, "run_five_readonly_canaries", lambda **kwargs: {"status": "readonly_canary_complete", "successful_ticks": 5})
    monkeypatch.setattr(machine, "verify_candidate_phase_two_ready", lambda **kwargs: {"status": "phase_two_ready", "exchange_write_called": False})
    monkeypatch.setattr(machine, "collect_activation_machine_facts", lambda **kwargs: {"status": "activation_machine_facts_verified"})
    def restore_policy(**kwargs):
        assert kwargs["enable_after_certification"] is True
        return {"status": "lifecycle_policy_restored", "enabled": True, "lifecycle_proof_ref": "lifecycle-cert:v2:" + "e" * 64, "proof": {}}

    monkeypatch.setattr(machine, "restore_lifecycle_mutation_policy", restore_policy)
    monkeypatch.setattr(machine, "apply_committed_activation", lambda **kwargs: {"status": "activation_applied"})
    config = {
        "transaction_id": "a1b2c3d4",
        "deploy_nonce": "nonce-1",
        "old_sha": "b" * 40,
        "target_sha": "a" * 40,
        "deploy_root": str(deploy_root),
        "repo_url": "https://example.invalid/repo.git",
        "git_ref": "codex/release",
        "release_name": "candidate",
        "previous_release_path": str(previous),
        "legacy_venv_path": str(legacy),
        "env_path": str(env_file),
        "expected_revision": "124",
        "bootstrap_sha256": "c" * 64,
        "enable_lifecycle_mutation_after_certification": True,
        "canonical_lock_path": str(lock_path),
        "require_root_owner": False,
    }
    journal_path = tmp_path / "deploy-state/journal.json"
    try:
        first = machine.execute_deploy_transaction(
            config=config, lock_handle=lock, journal_path=journal_path
        )
        second = machine.execute_deploy_transaction(
            config=config, lock_handle=lock, journal_path=journal_path
        )
    finally:
        lock.close()

    journal = machine.DeployJournal.load(journal_path)
    assert first["status"] == "tokyo_runtime_deploy_applied"
    assert second["status"] == "tokyo_runtime_deploy_applied"
    assert first["lifecycle_policy_enabled"] is True
    assert second["lifecycle_policy_enabled"] is True
    assert [entry["phase"] for entry in journal.entries] == list(machine.DEPLOY_PHASES)
    assert calls == ["stage", "stage", "stage"]
    assert migration_env_paths == [env_file.parent / machine.RUNTIME_MIGRATION_ENV_NAME]
    active_env = env_file.parent / machine.RUNTIME_APPLICATION_ACTIVE_ENV_NAME
    assert active_env.stat().st_mode & 0o777 == 0o600
    active_values = machine.load_runtime_environment(active_env)
    assert active_values["EXCHANGE_API_KEY"] == "test-key"
    assert active_values["PG_DATABASE_URL"] == "postgresql://application.invalid/db"


def test_runtime_application_environment_only_replaces_database_url(tmp_path):
    base = tmp_path / "live.env"
    pending = tmp_path / "application.pending.env"
    active = tmp_path / "application.active.env"
    base.write_text(
        "EXCHANGE_API_KEY='kept-secret'\n"
        "DATABASE_URL='postgresql://old.invalid/legacy'\n"
        "PG_DATABASE_URL='postgresql://old.invalid/db'\n",
        encoding="utf-8",
    )
    pending.write_text(
        "PG_DATABASE_URL='postgresql://app.invalid/db'\n", encoding="utf-8"
    )
    base.chmod(0o600)
    pending.chmod(0o600)

    first = machine.activate_runtime_application_environment(
        base_env_path=base,
        pending_application_env_path=pending,
        active_env_path=active,
    )
    second = machine.activate_runtime_application_environment(
        base_env_path=base,
        pending_application_env_path=pending,
        active_env_path=active,
    )

    values = machine.load_runtime_environment(active)
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert active.stat().st_mode & 0o777 == 0o600
    assert values["EXCHANGE_API_KEY"] == "kept-secret"
    assert values["PG_DATABASE_URL"] == "postgresql://app.invalid/db"
    assert "DATABASE_URL" not in values
    assert "app.invalid" not in str(first)


@pytest.mark.parametrize(
    "candidate_error",
    [
        "ValueError: canary_scope_fact_limit_exceeded",
        "ValueError: canary_scope_signal_limit_exceeded",
        "1 validation error for CanaryMutationSentinelScopeV1 signal_event_ids too_long",
    ],
)
def test_canary_sentinel_retries_legacy_scope_overflow_with_bounded_wrapper(
    tmp_path, candidate_error
):
    release = tmp_path / "release"
    release.mkdir()
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql://example.invalid/db\n")
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            return machine.ChildResult(
                returncode=1,
                stdout="",
                stderr=candidate_error,
            )
        return machine.ChildResult(
            returncode=0,
            stdout=json.dumps({
                "status": "canary_mutation_sentinel_captured",
                "digest": "sha256:" + "a" * 64,
                "scope": {"schema": "brc.canary_mutation_sentinel_scope.v1"},
            }),
            stderr="",
        )

    result = machine.capture_candidate_mutation_sentinel(
        release_path=release,
        env_path=env_file,
        target_sha="a" * 40,
        runner=runner,
        require_root_owner=False,
    )

    assert result["status"] == "canary_mutation_sentinel_captured"
    assert len(calls) == 2
    assert calls[0][1] == "scripts/capture_canary_mutation_sentinel.py"
    assert calls[1][1] == "-c"
    assert "BoundedReferencedSet" in calls[1][2]


def test_canary_sentinel_retries_schema_125_with_in_memory_contract_wrapper(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql://example.invalid/db\n")
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            return machine.ChildResult(
                returncode=1,
                stdout="",
                stderr=(
                    "ValueError: canary_sentinel_storage_schema_mismatch:"
                    "brc_ticket_exit_policy_current"
                ),
            )
        return machine.ChildResult(
            returncode=0,
            stdout=json.dumps({
                "status": "canary_mutation_sentinel_captured",
                "digest": "sha256:" + "a" * 64,
                "scope": {"schema": "brc.canary_mutation_sentinel_scope.v1"},
            }),
            stderr="",
        )

    result = machine.capture_candidate_mutation_sentinel(
        release_path=release,
        env_path=env_file,
        target_sha="a" * 40,
        runner=runner,
        require_root_owner=False,
    )

    assert result["status"] == "canary_mutation_sentinel_captured"
    assert len(calls) == 2
    assert calls[1][1] == "-c"
    assert "binding_source" in calls[1][2]
    assert "adoption_event_id" in calls[1][2]
