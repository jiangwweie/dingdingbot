from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOTS = (
    REPO_ROOT / "src/trading_kernel",
    REPO_ROOT / "migrations/trading_kernel",
    REPO_ROOT / "scripts/trading_kernel",
)
FORBIDDEN_TERMS = (
    "correlation",
    "covariance",
    "相关性",
    "相关系数",
)


def test_runtime_and_schema_do_not_implement_correlation_admission() -> None:
    violations: list[str] = []
    for root in RUNTIME_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".sql"}:
                continue
            lowered = path.read_text(encoding="utf-8").lower()
            for term in FORBIDDEN_TERMS:
                if term in lowered:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT).as_posix()}: {term}"
                    )
    assert violations == []
