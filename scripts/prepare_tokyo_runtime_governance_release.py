#!/usr/bin/env python3
"""Prepare a local dry-run release report for Tokyo runtime governance.

Default behavior is read-only / dry-run: inspect local git facts and print a
deployment-readiness manifest. It does not SSH, deploy, run migrations, read
secrets, place orders, create execution records, call OrderLifecycle, or call
exchange APIs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DEPLOYED_HEAD = "ae9b209e33cd287273491f2e93dfdff3b6a814fd"
DEFAULT_EXPECTED_MIN_MIGRATIONS = 64
DEFAULT_EXPECTED_LATEST_MIGRATION = (
    "2026-06-10-064_add_runtime_profile_proposal_snapshot.py"
)
DEFAULT_OUTPUT_DIR = "output/tokyo-runtime-governance-release"


class ReleaseReadinessError(RuntimeError):
    """Raised when release readiness inspection cannot proceed."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    returncode: int


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root()
    report = build_release_readiness_report(
        repo_root=repo_root,
        deployed_head=args.deployed_head,
        expected_min_migrations=args.expected_min_migrations,
        expected_latest_migration=args.expected_latest_migration,
        write_artifacts=args.write_artifacts,
        output_dir=Path(args.output_dir),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report["release_checks"]["ready_for_packaging"] else 2


def build_release_readiness_report(
    *,
    repo_root: Path,
    deployed_head: str,
    expected_min_migrations: int,
    expected_latest_migration: str,
    write_artifacts: bool,
    output_dir: Path,
) -> dict[str, Any]:
    """Build a local-only readiness manifest for a future Tokyo release."""

    head = _git(repo_root, "rev-parse", "HEAD").stdout
    branch = _git(repo_root, "branch", "--show-current").stdout or "DETACHED"
    short_head = _git(repo_root, "rev-parse", "--short=8", "HEAD").stdout
    tracked_dirty = _tracked_dirty(repo_root)
    untracked = _git_lines(repo_root, "ls-files", "--others", "--exclude-standard")
    deployed_is_ancestor = _is_ancestor(repo_root, deployed_head, "HEAD")
    commits_ahead = (
        int(_git(repo_root, "rev-list", "--count", f"{deployed_head}..HEAD").stdout)
        if deployed_is_ancestor
        else None
    )
    migration_files = sorted(
        path.name for path in (repo_root / "migrations" / "versions").glob("*.py")
    )
    latest_migration = migration_files[-1] if migration_files else None
    tracked_secret_candidates = _tracked_secret_candidates(repo_root)

    blockers: list[str] = []
    warnings: list[str] = []
    if tracked_dirty:
        blockers.append("tracked_worktree_dirty")
    if not deployed_is_ancestor:
        blockers.append("deployed_head_not_ancestor_of_local_head")
    if len(migration_files) < expected_min_migrations:
        blockers.append("local_migration_count_below_expected_minimum")
    if latest_migration != expected_latest_migration:
        blockers.append("latest_migration_does_not_match_expected_stage_head")
    if tracked_secret_candidates:
        blockers.append("tracked_secret_candidate_files_present")
    if untracked:
        warnings.append("untracked_files_exist_and_are_not_in_git_archive")

    artifact_name = (
        f"brc-runtime-governance-{short_head}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    report: dict[str, Any] = {
        "status": "ready_for_local_packaging" if not blockers else "blocked",
        "scope": "tokyo_runtime_governance_release_preparation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "local_git": {
            "branch": branch,
            "head": head,
            "short_head": short_head,
            "tracked_dirty": tracked_dirty,
            "untracked_files": untracked,
        },
        "tokyo_baseline": {
            "deployed_head": deployed_head,
            "deployed_head_is_ancestor": deployed_is_ancestor,
            "commits_ahead_of_deployed": commits_ahead,
        },
        "migrations": {
            "count": len(migration_files),
            "latest": latest_migration,
            "expected_minimum_count": expected_min_migrations,
            "expected_latest": expected_latest_migration,
        },
        "secret_scan": {
            "tracked_secret_candidates": tracked_secret_candidates,
            "note": (
                "This scans tracked path names only. It does not read env files "
                "or secret values."
            ),
        },
        "release_checks": {
            "ready_for_packaging": not blockers,
            "blockers": blockers,
            "warnings": warnings,
        },
        "safety_invariants": {
            "ssh_called": False,
            "remote_files_modified": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "secrets_read": False,
        },
        "artifact_plan": {
            "write_artifacts_requested": write_artifacts,
            "output_dir": str((repo_root / output_dir).resolve()),
            "artifact_name": artifact_name,
            "archive_path": None,
            "manifest_path": None,
        },
    }

    if write_artifacts:
        if blockers:
            raise ReleaseReadinessError(
                "refusing to write release artifacts while readiness blockers exist: "
                + ", ".join(blockers)
            )
        artifact_dir = repo_root / output_dir / artifact_name
        artifact_dir.mkdir(parents=True, exist_ok=False)
        archive_path = artifact_dir / f"{artifact_name}.tar.gz"
        manifest_path = artifact_dir / "release-readiness-manifest.json"
        _git(
            repo_root,
            "archive",
            "--format=tar.gz",
            f"--prefix={artifact_name}/",
            "-o",
            str(archive_path),
            "HEAD",
        )
        report["artifact_plan"]["archive_path"] = str(archive_path)
        report["artifact_plan"]["manifest_path"] = str(manifest_path)
        manifest_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    return report


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect local git/migration facts and optionally create a local "
            "git-archive release artifact for a future Tokyo deployment."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--deployed-head",
        default=DEFAULT_DEPLOYED_HEAD,
        help="Tokyo deployed commit expected to be an ancestor of local HEAD.",
    )
    parser.add_argument(
        "--expected-min-migrations",
        type=int,
        default=DEFAULT_EXPECTED_MIN_MIGRATIONS,
        help="Minimum migration-file count expected for this release stage.",
    )
    parser.add_argument(
        "--expected-latest-migration",
        default=DEFAULT_EXPECTED_LATEST_MIGRATION,
        help="Latest migration filename expected for this release stage.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Local output directory used only with --write-artifacts.",
    )
    parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help=(
            "Write a local git archive and manifest. This never deploys or "
            "modifies remote state."
        ),
    )
    return parser.parse_args(argv)


def _repo_root() -> Path:
    result = _run(("git", "rev-parse", "--show-toplevel"), cwd=Path.cwd())
    if result.returncode != 0 or not result.stdout:
        raise ReleaseReadinessError("not inside a git repository")
    return Path(result.stdout)


def _git(repo_root: Path, *args: str) -> CommandResult:
    result = _run(("git", *args), cwd=repo_root)
    if result.returncode != 0:
        raise ReleaseReadinessError(f"git {' '.join(args)} failed")
    return result


def _git_lines(repo_root: Path, *args: str) -> list[str]:
    stdout = _git(repo_root, *args).stdout
    return [line for line in stdout.splitlines() if line]


def _run(command: tuple[str, ...], *, cwd: Path) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = completed.stdout.strip()
    if completed.returncode != 0 and completed.stderr.strip():
        stdout = completed.stderr.strip()
    return CommandResult(stdout=stdout, returncode=completed.returncode)


def _tracked_dirty(repo_root: Path) -> bool:
    return (
        _run(("git", "diff", "--quiet"), cwd=repo_root).returncode != 0
        or _run(("git", "diff", "--cached", "--quiet"), cwd=repo_root).returncode
        != 0
    )


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    return (
        _run(("git", "merge-base", "--is-ancestor", ancestor, descendant), cwd=repo_root)
        .returncode
        == 0
    )


def _tracked_secret_candidates(repo_root: Path) -> list[str]:
    candidates: list[str] = []
    for path in _git_lines(repo_root, "ls-files"):
        lowered = path.lower()
        name = Path(path).name.lower()
        if name.endswith(".example") or ".example." in lowered:
            continue
        if lowered in {".env", ".env.local", ".env.production"}:
            candidates.append(path)
            continue
        if lowered.startswith("env/") and lowered.endswith(".env"):
            candidates.append(path)
            continue
        if any(token in lowered for token in ("/secrets/", "secret")):
            candidates.append(path)
            continue
        if any(name.endswith(suffix) for suffix in (".pem", ".key", ".p12")):
            candidates.append(path)
    return sorted(dict.fromkeys(candidates))


def _print_human_report(report: dict[str, Any]) -> None:
    checks = report["release_checks"]
    local_git = report["local_git"]
    migrations = report["migrations"]
    tokyo = report["tokyo_baseline"]
    print(f"status={report['status']}")
    print(f"branch={local_git['branch']}")
    print(f"head={local_git['head']}")
    print(f"deployed_head_is_ancestor={tokyo['deployed_head_is_ancestor']}")
    print(f"commits_ahead_of_deployed={tokyo['commits_ahead_of_deployed']}")
    print(f"migration_count={migrations['count']}")
    print(f"latest_migration={migrations['latest']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))
    print("ready_for_packaging=" + str(checks["ready_for_packaging"]).lower())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseReadinessError as exc:
        print(f"release_readiness_error={exc}", file=sys.stderr)
        raise SystemExit(2)
