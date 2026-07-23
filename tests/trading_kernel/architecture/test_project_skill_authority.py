from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"

HIGH_RISK_SKILLS = (
    "architect/SKILL.md",
    "backend/SKILL.md",
    "chain-position/SKILL.md",
    "reviewer/SKILL.md",
    "runtime-signal-forensics/SKILL.md",
    "kaigong/SKILL.md",
    "pm/SKILL.md",
    "qa/SKILL.md",
    "shougong/SKILL.md",
    "doc-manager/SKILL.md",
)

REQUIRED_HIGH_RISK_REFERENCES = (
    "AGENTS.md",
    "docs/current/PROJECT_INFORMATION_ARCHITECTURE.md",
)

RETIRED_SKILL_PATTERNS = {
    "retired source tree": re.compile(
        r"src/(?:application|domain|infrastructure)(?:/|`)", re.IGNORECASE
    ),
    "FinalGate": re.compile(r"\bFinalGate\b", re.IGNORECASE),
    "Operation Layer": re.compile(r"\bOperation Layer\b", re.IGNORECASE),
    "promotion candidate": re.compile(r"promotion[_ -]candidate", re.IGNORECASE),
    "action-time lane input": re.compile(
        r"action[_ -]time[_ -]lane[_ -]input", re.IGNORECASE
    ),
    "retired watcher unit": re.compile(
        r"brc-(?:runtime-signal-watcher|runtime-monitor)", re.IGNORECASE
    ),
    "timer unit": re.compile(r"[A-Za-z0-9_.@-]+\.timer\b", re.IGNORECASE),
    "retired layered chain": re.compile(r"\bL[2-7](?:\s*[-→>]\s*L[2-7])+\b"),
}


def _skill_document_paths() -> list[Path]:
    return sorted(PROJECT_SKILLS_ROOT.rglob("*.md"))


def test_all_project_skill_document_current_references_exist() -> None:
    missing: list[str] = []
    reference_pattern = re.compile(r"docs/current/[A-Za-z0-9_./-]+\.md")

    for path in _skill_document_paths():
        source = path.read_text(encoding="utf-8")
        for reference in sorted(set(reference_pattern.findall(source))):
            if not (REPO_ROOT / reference).is_file():
                missing.append(
                    f"{path.relative_to(REPO_ROOT).as_posix()}: {reference}"
                )

    assert not missing, "stale current-document references remain in Skills:\n" + (
        "\n".join(missing)
    )


def test_all_project_skill_documents_exclude_retired_runtime_semantics() -> None:
    violations: list[str] = []

    for path in _skill_document_paths():
        source = path.read_text(encoding="utf-8")
        for label, pattern in RETIRED_SKILL_PATTERNS.items():
            if pattern.search(source):
                violations.append(
                    f"{path.relative_to(REPO_ROOT).as_posix()}: {label}"
                )

    assert not violations, "retired runtime semantics remain in Skills:\n" + "\n".join(
        sorted(violations)
    )


def test_high_risk_skills_anchor_to_current_project_authority() -> None:
    violations: list[str] = []

    for relative_path in HIGH_RISK_SKILLS:
        path = PROJECT_SKILLS_ROOT / relative_path
        source = path.read_text(encoding="utf-8")
        for required_reference in REQUIRED_HIGH_RISK_REFERENCES:
            if required_reference not in source:
                violations.append(f"{relative_path}: missing {required_reference}")

    assert not violations, "high-risk Skills lack current authority anchors:\n" + (
        "\n".join(sorted(violations))
    )
