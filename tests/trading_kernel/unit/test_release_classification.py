from __future__ import annotations

from scripts.classify_release import ReleaseLevel, classify_changed_paths


def test_release_classification_uses_the_heaviest_changed_boundary() -> None:
    cases = (
        (("docs/current/MAIN_CONTROL_ROADMAP.md",), ReleaseLevel.R0),
        (("scripts/trading_kernel/deploy_tokyo_release.py",), ReleaseLevel.R0),
        (("frontend/owner-console/src/app/App.tsx",), ReleaseLevel.R1),
        (
            ("src/trading_kernel/interfaces/owner_console_http/app.py",),
            ReleaseLevel.R2,
        ),
        (("src/trading_kernel/application/entry.py",), ReleaseLevel.R3),
        (("migrations/trading_kernel/versions/0005_example.py",), ReleaseLevel.R4),
        (
            (
                "frontend/owner-console/src/app/App.tsx",
                "src/trading_kernel/application/entry.py",
            ),
            ReleaseLevel.R3,
        ),
    )

    for paths, expected in cases:
        assert classify_changed_paths(paths).level is expected


def test_release_classification_defaults_unknown_runtime_paths_to_r3() -> None:
    result = classify_changed_paths(("unclassified/runtime_hook.py",))

    assert result.level is ReleaseLevel.R3
    assert result.primary_blocker == "internal_external_flatness"


def test_release_classification_keeps_authority_changes_at_r4() -> None:
    result = classify_changed_paths(
        (
            "src/trading_kernel/domain/strategy_registry.py",
            "deploy/owner-console/postgresql/owner-console-control-role.sql",
        )
    )

    assert result.level is ReleaseLevel.R4
    assert result.requires_flat is True
    assert result.requires_kernel_certification is True
