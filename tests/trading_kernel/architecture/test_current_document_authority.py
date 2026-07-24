from __future__ import annotations

from pathlib import Path
import re
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
CURRENT_DOCS_ROOT = REPO_ROOT / "docs" / "current"
PROJECT_SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"

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

PRODUCTION_STATE_DOCUMENTS = (
    "docs/current/MAIN_CONTROL_ROADMAP.md",
    "docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md",
    "docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md",
    "docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md",
)

CURRENT_PRODUCTION_COMMIT = "4749174c"
CURRENT_LOCAL_CERTIFICATION = "407 passed"
CURRENT_ACCEPTANCE_STAGE = "Acceptance-armed"
RETIRED_ACCEPTANCE_TICKET = "ticket:c1ebc24a178a3ae4d87978e2fa1204ae"
RESIDENT_WORKER_NAMES = (
    "Observation",
    "Entry",
    "Lifecycle",
    "Reconciliation",
)
RETIRED_CAPACITY_MARKERS = (
    "real_submit" + "_enabled",
    "max_gross" + "_notional",
    "max_gross" + "_risk_at_stop",
    "max_ticket" + "_risk_at_stop",
    "target" + "_leverage",
    "Acceptance=" + "1 Ticket",
    "Full=" + "2 Tickets",
    "20" + " USDT",
    "40" + " USDT",
)
RETIRED_CAPACITY_SCAN_ROOTS = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/current",
    "src/trading_kernel",
    "scripts/trading_kernel",
    "migrations/trading_kernel",
    "deploy/systemd",
    "tests/trading_kernel",
)
RETIRED_CAPACITY_SCAN_EXCLUSIONS = {
    "tests/trading_kernel/architecture/test_current_document_authority.py",
    "tests/trading_kernel/integration/test_schema_baseline.py",
}


def _current_authority_and_execution_text() -> str:
    result = subprocess.run(
        ("git", "ls-files", "-z", *RETIRED_CAPACITY_SCAN_ROOTS),
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    sources: list[str] = []
    for raw_path in result.stdout.decode("utf-8").split("\0"):
        if not raw_path or raw_path in RETIRED_CAPACITY_SCAN_EXCLUSIONS:
            continue
        path = REPO_ROOT / raw_path
        if path.is_file():
            sources.append(path.read_text(encoding="utf-8"))
    return "\n".join(sources)


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


@pytest.mark.parametrize("retired", RETIRED_CAPACITY_MARKERS)
def test_retired_capacity_semantics_are_absent_from_current_execution(
    retired: str,
) -> None:
    assert retired not in _current_authority_and_execution_text()


def test_production_state_documents_match_the_deployed_kernel() -> None:
    violations: list[str] = []

    for relative_path in PRODUCTION_STATE_DOCUMENTS:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        if CURRENT_PRODUCTION_COMMIT not in source:
            violations.append(f"{relative_path}: missing production commit")
        if CURRENT_LOCAL_CERTIFICATION not in source:
            violations.append(f"{relative_path}: missing current test certification")
        if CURRENT_ACCEPTANCE_STAGE not in source:
            violations.append(f"{relative_path}: missing acceptance-stage marker")
        for worker_name in RESIDENT_WORKER_NAMES:
            if worker_name not in source:
                violations.append(f"{relative_path}: missing {worker_name} worker")
        if "303 passed" in source:
            violations.append(f"{relative_path}: stale 303-test certification")
        if "no Tokyo mutation claimed" in source:
            violations.append(f"{relative_path}: stale pre-cutover Tokyo status")
        if RETIRED_ACCEPTANCE_TICKET in source:
            violations.append(f"{relative_path}: retired acceptance Ticket is current")

    assert not violations, "production-state drift remains:\n" + "\n".join(
        sorted(violations)
    )


def test_current_runtime_documents_do_not_deploy_timer_workers() -> None:
    violations: list[str] = []
    timer_deployment_patterns = (
        re.compile(r"deploy/systemd/[^`\s]*\.timer", re.IGNORECASE),
        re.compile(r"systemctl\s+enable\s+[^\n]*\.timer", re.IGNORECASE),
        re.compile(r"systemctl\s+start\s+[^\n]*\.timer", re.IGNORECASE),
    )

    for relative_path in PRODUCTION_STATE_DOCUMENTS:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in timer_deployment_patterns:
            for match in pattern.finditer(source):
                violations.append(f"{relative_path}: {match.group(0)}")

    assert not violations, "timer-based worker deployment remains:\n" + "\n".join(
        sorted(violations)
    )
