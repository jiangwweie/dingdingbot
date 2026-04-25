from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.application.readmodels.console_models import CandidateListItem


STRICT_PARAM_BOUNDS = {
    "ema_period": (40, 80),
    "max_atr_ratio": (Decimal("0.005"), Decimal("0.03")),
    "min_distance_pct": (Decimal("0.003"), Decimal("0.02")),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _artifact_dir() -> Path:
    return _repo_root() / "reports" / "optuna_candidates"


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _is_on_boundary(name: str, value: Any) -> bool:
    if name not in STRICT_PARAM_BOUNDS:
        return False
    lower, upper = STRICT_PARAM_BOUNDS[name]
    parsed = _to_decimal(value)
    if parsed is None:
        return False
    return parsed == Decimal(str(lower)) or parsed == Decimal(str(upper))


class CandidateArtifactService:
    def __init__(self, artifact_dir: Path | None = None) -> None:
        self._artifact_dir = artifact_dir or _artifact_dir()

    def list_candidates(self, limit: int = 100) -> list[CandidateListItem]:
        if not self._artifact_dir.exists():
            return []

        items: list[CandidateListItem] = []
        for path in sorted(self._artifact_dir.glob("*.json"), reverse=True):
            payload = self._load_json(path)
            if payload is None:
                continue
            items.append(self._to_list_item(payload))

        items.sort(key=lambda item: item.generated_at, reverse=True)
        return items[:limit]

    def _load_json(self, path: Path) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
        except (OSError, json.JSONDecodeError):
            return None
        return None

    def _to_list_item(self, payload: dict[str, Any]) -> CandidateListItem:
        best_trial = payload.get("best_trial") or {}
        warnings = self._build_warnings(best_trial)
        review_status, strict_gate_result = self._evaluate_review(best_trial, warnings)

        return CandidateListItem(
            candidate_name=str(payload.get("candidate_name", "unknown")),
            generated_at=str(payload.get("generated_at", "")),
            source_profile=str((payload.get("source_profile") or {}).get("name", "unknown")),
            git_commit=str((payload.get("git") or {}).get("commit", ""))[:12],
            objective=str((payload.get("job") or {}).get("objective", "unknown")),
            review_status=review_status,
            strict_gate_result=strict_gate_result,
            warnings=warnings,
        )

    def _build_warnings(self, best_trial: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        sortino = _to_decimal(best_trial.get("sortino_ratio"))
        if sortino is None or sortino == Decimal("0"):
            warnings.append("sortino_missing_or_suspect")

        params = best_trial.get("params") or {}
        if any(_is_on_boundary(name, value) for name, value in params.items()):
            warnings.append("parameter_near_boundary")

        return warnings

    def _evaluate_review(
        self,
        best_trial: dict[str, Any],
        warnings: list[str],
    ) -> tuple[str, str]:
        total_trades = int(best_trial.get("total_trades") or 0)
        sharpe_ratio = float(best_trial.get("sharpe_ratio") or 0.0)
        total_return = float(_to_decimal(best_trial.get("total_return")) or Decimal("0"))
        max_drawdown = float(_to_decimal(best_trial.get("max_drawdown")) or Decimal("0"))
        win_rate = float(best_trial.get("win_rate") or 0.0)
        params_at_boundary = "parameter_near_boundary" in warnings

        strict_pass = (
            total_trades >= 100
            and sharpe_ratio >= 1.0
            and total_return >= 0.30
            and max_drawdown <= 0.25
            and win_rate >= 0.45
            and not params_at_boundary
        )

        if strict_pass:
            if warnings:
                return "PASS_STRICT_WITH_WARNINGS", "PASSED"
            return "PASS_STRICT", "PASSED"

        loose_pass = (
            total_trades >= 50
            and sharpe_ratio >= 0.5
            and total_return >= 0.10
            and max_drawdown <= 0.30
            and win_rate >= 0.40
        )
        if loose_pass:
            return "PASS_LOOSE", "FAILED"

        return "REJECT", "FAILED"

