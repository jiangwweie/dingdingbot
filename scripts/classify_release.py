#!/usr/bin/env python3
"""Classify one committed change set into the M0.5 R0-R4 release model."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]


class ReleaseLevel(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


@dataclass(frozen=True)
class ReleaseClassification:
    level: ReleaseLevel
    changed_paths: tuple[str, ...]
    requires_flat: bool
    requires_kernel_certification: bool
    affected_services: tuple[str, ...]
    primary_blocker: str | None


_LEVEL_ORDER = {
    ReleaseLevel.R0: 0,
    ReleaseLevel.R1: 1,
    ReleaseLevel.R2: 2,
    ReleaseLevel.R3: 3,
    ReleaseLevel.R4: 4,
}

_AUTHORITY_FILES = frozenset(
    {
        "src/trading_kernel/domain/strategy_registry.py",
        "src/trading_kernel/infrastructure/runtime_authority_seed.py",
        "src/trading_kernel/infrastructure/runtime_identity.py",
    }
)
_OWNER_API_FILES = frozenset(
    {
        "requirements-owner-console.txt",
        "scripts/owner_console/run_api.py",
        "src/trading_kernel/infrastructure/owner_market_data.py",
        "src/trading_kernel/infrastructure/pg_owner_control.py",
        "src/trading_kernel/infrastructure/pg_owner_read_repository.py",
    }
)
_LOCAL_RELEASE_TOOLS = frozenset(
    {
        "scripts/classify_release.py",
        "scripts/owner_console/certify_release_candidate.py",
        "scripts/owner_console/certify_static_release_candidate.py",
        "scripts/owner_console/deploy_release.py",
        "scripts/release_control.py",
        "scripts/trading_kernel/certify_release_candidate.py",
        "scripts/trading_kernel/deploy_tokyo_release.py",
        "scripts/trading_kernel/verification_portfolios.py",
    }
)
_R0_ROOT_FILES = frozenset(
    {
        ".gitignore",
        "AGENTS.md",
        "CLAUDE.md",
        "MEMORY.md",
        "README.md",
        "pytest.ini",
    }
)


def classify_changed_paths(paths: tuple[str, ...]) -> ReleaseClassification:
    normalized = tuple(sorted({_normalize_path(path) for path in paths if path.strip()}))
    levels = tuple(_classify_path(path) for path in normalized)
    level = max(levels, key=_LEVEL_ORDER.__getitem__) if levels else ReleaseLevel.R0
    return ReleaseClassification(
        level=level,
        changed_paths=normalized,
        requires_flat=level in {ReleaseLevel.R3, ReleaseLevel.R4},
        requires_kernel_certification=level in {ReleaseLevel.R3, ReleaseLevel.R4},
        affected_services=_affected_services(level),
        primary_blocker=_primary_blocker(level),
    )


def changed_paths_between(base: str, target: str) -> tuple[str, ...]:
    result = subprocess.run(
        (
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            "-z",
            base,
            target,
        ),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return tuple(
        path.decode("utf-8")
        for path in result.stdout.split(b"\0")
        if path
    )


def _classify_path(path: str) -> ReleaseLevel:
    if _is_authority_path(path):
        return ReleaseLevel.R4
    if is_owner_api_path(path):
        return ReleaseLevel.R2
    if is_owner_static_path(path):
        return ReleaseLevel.R1
    if _is_non_runtime_path(path):
        return ReleaseLevel.R0
    return ReleaseLevel.R3


def _is_authority_path(path: str) -> bool:
    return (
        path.startswith(
            ("migrations/trading_kernel/", "deploy/owner-console/postgresql/")
        )
        or path in _AUTHORITY_FILES
    )


def is_owner_static_path(path: str) -> bool:
    return path.startswith("frontend/owner-console/")


def is_owner_api_path(path: str) -> bool:
    return (
        path.startswith(
            (
                "src/trading_kernel/application/owner_console/",
                "src/trading_kernel/interfaces/owner_console_http/",
                "deploy/owner-console/nginx/",
                "deploy/owner-console/systemd/",
            )
        )
        or path in _OWNER_API_FILES
    )


def _is_non_runtime_path(path: str) -> bool:
    return (
        path.startswith(("docs/", "tests/", ".agents/", ".github/"))
        or path in _LOCAL_RELEASE_TOOLS
        or path in _R0_ROOT_FILES
        or PurePosixPath(path).suffix.lower() == ".md"
    )


def _affected_services(level: ReleaseLevel) -> tuple[str, ...]:
    return {
        ReleaseLevel.R0: (),
        ReleaseLevel.R1: ("nginx-static-symlink",),
        ReleaseLevel.R2: ("brc-owner-console-api.service",),
        ReleaseLevel.R3: (
            "brc-trading-kernel-observation-worker.service",
            "brc-trading-kernel-entry-worker.service",
            "brc-trading-kernel-lifecycle-worker.service",
            "brc-trading-kernel-reconciliation-worker.service",
        ),
        ReleaseLevel.R4: (
            "postgresql-authority",
            "brc-trading-kernel-observation-worker.service",
            "brc-trading-kernel-entry-worker.service",
            "brc-trading-kernel-lifecycle-worker.service",
            "brc-trading-kernel-reconciliation-worker.service",
        ),
    }[level]


def _primary_blocker(level: ReleaseLevel) -> str | None:
    return {
        ReleaseLevel.R0: None,
        ReleaseLevel.R1: "frontend_build",
        ReleaseLevel.R2: "owner_api_compatibility",
        ReleaseLevel.R3: "internal_external_flatness",
        ReleaseLevel.R4: "stopped_flat_forward_upgrade",
    }[level]


def _normalize_path(path: str) -> str:
    normalized = PurePosixPath(path.strip()).as_posix()
    if normalized.startswith(("../", "/")):
        raise ValueError("changed path must stay inside the repository")
    return normalized


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base commit or tag.")
    parser.add_argument("--target", default="HEAD", help="Target commit; defaults to HEAD.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = classify_changed_paths(changed_paths_between(args.base, args.target))
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
