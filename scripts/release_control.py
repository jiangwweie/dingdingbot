"""Plan one exact R0-R4 release without mutating a deployment target."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.classify_release import (
    ReleaseClassification,
    ReleaseLevel,
    changed_paths_between,
    classify_changed_paths,
    is_owner_api_path,
    is_owner_static_path,
)
from scripts.owner_console.certify_release_candidate import (
    validate_owner_api_release_certification,
)
from scripts.owner_console.certify_static_release_candidate import (
    validate_owner_static_release_certification,
)
from scripts.trading_kernel.certify_release_candidate import (
    ReleaseCertificationLevel,
    validate_release_certification_for_level,
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class CertificationRequirement(StrEnum):
    NONE = "none"
    OWNER_STATIC = "owner_static"
    OWNER_API = "owner_api"
    KERNEL_R3 = "kernel_r3"
    KERNEL_R4 = "kernel_r4"


class ReleaseStage(StrEnum):
    ORIENT = "orient"
    PREPARE = "prepare"
    SWITCH = "switch"
    VERIFY = "verify"
    ACTIVATE = "activate"
    SEAL = "seal"


@dataclass(frozen=True)
class ReleaseControlPlan:
    base_commit: str
    target_commit: str
    release_level: ReleaseLevel
    changed_paths: tuple[str, ...]
    certification_requirements: tuple[CertificationRequirement, ...]
    affected_services: tuple[str, ...]
    requires_flat: bool
    stages: tuple[ReleaseStage, ...]
    current_stage: ReleaseStage
    primary_blocker: str | None


def certification_requirements_for(
    classification: ReleaseClassification,
) -> tuple[CertificationRequirement, ...]:
    """Require one exact manifest for every deployment plane in the candidate."""

    requirements: list[CertificationRequirement] = []
    if any(is_owner_static_path(path) for path in classification.changed_paths):
        requirements.append(CertificationRequirement.OWNER_STATIC)
    if any(is_owner_api_path(path) for path in classification.changed_paths):
        requirements.append(CertificationRequirement.OWNER_API)
    if classification.level is ReleaseLevel.R3:
        requirements.append(CertificationRequirement.KERNEL_R3)
    elif classification.level is ReleaseLevel.R4:
        requirements.append(CertificationRequirement.KERNEL_R4)
    return tuple(requirements)


def affected_services_for(classification: ReleaseClassification) -> tuple[str, ...]:
    """Return every affected deployment target, not only the heaviest release."""

    services: list[str] = []
    if any(is_owner_static_path(path) for path in classification.changed_paths):
        services.append("nginx-static-symlink")
    if any(is_owner_api_path(path) for path in classification.changed_paths):
        services.append("brc-owner-console-api.service")
    services.extend(classification.affected_services)
    return tuple(dict.fromkeys(services))


def build_release_control_plan(
    *,
    base_commit: str,
    target_commit: str,
    classification: ReleaseClassification,
    certification_ready: bool,
) -> ReleaseControlPlan:
    _require_commit(base_commit, label="base")
    _require_commit(target_commit, label="target")
    requirements = certification_requirements_for(classification)
    needs_certification = bool(requirements)
    current_stage = (
        ReleaseStage.SEAL
        if not needs_certification
        else ReleaseStage.SWITCH
        if certification_ready
        else ReleaseStage.PREPARE
    )
    primary_blocker = (
        None
        if current_stage is ReleaseStage.SEAL
        else classification.primary_blocker
        if current_stage is ReleaseStage.SWITCH
        else "certification_required"
    )
    return ReleaseControlPlan(
        base_commit=base_commit,
        target_commit=target_commit,
        release_level=classification.level,
        changed_paths=classification.changed_paths,
        certification_requirements=requirements,
        affected_services=affected_services_for(classification),
        requires_flat=classification.requires_flat,
        stages=(
            ReleaseStage.ORIENT,
            ReleaseStage.PREPARE,
            ReleaseStage.SWITCH,
            ReleaseStage.VERIFY,
            ReleaseStage.ACTIVATE,
            ReleaseStage.SEAL,
        ),
        current_stage=current_stage,
        primary_blocker=primary_blocker,
    )


def certification_ready_for(
    requirements: tuple[CertificationRequirement, ...],
    *,
    repo_root: Path,
    target_commit: str,
) -> bool:
    """Return whether one exact committed candidate has reusable certification.

    This is deliberately validation-only: a missing or stale manifest remains a
    Prepare-stage blocker and never causes the planning command to rerun tests.
    """

    try:
        for requirement in requirements:
            if requirement is CertificationRequirement.OWNER_STATIC:
                validate_owner_static_release_certification(repo_root, target_commit)
            elif requirement is CertificationRequirement.OWNER_API:
                validate_owner_api_release_certification(repo_root, target_commit)
            elif requirement is CertificationRequirement.KERNEL_R3:
                validate_release_certification_for_level(
                    repo_root,
                    target_commit,
                    ReleaseCertificationLevel.R3,
                )
            elif requirement is CertificationRequirement.KERNEL_R4:
                validate_release_certification_for_level(
                    repo_root,
                    target_commit,
                    ReleaseCertificationLevel.R4,
                )
        return True
    except (OSError, ValueError):
        return False


def _require_commit(commit: str, *, label: str) -> None:
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError(f"{label} commit must be an exact lowercase SHA")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--target", default="HEAD")
    return parser


def _resolve_commit(reference: str) -> str:
    from subprocess import run

    result = run(
        ("git", "rev-parse", "--verify", f"{reference}^{{commit}}"),
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    _require_commit(commit, label="resolved")
    return commit


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    base_commit = _resolve_commit(args.base)
    target_commit = _resolve_commit(args.target)
    classification = classify_changed_paths(changed_paths_between(base_commit, target_commit))
    plan = build_release_control_plan(
        base_commit=base_commit,
        target_commit=target_commit,
        classification=classification,
        certification_ready=certification_ready_for(
            certification_requirements_for(classification),
            repo_root=Path.cwd(),
            target_commit=target_commit,
        ),
    )
    print(json.dumps(asdict(plan), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
