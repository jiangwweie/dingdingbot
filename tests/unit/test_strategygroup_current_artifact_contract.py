from __future__ import annotations

import json
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]

PRIMARY_JUDGMENT_TRUE_RE = re.compile(
    r"primary_judgment_source.*(?:true|True)", re.IGNORECASE
)
PRIMARY_JUDGMENT_TRUE_ALLOWED_PATHS = {
}
RETIRED_CURRENT_ARTIFACT_PATH_TOKENS = {
    "latest-strategygroup-owner-decision-package",
    "latest-strategygroup-tradeability-verdict",
    "latest-strategygroup-capital-trial-readiness-bridge",
    "latest-strategygroup-live-submit-readiness-bridge",
    "latest-strategygroup-decision-ledger",
}


def _read_json(path: str) -> dict:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


def _assert_output_paths_absent(*paths: str) -> None:
    assert [path for path in paths if (REPO_ROOT / path).exists()] == []


def test_primary_judgment_source_true_is_allowlisted_to_core_states():
    violations: list[str] = []
    scanned_roots = (
        REPO_ROOT / "scripts",
        REPO_ROOT / "src",
        REPO_ROOT / "docs/current",
        REPO_ROOT / "output/runtime-monitor",
    )

    for root in scanned_roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".json", ".md"}:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not PRIMARY_JUDGMENT_TRUE_RE.search(line):
                    continue
                if relative not in PRIMARY_JUDGMENT_TRUE_ALLOWED_PATHS:
                    violations.append(f"{relative}:{line_number}:{line.strip()}")

    assert violations == []


def test_current_artifact_contract_blocks_retired_generated_artifact_paths():
    violations: list[str] = []
    scanned_roots = (
        REPO_ROOT / "scripts",
        REPO_ROOT / "docs/current",
    )

    for root in scanned_roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".json", ".md"}:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for token in RETIRED_CURRENT_ARTIFACT_PATH_TOKENS:
                if token in text:
                    violations.append(f"{relative}:{token}")

    assert violations == []


def test_current_d3_review_projections_have_no_authority_mirror_fields():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-opportunity-review-work-loop.md",
        "output/runtime-monitor/latest-strategygroup-regime-role-coverage-map.json",
    )


def test_current_d4_strategy_asset_projections_have_no_authority_mirror_fields():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-research-intake-review.json",
    )


def test_current_trial_asset_admission_proposal_artifact_is_complete():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json",
        "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.md",
    )


def test_current_capital_trial_envelope_projection_has_no_authority_mirrors():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-projection.json",
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-projection.md",
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-v0.json",
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-v0.md",
    )


def test_current_strategy_decision_owner_outputs_have_no_real_order_mirrors():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-owner-decision-package.json",
        "output/runtime-monitor/latest-strategygroup-owner-decision-package.md",
        "output/runtime-monitor/latest-strategygroup-quality-closure-wave.json",
        "output/runtime-monitor/latest-strategygroup-quality-closure-wave.md",
        "output/runtime-monitor/latest-strategygroup-owner-policy-package.json",
        "output/runtime-monitor/latest-strategygroup-owner-policy-package.md",
    )


def test_current_trial_grade_signal_gate_audit_does_not_expose_authority_mirrors():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.json",
        "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.md",
    )
