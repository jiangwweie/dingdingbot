from __future__ import annotations

from scripts import audit_production_runtime_file_io as audit


def test_file_io_audit_rejects_trading_kernel_runtime_file_read() -> None:
    occurrences = audit.audit_python_file(
        rel_path="src/trading_kernel/application/runtime.py",
        text='''
def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()
''',
    )

    flagged = [item for item in occurrences if "runtime_file_read" in item.risk_flags]
    assert flagged
    assert {item.runtime_surface for item in flagged} == {"trading_kernel_runtime"}
    assert all("blocking_cleanup_required" in item.risk_flags for item in flagged)


def test_file_io_audit_rejects_trading_kernel_runtime_file_write() -> None:
    occurrences = audit.audit_python_file(
        rel_path="scripts/trading_kernel/run_command_worker_once.py",
        text='''
from pathlib import Path

def save(path):
    Path(path).write_text("state", encoding="utf-8")
''',
    )

    flagged = [item for item in occurrences if "runtime_file_write" in item.risk_flags]
    assert flagged
    assert {item.runtime_surface for item in flagged} == {"trading_kernel_runtime"}
    assert all("blocking_cleanup_required" in item.risk_flags for item in flagged)


def test_current_runtime_has_no_blocking_file_authority() -> None:
    occurrences = audit.audit_targets(
        repo_root=audit.REPO_ROOT,
        targets=["src/trading_kernel", "scripts/trading_kernel"],
    )
    blocking = [
        item
        for item in occurrences
        if "blocking_cleanup_required" in item.risk_flags
    ]
    assert blocking == []
