#!/usr/bin/env python3
"""Validate production runtime avoids file authority and generated report writes."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DISPATCHER_DROPIN = (
    REPO_ROOT
    / "deploy/systemd/brc-runtime-signal-watcher.service.d/"
    "90-resume-dispatcher-after-refresh.conf"
)
PRODUCT_STATE_DROPIN = (
    REPO_ROOT
    / "deploy/systemd/brc-runtime-signal-watcher.service.d/"
    "80-product-state-refresh.conf"
)
ACTION_TIME_DROPIN = (
    REPO_ROOT
    / "deploy/systemd/brc-runtime-signal-watcher.service.d/"
    "85-action-time-refresh-if-needed.conf"
)
WATCHER_DROPIN_DIR = REPO_ROOT / "deploy/systemd/brc-runtime-signal-watcher.service.d"
STRICT_AUDIT_RISK_FLAGS = (
    "blocking_cleanup_required",
    "file_artifact_cli_interface",
    "frequent_report_write",
    "generated_file_write",
    "legacy_artifact_file_io",
    "owner_explanation_file_source",
    "runtime_file_read",
    "runtime_file_write",
    "suspicious_runtime_file_authority",
    "unbounded_destructive_file_mutation",
)


def validate_no_runtime_file_authority(
    *,
    repo_root: Path = REPO_ROOT,
    include_transitive_audit: bool = True,
) -> list[str]:
    errors: list[str] = []
    dropin_dir = repo_root / WATCHER_DROPIN_DIR.relative_to(REPO_ROOT)
    dropins = {
        path.relative_to(repo_root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(dropin_dir.glob("*.conf"))
    }
    dispatcher = _required_text(dropins, DISPATCHER_DROPIN.relative_to(REPO_ROOT))
    product_state = _required_text(dropins, PRODUCT_STATE_DROPIN.relative_to(REPO_ROOT))
    action_time = _required_text(dropins, ACTION_TIME_DROPIN.relative_to(REPO_ROOT))
    if "--identity-source pg_ticket" not in dispatcher:
        errors.append("runtime dispatcher production drop-in must use pg_ticket identity")
    if "--resume-pack-json" in dispatcher:
        errors.append("runtime dispatcher production drop-in must not pass --resume-pack-json")
    if "--mode watcher_tick_summary" not in product_state:
        errors.append("watcher product-state post-step must use watcher_tick_summary")
    if "--mode action_time_if_needed" not in action_time:
        errors.append("watcher action-time post-step must use action_time_if_needed")
    forbidden_production_inputs = (
        "--candidate-pool-json",
        "--daily-table-json",
        "--goal-status-json",
        "--live-facts-json",
        "--runtime-active-monitor-json",
        "--resume-pack-json",
        "--output-json",
        "--output-owner-progress",
        "--report-dir",
        "--runtime-monitor-dir",
        "runtime_dry_run_audit_chain.py",
        "runtime-dry-run-audit-chain.json",
        "--mode control_refresh",
        "--mode diagnostic_full",
    )
    for token in forbidden_production_inputs:
        for rel_path, text in dropins.items():
            if token in text:
                errors.append(f"{rel_path} contains forbidden production runtime token: {token}")
    if include_transitive_audit:
        errors.extend(_production_file_io_audit_errors(repo_root=repo_root))
    return errors


def _production_file_io_audit_errors(*, repo_root: Path) -> list[str]:
    from scripts import audit_production_runtime_file_io as file_io_audit

    targets = list(file_io_audit.DEFAULT_TARGETS) + list(
        file_io_audit.DEFAULT_EXTRA_TARGETS
    )
    occurrences = file_io_audit.audit_targets(repo_root=repo_root, targets=targets)
    risk_counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {flag: [] for flag in STRICT_AUDIT_RISK_FLAGS}
    for item in occurrences:
        for flag in item.risk_flags:
            if flag not in STRICT_AUDIT_RISK_FLAGS:
                continue
            risk_counts[flag] += 1
            if len(examples[flag]) < 5:
                examples[flag].append(
                    f"{item.path}:{item.line}:{item.operation}:{item.api}"
                )

    errors: list[str] = []
    for flag in STRICT_AUDIT_RISK_FLAGS:
        count = risk_counts.get(flag, 0)
        if not count:
            continue
        sample = ", ".join(examples[flag])
        errors.append(
            f"production runtime file I/O audit found {flag}={count}; examples={sample}"
        )
    return errors


def _required_text(dropins: dict[str, str], rel_path: Path) -> str:
    return dropins.get(rel_path.as_posix(), "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--dropins-only",
        action="store_true",
        help="Check only legacy drop-in tokens. Normal validation also audits production code paths.",
    )
    args = parser.parse_args(argv)

    errors = validate_no_runtime_file_authority(
        repo_root=args.repo_root,
        include_transitive_audit=not args.dropins_only,
    )
    report: dict[str, Any] = {
        "status": "no_runtime_file_authority_valid" if not errors else "blocked",
        "errors": errors,
        "checked_files": [
            str(path)
            for path in sorted(
                path.relative_to(REPO_ROOT)
                for path in WATCHER_DROPIN_DIR.glob("*.conf")
            )
        ],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print(report["status"])
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
