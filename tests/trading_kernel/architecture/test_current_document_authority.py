from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[3]
CURRENT_DOCS_ROOT = REPO_ROOT / "docs" / "current"

CURRENT_DOCUMENT_ALLOWLIST = {
    "AI_AGENT_CONSTRAINTS.md",
    "BLOCKER_CLASSIFICATION_CONTRACT.md",
    "MAIN_CONTROL_ROADMAP.md",
    "OWNER_RUNTIME_OPERATING_MODEL.md",
    "P0_TRADING_KERNEL_REBUILD_DESIGN.md",
    "P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md",
    "PROJECT_INFORMATION_ARCHITECTURE.md",
    "RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md",
    "STRATEGY_ENGINEERING_INTAKE_CONTRACT.md",
    "STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md",
    "TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md",
    "TRADEABILITY_DECISION_CONTRACT.md",
    "strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md",
}

ENTRY_DOCUMENTS = (
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "MEMORY.md",
    "docs/README.md",
)

RETIRED_AUTHORITY_MARKERS = (
    "DUAL_POSITION_",
    "P0-ACH",
    "migration 146",
    "schema 143",
    "brc_account_risk_policy_current",
    "src/application/action_time",
    "src/application/runtime_execution",
)


def test_current_documents_are_the_minimal_kernel_authority_set() -> None:
    actual = {
        path.relative_to(CURRENT_DOCS_ROOT).as_posix()
        for path in CURRENT_DOCS_ROOT.rglob("*.md")
    }

    assert actual == CURRENT_DOCUMENT_ALLOWLIST, (
        "docs/current must contain only the rebuilt-kernel authority set\n"
        f"unexpected={sorted(actual - CURRENT_DOCUMENT_ALLOWLIST)}\n"
        f"missing={sorted(CURRENT_DOCUMENT_ALLOWLIST - actual)}"
    )


def test_entry_documents_reference_only_existing_current_documents() -> None:
    missing: list[str] = []
    reference_pattern = re.compile(r"docs/current/[A-Za-z0-9_./-]+\.md")

    for relative_path in ENTRY_DOCUMENTS:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for reference in sorted(set(reference_pattern.findall(source))):
            if not (REPO_ROOT / reference).is_file():
                missing.append(f"{relative_path}: {reference}")

    assert not missing, "stale current-document references remain:\n" + "\n".join(
        missing
    )


def test_current_authority_does_not_reintroduce_retired_execution_semantics() -> None:
    violations: list[str] = []
    paths = [REPO_ROOT / path for path in ENTRY_DOCUMENTS]
    paths.extend(CURRENT_DOCS_ROOT.rglob("*.md"))

    for path in paths:
        source = path.read_text(encoding="utf-8")
        for marker in RETIRED_AUTHORITY_MARKERS:
            if marker in source:
                violations.append(
                    f"{path.relative_to(REPO_ROOT).as_posix()}: {marker}"
                )

    assert not violations, "retired authority semantics remain:\n" + "\n".join(
        sorted(violations)
    )
