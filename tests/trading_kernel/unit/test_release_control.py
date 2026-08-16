from __future__ import annotations

import pytest

from scripts.classify_release import ReleaseLevel, classify_changed_paths
from scripts.release_control import (
    CertificationRequirement,
    ReleaseStage,
    build_release_control_plan,
    certification_ready_for,
    certification_requirements_for,
)


@pytest.mark.parametrize(
    ("paths", "expected_requirements", "expected_stage"),
    (
        (("docs/current/MAIN_CONTROL_ROADMAP.md",), (), ReleaseStage.SEAL),
        (("frontend/owner-console/src/app/App.tsx",), (CertificationRequirement.OWNER_STATIC,), ReleaseStage.PREPARE),
        (("src/trading_kernel/interfaces/owner_console_http/routes/auth.py",), (CertificationRequirement.OWNER_API,), ReleaseStage.PREPARE),
        (("src/trading_kernel/application/entry.py",), (CertificationRequirement.KERNEL_R3,), ReleaseStage.PREPARE),
        (("migrations/trading_kernel/versions/0006_example.py",), (CertificationRequirement.KERNEL_R4,), ReleaseStage.PREPARE),
    ),
)
def test_release_control_maps_level_to_one_exact_certification_requirement(
    paths: tuple[str, ...],
    expected_requirements: tuple[CertificationRequirement, ...],
    expected_stage: ReleaseStage,
) -> None:
    classification = classify_changed_paths(paths)

    plan = build_release_control_plan(
        base_commit="a" * 40,
        target_commit="b" * 40,
        classification=classification,
        certification_ready=False,
    )

    assert plan.release_level is classification.level
    assert plan.certification_requirements == expected_requirements
    assert certification_requirements_for(classification) == expected_requirements
    assert plan.current_stage is expected_stage
    assert plan.primary_blocker == (
        None if expected_stage is ReleaseStage.SEAL else "certification_required"
    )


def test_release_control_reuses_exact_certification_before_switch() -> None:
    plan = build_release_control_plan(
        base_commit="a" * 40,
        target_commit="b" * 40,
        classification=classify_changed_paths(("src/trading_kernel/application/entry.py",)),
        certification_ready=True,
    )

    assert plan.current_stage is ReleaseStage.SWITCH
    assert plan.primary_blocker == "internal_external_flatness"
    assert plan.stages == (
        ReleaseStage.ORIENT,
        ReleaseStage.PREPARE,
        ReleaseStage.SWITCH,
        ReleaseStage.VERIFY,
        ReleaseStage.ACTIVATE,
        ReleaseStage.SEAL,
    )


def test_release_control_requires_every_affected_release_plane() -> None:
    plan = build_release_control_plan(
        base_commit="a" * 40,
        target_commit="b" * 40,
        classification=classify_changed_paths(
            (
                "frontend/owner-console/src/app/App.tsx",
                "migrations/trading_kernel/versions/0006_example.py",
            )
        ),
        certification_ready=True,
    )

    assert plan.release_level is ReleaseLevel.R4
    assert plan.certification_requirements == (
        CertificationRequirement.OWNER_STATIC,
        CertificationRequirement.KERNEL_R4,
    )
    assert plan.current_stage is ReleaseStage.SWITCH
    assert plan.affected_services == (
        "nginx-static-symlink",
        "postgresql-authority",
        "brc-trading-kernel-observation-worker.service",
        "brc-trading-kernel-entry-worker.service",
        "brc-trading-kernel-lifecycle-worker.service",
        "brc-trading-kernel-reconciliation-worker.service",
    )


def test_release_control_does_not_omit_static_certification_from_an_api_candidate() -> None:
    classification = classify_changed_paths(
        (
            "frontend/owner-console/src/app/App.tsx",
            "src/trading_kernel/interfaces/owner_console_http/routes/auth.py",
        )
    )

    assert certification_requirements_for(classification) == (
        CertificationRequirement.OWNER_STATIC,
        CertificationRequirement.OWNER_API,
    )


def test_local_certification_tool_does_not_escalate_to_a_kernel_runtime_release() -> None:
    classification = classify_changed_paths(
        ("scripts/trading_kernel/certify_release_candidate.py",)
    )

    assert classification.level is ReleaseLevel.R0


def test_verification_portfolio_does_not_escalate_to_a_kernel_runtime_release() -> None:
    classification = classify_changed_paths(
        ("scripts/trading_kernel/verification_portfolios.py",)
    )

    assert classification.level is ReleaseLevel.R0


def test_release_control_reports_missing_manifest_without_running_certification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.release_control.validate_release_certification_for_level",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("manifest missing")),
    )

    assert (
        certification_ready_for(
            (CertificationRequirement.KERNEL_R4,),
            repo_root=__import__("pathlib").Path("/repo"),
            target_commit="a" * 40,
        )
        is False
    )
