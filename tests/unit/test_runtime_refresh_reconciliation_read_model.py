from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "runtime_refresh_reconciliation_read_model.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "runtime_refresh_reconciliation_read_model",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class _Mismatch:
    symbol: str = "AVAX/USDT:USDT"
    mismatch_type: str = "local_order_missing_on_exchange"
    severity: str = "WARNING"
    reason: str = "test mismatch"
    metadata: dict[str, str] = field(default_factory=lambda: {"source": "test"})


@dataclass
class _Result:
    symbol: str = "AVAX/USDT:USDT"
    checked_at: int = 1781000000000
    mismatches: list[_Mismatch] = field(default_factory=list)

    @property
    def is_consistent(self) -> bool:
        return not self.mismatches

    @property
    def severe_count(self) -> int:
        return sum(1 for item in self.mismatches if item.severity == "SEVERE")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.mismatches if item.severity == "WARNING")


def test_summarize_result_preserves_report_only_boundary():
    module = _load_module()

    summary = module._summarize_result(
        _Result(mismatches=[_Mismatch()]),
        persisted=True,
    )

    assert summary["symbol"] == "AVAX/USDT:USDT"
    assert summary["is_consistent"] is False
    assert summary["warning_count"] == 1
    assert summary["severe_count"] == 0
    assert summary["mismatch_count"] == 1
    assert summary["persisted"] is True
    assert summary["mismatches"][0]["metadata"] == {"source": "test"}


def test_parse_bool_env_accepts_only_explicit_true_values():
    module = _load_module()

    assert module._parse_bool_env("true") is True
    assert module._parse_bool_env("1") is True
    assert module._parse_bool_env("yes") is True
    assert module._parse_bool_env("false") is False
    assert module._parse_bool_env(None) is False
