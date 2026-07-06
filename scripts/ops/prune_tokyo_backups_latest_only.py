#!/usr/bin/env python3
"""One-shot Tokyo backup pruning helper that keeps only the newest backup."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


SCHEMA = "brc.ops.tokyo_backup_latest_only_prune_once.v1"
BACKUP_SUFFIXES = (".pgdump", ".dump", ".backup", ".sql.gz")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    manifest = build_manifest(
        root=root,
        apply=args.apply,
        max_delete_count=args.max_delete_count,
    )
    if args.apply:
        apply_prune(manifest, root=root, max_delete_count=args.max_delete_count)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if not manifest["checks"]["blockers"] else 2


def build_manifest(*, root: Path, apply: bool, max_delete_count: int = 100) -> dict[str, Any]:
    blockers: list[str] = []
    if not root.exists() or not root.is_dir():
        blockers.append("backup_root_missing")
    if max_delete_count < 1:
        blockers.append("max_delete_count_must_be_positive")
    backups: list[Path] = []
    if not blockers:
        backups = [
            path
            for path in root.iterdir()
            if path.is_file() and not path.is_symlink() and path.name.endswith(BACKUP_SUFFIXES)
        ]
        backups.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    protected = backups[:1]
    delete_candidates = backups[1:]
    return {
        "schema": SCHEMA,
        "status": "blocked" if blockers else ("apply_ready" if apply else "dry_run"),
        "mode": "apply" if apply else "dry_run",
        "run_id": f"backup-prune:{uuid4().hex[:12]}",
        "root": str(root),
        "max_delete_count": max_delete_count,
        "protected_entries": [_entry(path, root, "protected_latest_backup") for path in protected],
        "delete_candidates": [_entry(path, root, "delete_candidate") for path in delete_candidates],
        "candidate_count": len(delete_candidates),
        "checks": {
            "blockers": blockers,
            "no_new_backup_created": True,
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
        if path.exists() and path.is_file() and not path.is_symlink() and _is_within(root, path):
            path.unlink()
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
        "bytes": stat.st_size,
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
    parser.add_argument("--root", default="/home/ubuntu/brc-deploy/backups")
    parser.add_argument("--max-delete-count", type=int, default=100)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
