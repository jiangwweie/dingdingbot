from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = REPO_ROOT / "tests" / "trading_kernel"


def _test_module_imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    return tuple(imports)


def test_test_modules_do_not_import_other_test_modules() -> None:
    violations: list[str] = []
    for path in TEST_ROOT.rglob("test_*.py"):
        relative = path.relative_to(REPO_ROOT).as_posix()
        for module in _test_module_imports(path):
            if ".test_" in module or module.startswith("test_"):
                violations.append(f"{relative}: {module}")

    assert not violations, (
        "shared fixture and helper code belongs under tests/trading_kernel/support; "
        "test modules must not become a public fixture API:\n"
        + "\n".join(sorted(violations))
    )


def test_support_modules_do_not_import_test_modules() -> None:
    violations: list[str] = []
    for path in (TEST_ROOT / "support").rglob("*.py"):
        relative = path.relative_to(REPO_ROOT).as_posix()
        for module in _test_module_imports(path):
            if ".test_" in module or module.startswith("test_"):
                violations.append(f"{relative}: {module}")

    assert not violations, "support module imports test module:\n" + "\n".join(
        sorted(violations)
    )
