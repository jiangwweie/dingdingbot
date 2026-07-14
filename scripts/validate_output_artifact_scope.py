#!/usr/bin/env python3
"""Validate routine commits do not include generated output artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        default=[],
        help="Changed output path to validate. May be passed more than once.",
    )
    parser.add_argument(
        "--git-status",
        action="store_true",
        help="Validate changed output paths reported by git status --porcelain.",
    )
    parser.add_argument(
        "--git-tracked",
        action="store_true",
        help="Validate tracked output paths reported by git ls-files.",
    )
    args = parser.parse_args(argv)

    paths = list(args.paths)
    if args.git_status:
        paths.extend(_git_changed_output_paths(REPO_ROOT))
    errors = validate_changed_output_paths(paths)
    if args.git_tracked:
        errors.extend(
            validate_tracked_output_paths(
                _git_tracked_output_paths(REPO_ROOT),
                repo_root=REPO_ROOT,
            )
        )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "output_artifact_scope_valid",
                "checked_path_count": len(set(paths)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def validate_changed_output_paths(paths: list[str]) -> list[str]:
    errors: list[str] = []
    for path in sorted(set(_normalize_path(path) for path in paths)):
        if not path or not path.startswith("output/"):
            continue
        errors.append(
            f"{path} is generated output; do not include output/** in routine commits"
        )
    return errors


def validate_tracked_output_paths(
    paths: list[str],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    errors: list[str] = []
    for path in sorted(set(_normalize_path(path) for path in paths)):
        if not path or not path.startswith("output/"):
            continue
        if not (repo_root / path).exists():
            continue
        errors.append(f"{path} is tracked generated output; remove it from git")
    return errors


def _git_changed_output_paths(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "output"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    return _changed_output_paths_from_porcelain(result.stdout)


def _git_tracked_output_paths(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "output"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _changed_output_paths_from_porcelain(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        status = line[:2]
        if "D" in status:
            continue
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        paths.append(raw_path.strip())
    return paths


def _normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
