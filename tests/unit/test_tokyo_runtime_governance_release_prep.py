from __future__ import annotations

import importlib.util
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prepare_tokyo_runtime_governance_release.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_tokyo_runtime_governance_release",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _init_release_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "release-repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "codex@example.test")
    _run_git(repo, "config", "user.name", "Codex Test")
    _write(repo / "README.md", "baseline\n")
    _write(
        repo
        / "migrations"
        / "versions"
        / "2026-06-10-064_add_runtime_profile_proposal_snapshot.py",
        "revision = '064'\ndown_revision = '063'\n",
    )
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "baseline deployed release")
    deployed_head = _run_git(repo, "rev-parse", "HEAD")
    _write(repo / "README.md", "baseline\nruntime governance changes\n")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "runtime governance changes")
    return repo, deployed_head


def test_release_readiness_report_passes_for_clean_ancestor_release(tmp_path: Path):
    module = _load_module()
    repo, deployed_head = _init_release_repo(tmp_path)

    report = module.build_release_readiness_report(
        repo_root=repo,
        deployed_head=deployed_head,
        expected_min_migrations=1,
        expected_latest_migration=(
            "2026-06-10-064_add_runtime_profile_proposal_snapshot.py"
        ),
        write_artifacts=False,
        output_dir=Path("output/release-check"),
    )

    assert report["status"] == "ready_for_local_packaging"
    assert report["release_checks"]["ready_for_packaging"] is True
    assert report["release_checks"]["blockers"] == []
    assert report["tokyo_baseline"]["deployed_head_is_ancestor"] is True
    assert report["tokyo_baseline"]["commits_ahead_of_deployed"] == 1
    assert report["migrations"]["count"] == 1
    assert report["migrations"]["latest"] == (
        "2026-06-10-064_add_runtime_profile_proposal_snapshot.py"
    )
    assert all(value is False for value in report["safety_invariants"].values())
    assert report["artifact_plan"]["archive_path"] is None
    assert report["secret_scan"]["tracked_secret_candidates"] == []


def test_release_readiness_blocks_dirty_tracked_tree_and_refuses_artifacts(
    tmp_path: Path,
):
    module = _load_module()
    repo, deployed_head = _init_release_repo(tmp_path)
    _write(repo / "README.md", "dirty tracked change\n")

    report = module.build_release_readiness_report(
        repo_root=repo,
        deployed_head=deployed_head,
        expected_min_migrations=1,
        expected_latest_migration=(
            "2026-06-10-064_add_runtime_profile_proposal_snapshot.py"
        ),
        write_artifacts=False,
        output_dir=Path("output/release-check"),
    )

    assert report["status"] == "blocked"
    assert report["release_checks"]["ready_for_packaging"] is False
    assert "tracked_worktree_dirty" in report["release_checks"]["blockers"]

    with pytest.raises(module.ReleaseReadinessError, match="tracked_worktree_dirty"):
        module.build_release_readiness_report(
            repo_root=repo,
            deployed_head=deployed_head,
            expected_min_migrations=1,
            expected_latest_migration=(
                "2026-06-10-064_add_runtime_profile_proposal_snapshot.py"
            ),
            write_artifacts=True,
            output_dir=Path("output/release-check"),
        )


def test_release_artifact_uses_git_archive_and_excludes_untracked_files(
    tmp_path: Path,
):
    module = _load_module()
    repo, deployed_head = _init_release_repo(tmp_path)
    _write(repo / "untracked-secret.env", "SECRET=not-in-archive\n")

    report = module.build_release_readiness_report(
        repo_root=repo,
        deployed_head=deployed_head,
        expected_min_migrations=1,
        expected_latest_migration=(
            "2026-06-10-064_add_runtime_profile_proposal_snapshot.py"
        ),
        write_artifacts=True,
        output_dir=Path("output/release-check"),
    )

    assert report["release_checks"]["ready_for_packaging"] is True
    assert report["release_checks"]["blockers"] == []
    assert report["release_checks"]["warnings"] == [
        "untracked_files_exist_and_are_not_in_git_archive"
    ]
    archive_path = Path(report["artifact_plan"]["archive_path"])
    manifest_path = Path(report["artifact_plan"]["manifest_path"])
    assert archive_path.exists()
    assert manifest_path.exists()

    with tarfile.open(archive_path, "r:gz") as archive:
        names = archive.getnames()
    assert any(name.endswith("/README.md") for name in names)
    assert not any("untracked-secret.env" in name for name in names)
    assert all(value is False for value in report["safety_invariants"].values())
