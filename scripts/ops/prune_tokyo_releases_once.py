#!/usr/bin/env python3
"""One-shot Tokyo release directory pruning helper."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4


SCHEMA = "brc.ops.tokyo_release_prune_once.v1"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    current_symlink = Path(args.current_symlink).expanduser().resolve()
    manifest = build_manifest(
        root=root,
        current_symlink=current_symlink,
        keep_count=args.keep_count,
        max_delete_count=args.max_delete_count,
        apply=args.apply,
    )
    if args.apply:
        apply_prune(manifest, root=root, max_delete_count=args.max_delete_count)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if not manifest["checks"]["blockers"] else 2


def build_manifest(
    *,
    root: Path,
    current_symlink: Path,
    keep_count: int,
    max_delete_count: int = 2,
    apply: bool = False,
) -> dict[str, Any]:
    blockers: list[str] = []
    if keep_count < 3:
        blockers.append("keep_count_must_be_at_least_3")
    if max_delete_count < 1:
        blockers.append("max_delete_count_must_be_positive")
    if not root.exists() or not root.is_dir():
        blockers.append("release_root_missing")
    if not current_symlink.exists():
        blockers.append("current_symlink_missing")
    current = current_symlink.resolve() if current_symlink.exists() else None
    if current and not _is_within(root, current):
        blockers.append("current_release_not_under_release_root")

    releases: list[Path] = []
    if not blockers:
        releases = [
            path
            for path in root.iterdir()
            if path.is_dir()
            and not path.is_symlink()
            and path.name.startswith("brc-runtime-governance-")
        ]
        releases.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    protected: set[Path] = set()
    if current:
        protected.add(current)
    for release in releases[:keep_count]:
        protected.add(release)
    if current in releases:
        index = releases.index(current)
        if index + 1 < len(releases):
            protected.add(releases[index + 1])

    delete_candidates = [
        _entry(path, root, "delete_candidate")
        for path in releases
        if path not in protected
    ]
    protected_entries = [
        _entry(path, root, "protected_current_or_recent")
        for path in releases
        if path in protected
    ]
    return {
        "schema": SCHEMA,
        "status": "blocked" if blockers else ("apply_ready" if apply else "dry_run"),
        "mode": "apply" if apply else "dry_run",
        "run_id": f"release-prune:{uuid4().hex[:12]}",
        "root": str(root),
        "current_symlink": str(current_symlink),
        "current_release": str(current) if current else None,
        "keep_count": keep_count,
        "max_delete_count": max_delete_count,
        "delete_candidates": delete_candidates,
        "protected_entries": protected_entries,
        "candidate_count": len(delete_candidates),
        "checks": {
            "blockers": blockers,
            "no_pg_runtime_truth_write": True,
            "no_trade_runtime_mutation": True,
        },
    }


def apply_prune(
    manifest: dict[str, Any],
    *,
    root: Path,
    max_delete_count: int | None = None,
) -> None:
    if manifest.get("checks", {}).get("blockers"):
        return
    deleted: list[str] = []
    candidates = manifest.get("delete_candidates") or []
    delete_budget = max_delete_count if max_delete_count is not None else len(candidates)
    for row in candidates[:delete_budget]:
        path = (root / row["relative_path"]).resolve()
        if path.exists() and path.is_dir() and not path.is_symlink() and _is_within(root, path):
            shutil.rmtree(path)
            deleted.append(row["relative_path"])
    if len(candidates) > delete_budget:
        manifest["checks"].setdefault("warnings", []).append("delete_budget_exhausted")
    manifest["deleted_count"] = len(deleted)
    manifest["deleted_relative_paths"] = deleted
    manifest["status"] = "applied"


def _entry(path: Path, root: Path, status: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "relative_path": str(path.resolve().relative_to(root)),
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "status": status,
    }


def _is_within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=False)
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--root", default="/home/ubuntu/brc-deploy/releases")
    parser.add_argument("--current-symlink", default="/home/ubuntu/brc-deploy/app/current")
    parser.add_argument("--keep-count", type=int, default=5)
    parser.add_argument("--max-delete-count", type=int, default=2)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
