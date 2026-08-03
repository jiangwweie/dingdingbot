from __future__ import annotations

import re
import subprocess
from pathlib import Path

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
    "Active operability-repair",
    "Active Operability Repair",
    "Complete locally, not deployed",
    "pre-repair deployed model",
    "becomes production truth only after",
    "after the active operability repair",
    "v4 -> v5",
    "v4-to-v5",
)

CURRENT_RUNTIME_STATE_DOCUMENT = "docs/current/MAIN_CONTROL_ROADMAP.md"
VOLATILE_STATE_FREE_DOCUMENTS = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md",
    "docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md",
    "docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md",
)
RUNTIME_MODEL_DOCUMENTS = (
    CURRENT_RUNTIME_STATE_DOCUMENT,
    "docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md",
    "docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md",
    "docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md",
)
SCHEMA_MIGRATION_AUTHORITY_DOCUMENTS = (
    "docs/current/PROJECT_INFORMATION_ARCHITECTURE.md",
    "docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md",
    "docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md",
)

CURRENT_ACCEPTANCE_STAGE = "Current live acceptance"
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


def test_completed_operability_repair_is_not_current_authority() -> None:
    completed_documents = {
        "TRADING_KERNEL_OPERABILITY_REPAIR_DESIGN.md",
        "TRADING_KERNEL_OPERABILITY_REPAIR_TEST_SPEC.md",
        "TRADING_KERNEL_OPERABILITY_REPAIR_EXECUTION_PLAN.md",
    }
    actual = {
        path.name
        for path in CURRENT_DOCS_ROOT.rglob("*.md")
    }

    assert completed_documents.isdisjoint(actual)

    for relative_path in ENTRY_DOCUMENTS:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for document in completed_documents:
            assert document not in source


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


def test_current_documents_do_not_restore_retired_candidate_authority() -> None:
    registry_contract = (
        CURRENT_DOCS_ROOT
        / "strategy-group-handoffs"
        / "STRATEGYGROUP_REGISTRY_CONTRACT.md"
    ).read_text(encoding="utf-8")

    assert "| `candidate_instruments` |" not in registry_contract
    assert "| `candidate_scope_priority` |" not in registry_contract
    assert "StrategyUniverse" in registry_contract
    assert "current pointer is the sole" in registry_contract


@pytest.mark.parametrize("retired", RETIRED_CAPACITY_MARKERS)
def test_retired_capacity_semantics_are_absent_from_current_execution(
    retired: str,
) -> None:
    assert retired not in _current_authority_and_execution_text()


def test_runtime_state_document_matches_the_deployed_kernel() -> None:
    source = (REPO_ROOT / CURRENT_RUNTIME_STATE_DOCUMENT).read_text(encoding="utf-8")
    commit_match = re.search(
        r"\| Production commit \| `([0-9a-f]{40})` \|",
        source,
    )
    tag_match = re.search(
        r"\| Production tag \| `(tokyo-runtime-\d{4}\.\d{2}\.\d{2}\.\d+)`",
        source,
    )
    certification_match = re.search(
        r"\| Production-commit certification \| `(\d+ passed)`;",
        source,
    )
    assert commit_match is not None
    assert tag_match is not None
    assert certification_match is not None

    production_commit = commit_match.group(1)
    production_tag = tag_match.group(1)
    resolved_tag = subprocess.run(
        ("git", "rev-parse", f"{production_tag}^{{}}"),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert resolved_tag == production_commit
    required_markers = (CURRENT_ACCEPTANCE_STAGE, *RESIDENT_WORKER_NAMES)

    missing = [marker for marker in required_markers if marker not in source]

    assert not missing, (
        f"{CURRENT_RUNTIME_STATE_DOCUMENT} is missing current runtime facts:\n"
        + "\n".join(sorted(missing))
    )
    assert "303 passed" not in source
    assert "407 passed" not in source
    assert "765 passed" not in source
    assert "no Tokyo mutation claimed" not in source
    assert RETIRED_ACCEPTANCE_TICKET not in source
    assert "| Integration branch | `dev` |" in source
    assert "codex/sor-v3-strategy-capacity-migration-20260731" not in source


def test_current_authority_distinguishes_data_migration_from_runtime_compatibility() -> None:
    required_meaning = {
        "AGENTS.md": (
            "preserve certified terminal lineage",
            "runtime compatibility adapters remain forbidden",
        ),
        "docs/current/AI_AGENT_CONSTRAINTS.md": (
            "preserve certified terminal lineage",
            "runtime compatibility adapters remain forbidden",
        ),
    }

    for relative_path, markers in required_meaning.items():
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in source]
        assert not missing, f"{relative_path} lacks migration boundary: {missing}"


def test_stable_documents_do_not_duplicate_volatile_runtime_facts() -> None:
    volatile_patterns = (
        re.compile(r"\b[0-9a-f]{40}\b"),
        re.compile(r"`[0-9a-f]{7,40}`"),
        re.compile(r"\b\d+ passed\b"),
        re.compile(r"tokyo-runtime-\d{4}\.\d{2}\.\d{2}\.\d+"),
        re.compile(r"ticket:[0-9a-f]{32}"),
        re.compile(r"\bAcceptance-armed\b"),
    )
    violations: list[str] = []

    for relative_path in VOLATILE_STATE_FREE_DOCUMENTS:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in volatile_patterns:
            for match in pattern.finditer(source):
                violations.append(f"{relative_path}: {match.group(0)}")

    assert not violations, "volatile runtime facts are duplicated:\n" + "\n".join(
        sorted(violations)
    )


def test_current_runtime_documents_do_not_deploy_timer_workers() -> None:
    violations: list[str] = []
    timer_deployment_patterns = (
        re.compile(r"deploy/systemd/[^`\s]*\.timer", re.IGNORECASE),
        re.compile(r"systemctl\s+enable\s+[^\n]*\.timer", re.IGNORECASE),
        re.compile(r"systemctl\s+start\s+[^\n]*\.timer", re.IGNORECASE),
    )

    for relative_path in RUNTIME_MODEL_DOCUMENTS:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in timer_deployment_patterns:
            for match in pattern.finditer(source):
                violations.append(f"{relative_path}: {match.group(0)}")

    assert not violations, "timer-based worker deployment remains:\n" + "\n".join(
        sorted(violations)
    )


def test_current_schema_authority_is_the_exact_flat_forward_revision_chain() -> None:
    expected_chain = (
        "0001_trading_kernel_baseline_v4 "
        "-> 0002_sor_v3_strategy_group_capacity "
        "-> 0003_portfolio_admission_observability"
    )

    for relative_path in SCHEMA_MIGRATION_AUTHORITY_DOCUMENTS:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        normalized = re.sub(r"\s+", " ", source.replace("`", ""))
        assert expected_chain in normalized, (
            f"{relative_path} does not own the exact forward revision chain"
        )


def test_current_documents_converge_on_portfolio_admission_authority() -> None:
    required_meaning = {
        "docs/current/PROJECT_INFORMATION_ARCHITECTURE.md": (
            "AdmissionDecision",
            "Shadow Outcome",
        ),
        "docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md": (
            "Policy v4",
            "Exposure Family",
            "AdmissionDecision",
            "Shadow Outcome",
        ),
        "docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md": (
            "0003_portfolio_admission_observability",
            "AdmissionDecision",
            "Shadow Outcome",
        ),
        "docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md": (
            "max_ticket_stop_risk_fraction = 0.02",
            "min_materialization_ratio = 0.50",
            "directional_stop_risk_limit_fraction = 0.04",
        ),
        "docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md": (
            "0003_portfolio_admission_observability",
            "fix-forward",
        ),
        "docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md": (
            "fixed_horizon_excursion_v1",
            "Shadow Outcome",
        ),
    }
    for relative_path, markers in required_meaning.items():
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in source]
        assert not missing, f"{relative_path} lacks portfolio authority: {missing}"


def test_stable_policy_v4_target_is_distinct_from_deployed_policy_v3() -> None:
    runtime_profile = (
        REPO_ROOT / "docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md"
    ).read_text(encoding="utf-8")
    owner_model = (
        REPO_ROOT / "docs/current/OWNER_RUNTIME_OPERATING_MODEL.md"
    ).read_text(encoding="utf-8")
    roadmap = (REPO_ROOT / CURRENT_RUNTIME_STATE_DOCUMENT).read_text(
        encoding="utf-8"
    )

    for relative_path, source in (
        (
            "docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md",
            runtime_profile,
        ),
        ("docs/current/OWNER_RUNTIME_OPERATING_MODEL.md", owner_model),
    ):
        assert "approved post-`0003` Policy v4 target contract" in source, (
            f"{relative_path} does not identify Policy v4 as a target contract"
        )
        assert "currently deployed Policy v3" in source, (
            f"{relative_path} does not defer deployed identity to the roadmap"
        )
        assert "MAIN_CONTROL_ROADMAP.md" in source

    assert "| Dynamic policy | Policy version `3`;" in roadmap
    assert "Policy version `4`" not in roadmap
    assert "0003_portfolio_admission_observability" not in roadmap


def test_current_deployment_authority_has_no_active_handover_or_schema_deletion() -> None:
    forbidden = (
        "--protected-ticket-id",
        "--protected-ticket-json",
        "deploy-protected-identity",
        "DROP SCHEMA public",
    )
    violations: list[str] = []

    for relative_path in SCHEMA_MIGRATION_AUTHORITY_DOCUMENTS:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in source:
                violations.append(f"{relative_path}: {marker}")

    assert not violations, (
        "retired deployment authority remains:\n" + "\n".join(violations)
    )
