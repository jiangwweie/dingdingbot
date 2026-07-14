#!/usr/bin/env python3
"""One-shot Tokyo runtime report cleanup helper.

This is an ops tool, not a runtime authority path. It only scans an allowlisted
reports tree, defaults to dry-run, and never reads or writes PG runtime truth.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any
from uuid import uuid4


SCHEMA = "brc.ops.runtime_reports_cleanup_once.v1"
DEFAULT_RUNTIME_REPORT_DIR = "runtime-signal-watcher"
DELETE_TOKENS = ("dry-run", "dry_run", "replay", "debug", "history")
PROTECT_TOKENS = ("latest", "current")
PROTECTED_NAMES = {
    "strategygroup-runtime-goal-status.json",
    "server-product-state-refresh-sequence.json",
    "resume-dispatch-artifact.json",
}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.apply and args.dry_run:
        raise SystemExit("--apply and --dry-run are mutually exclusive")
    root = Path(args.root).expanduser().resolve()
    target = (root / DEFAULT_RUNTIME_REPORT_DIR).resolve()
    now = args.now or datetime.now(timezone.utc).timestamp()
    manifest = build_manifest(
        root=root,
        target=target,
        keep_hours=args.keep_hours,
        now=now,
        apply=args.apply,
        max_scan_seconds=args.max_scan_seconds,
        max_candidates=args.max_candidates,
        max_delete_count=args.max_delete_count,
    )
    if args.apply:
        apply_cleanup(
            manifest,
            root=root,
            max_delete_count=args.max_delete_count,
        )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if not manifest["checks"]["blockers"] else 2


def build_manifest(
    *,
    root: Path,
    target: Path,
    keep_hours: int,
    now: float,
    apply: bool,
    max_scan_seconds: float = 10.0,
    max_candidates: int = 2000,
    max_delete_count: int = 1000,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if keep_hours < 1:
        blockers.append("keep_hours_must_be_positive")
    if max_scan_seconds <= 0:
        blockers.append("max_scan_seconds_must_be_positive")
    if max_candidates < 1:
        blockers.append("max_candidates_must_be_positive")
    if max_delete_count < 1:
        blockers.append("max_delete_count_must_be_positive")
    if not _is_within(root, target):
        blockers.append("target_not_under_root")
    if not target.exists():
        blockers.append("runtime_signal_watcher_reports_dir_missing")
    if target.is_symlink():
        blockers.append("target_must_not_be_symlink")

    candidates: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    if not blockers:
        cutoff = now - keep_hours * 3600
        scan_started = time.monotonic()
        for path in target.rglob("*"):
            if time.monotonic() - scan_started > max_scan_seconds:
                warnings.append("scan_budget_exhausted")
                break
            if len(candidates) >= max_candidates:
                warnings.append("candidate_budget_exhausted")
                break
            if path.is_symlink():
                protected.append(_entry(path, root, "protected_symlink"))
                continue
            if path.is_dir():
                continue
            if _is_protected_runtime_export(path):
                protected.append(_entry(path, root, "protected_latest_or_current"))
                continue
            if not _is_cleanup_candidate(path.relative_to(target)):
                continue
            mtime = path.stat().st_mtime
            if mtime >= cutoff:
                protected.append(_entry(path, root, "protected_recent"))
                continue
            candidates.append(_entry(path, root, "delete_candidate"))

    run_id = f"runtime-report-cleanup:{uuid4().hex[:12]}"
    return {
        "schema": SCHEMA,
        "status": "blocked" if blockers else ("apply_ready" if apply else "dry_run"),
        "mode": "apply" if apply else "dry_run",
        "run_id": run_id,
        "root": str(root),
        "target": str(target),
        "keep_hours": keep_hours,
        "max_scan_seconds": max_scan_seconds,
        "max_candidates": max_candidates,
        "max_delete_count": max_delete_count,
        "candidate_count": len(candidates),
        "protected_count": len(protected),
        "delete_candidates": candidates,
        "protected_entries": protected,
        "checks": {
            "blockers": blockers,
            "warnings": warnings,
            "no_pg_runtime_truth_write": True,
            "no_trade_runtime_mutation": True,
        },
    }


def apply_cleanup(
    manifest: dict[str, Any],
    *,
    root: Path,
    max_delete_count: int | None = None,
) -> None:
    blockers = manifest.get("checks", {}).get("blockers") or []
    if blockers:
        return
    candidates = manifest.get("delete_candidates") or []
    deleted: list[str] = []
    delete_budget = max_delete_count if max_delete_count is not None else len(candidates)
    for row in candidates[:delete_budget]:
        path = (root / row["relative_path"]).resolve()
        if path.exists() and _is_within(root, path) and not path.is_symlink():
            path.unlink()
            deleted.append(row["relative_path"])
    if len(candidates) > delete_budget:
        manifest["checks"]["warnings"].append("delete_budget_exhausted")
    _remove_empty_dirs((root / DEFAULT_RUNTIME_REPORT_DIR).resolve(), root=root)
    manifest["deleted_count"] = len(deleted)
    manifest["deleted_relative_paths"] = deleted
    manifest["status"] = "applied"


def _is_cleanup_candidate(path: Path) -> bool:
    rel = path.as_posix().lower()
    return any(token in rel for token in DELETE_TOKENS)


def _is_protected_runtime_export(path: Path) -> bool:
    name = path.name.lower()
    if name in PROTECTED_NAMES:
        return True
    return any(token in name for token in PROTECT_TOKENS)


def _entry(path: Path, root: Path, status: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "relative_path": str(path.resolve().relative_to(root)),
        "bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "status": status,
    }


def _remove_empty_dirs(path: Path, *, root: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_dir() and _is_within(root, child):
            try:
                child.rmdir()
            except OSError:
                pass


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
    parser.add_argument("--root", default="/home/ubuntu/brc-deploy/reports")
    parser.add_argument("--keep-hours", type=int, default=72)
    parser.add_argument("--now", type=float)
    parser.add_argument("--max-scan-seconds", type=float, default=10.0)
    parser.add_argument("--max-candidates", type=int, default=2000)
    parser.add_argument("--max-delete-count", type=int, default=1000)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
