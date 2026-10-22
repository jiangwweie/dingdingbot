"""Keep the explanatory knowledge base navigable without making it authority."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE = ROOT / "docs" / "knowledge"
EXPECTED = {
    "README.md",
    "SOURCE_AUTHORITY.md",
    "GLOSSARY.md",
    "SYSTEM_OVERVIEW.md",
    "TRADE_LIFECYCLE.md",
    "DYNAMIC_SELECTION.md",
    "OWNER_CONTROLS.md",
    "RISK_AND_EXIT.md",
    "DATA_MODEL.md",
    "DEPLOYMENT_AND_RECOVERY.md",
    "CODE_AND_TEST_INDEX.md",
    "MAINTENANCE.md",
}
LINK = re.compile(r"\[[^\]\n]+\]\(([^)\s]+)\)")


def test_knowledge_has_one_complete_explanatory_entry() -> None:
    assert {p.name for p in KNOWLEDGE.glob("*.md")} == EXPECTED
    entry = (KNOWLEDGE / "README.md").read_text()
    assert EXPECTED - {"README.md"} <= set(LINK.findall(entry))
    assert "knowledge/README.md" in (ROOT / "docs" / "README.md").read_text()
    for name in EXPECTED:
        source = (KNOWLEDGE / name).read_text()
        assert "解释性知识库" in source, name
        assert "MAIN_CONTROL_ROADMAP.md" in source, name
        if name != "README.md":
            assert "[知识地图](README.md)" in source, name


def test_knowledge_links_and_python_definition_anchors_resolve() -> None:
    documents = sorted(KNOWLEDGE.glob("*.md"))
    assert documents, "knowledge base is missing"
    errors: list[str] = []
    for document in documents:
        for target in LINK.findall(document.read_text()):
            if target.startswith(("https://", "http://")):
                continue
            path, _, fragment = target.partition("#")
            resolved = (document.parent / path).resolve() if path else document
            if not resolved.is_relative_to(ROOT) or not resolved.is_file():
                errors.append(f"{document.name}: missing or nonportable {target}")
                continue
            if resolved.suffix == ".py" and fragment:
                definitions = {
                    node.lineno
                    for node in ast.walk(ast.parse(resolved.read_text()))
                    if isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    )
                }
                if not fragment.startswith("L") or not fragment[1:].isdigit():
                    errors.append(f"{document.name}: invalid Python anchor {target}")
                elif int(fragment[1:]) not in definitions:
                    errors.append(f"{document.name}: stale definition anchor {target}")
            elif resolved.suffix == ".md" and fragment:
                if f'id="{fragment}"' not in resolved.read_text():
                    errors.append(f"{document.name}: missing explicit anchor {target}")
    assert not errors, "\n".join(errors)
