from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.application.readmodels.console_models import (
    CandidateDetailResponse,
    CandidateListItem,
    CandidateMetadata,
    CandidateTrialItem,
    ReplayContextResponse,
    ReviewSummaryResponse,
    StrictGateCheckItem,
)


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
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        return None

    def _to_list_item(self, payload: dict[str, Any]) -> CandidateListItem:
        best_trial = payload.get("best_trial") or {}
        warnings = self._build_warnings(best_trial)
        review_status, strict_gate_result = self._evaluate_review(best_trial, warnings)

        source_profile_data = payload.get("source_profile") or {}
        git_data = payload.get("git") or {}
        job_data = payload.get("job") or {}

        return CandidateListItem(
            candidate_name=str(payload.get("candidate_name", "unknown")),
            generated_at=str(payload.get("generated_at", "")),
            source_profile=str(source_profile_data.get("name", "unknown")),
            git_commit=str(git_data.get("commit", ""))[:12],
            objective=str(job_data.get("objective", "unknown")),
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

    def get_candidate_detail(self, candidate_name: str) -> CandidateDetailResponse | None:
        """Return full candidate detail by name."""
        payload = self._find_candidate(candidate_name)
        if payload is None:
            return None
        return self._to_detail_response(payload)

    def get_replay_context(self, candidate_name: str) -> ReplayContextResponse | None:
        """Return replay context (reproduce_cmd + metadata + resolved_request + runtime_overrides)."""
        payload = self._find_candidate(candidate_name)
        if payload is None:
            return None
        metadata = self._build_metadata(payload)
        return ReplayContextResponse(
            candidate_name=str(payload.get("candidate_name", "unknown")),
            metadata=metadata,
            reproduce_cmd=str(payload.get("reproduce_cmd", "")),
            resolved_request=payload.get("resolved_request") or {},
            runtime_overrides=payload.get("runtime_overrides") or {},
            generated_at=metadata.generated_at,
        )

    def get_review_summary(self, candidate_name: str) -> ReviewSummaryResponse | None:
        """Return review summary with strict_v1 gate checklist."""
        payload = self._find_candidate(candidate_name)
        if payload is None:
            return None
        best_trial = payload.get("best_trial") or {}
        warnings = self._build_warnings(best_trial)
        review_status, strict_gate_result = self._evaluate_review(best_trial, warnings)

        # Build strict_v1 checklist
        total_trades = int(best_trial.get("total_trades") or 0)
        sharpe_ratio = float(best_trial.get("sharpe_ratio") or 0.0)
        total_return = float(_to_decimal(best_trial.get("total_return")) or Decimal("0"))
        max_drawdown = float(_to_decimal(best_trial.get("max_drawdown")) or Decimal("0"))
        win_rate = float(best_trial.get("win_rate") or 0.0)
        params_at_boundary = "parameter_near_boundary" in warnings

        checklist = [
            StrictGateCheckItem(gate="total_trades", threshold=">=100", actual=str(total_trades), passed=total_trades >= 100),
            StrictGateCheckItem(gate="sharpe_ratio", threshold=">=1.0", actual=f"{sharpe_ratio:.3f}", passed=sharpe_ratio >= 1.0),
            StrictGateCheckItem(gate="total_return", threshold=">=0.30", actual=f"{total_return:.3f}", passed=total_return >= 0.30),
            StrictGateCheckItem(gate="max_drawdown", threshold="<=0.25", actual=f"{max_drawdown:.3f}", passed=max_drawdown <= 0.25),
            StrictGateCheckItem(gate="win_rate", threshold=">=0.45", actual=f"{win_rate:.3f}", passed=win_rate >= 0.45),
            StrictGateCheckItem(gate="no_boundary_params", threshold="none", actual=str(params_at_boundary), passed=not params_at_boundary),
        ]

        # Params at boundary detail
        boundary_params: list[str] = []
        params = best_trial.get("params") or {}
        for name, value in params.items():
            if _is_on_boundary(name, value):
                boundary_params.append(name)

        # Summary text
        passed_count = sum(1 for c in checklist if c.passed)
        summary = f"{passed_count}/{len(checklist)} strict gates passed. Status: {review_status}."

        return ReviewSummaryResponse(
            candidate_name=str(payload.get("candidate_name", "unknown")),
            review_status=review_status,
            strict_gate_result=strict_gate_result,
            strict_v1_checklist=checklist,
            warnings=warnings,
            params_at_boundary=boundary_params,
            summary=summary,
        )

    def _find_candidate(self, candidate_name: str) -> dict[str, Any] | None:
        """Find and load a candidate JSON by name."""
        if not self._artifact_dir.exists():
            return None
        target = f"{candidate_name}.json"
        for path in self._artifact_dir.glob("*.json"):
            if path.name == target:
                return self._load_json(path)
        return None

    def _to_detail_response(self, payload: dict[str, Any]) -> CandidateDetailResponse:
        """Map full JSON payload to CandidateDetailResponse."""
        best_trial_raw = payload.get("best_trial")
        best_trial = self._to_trial_item(best_trial_raw) if best_trial_raw else None

        top_trials_raw = payload.get("top_trials") or []
        top_trials = [self._to_trial_item(t) for t in top_trials_raw if isinstance(t, dict)]

        metadata = self._build_metadata(payload)

        return CandidateDetailResponse(
            candidate_name=metadata.candidate_name,
            metadata=metadata,
            best_trial=best_trial,
            top_trials=top_trials,
            fixed_params=payload.get("fixed_params") or {},
            runtime_overrides=payload.get("runtime_overrides") or {},
            constraints=payload.get("constraints") or {},
            resolved_request=payload.get("resolved_request") or {},
            reproduce_cmd=str(payload.get("reproduce_cmd", "")),
            generated_at=metadata.generated_at,
            source_profile=metadata.source_profile,
            git=metadata.git,
            objective=metadata.objective,
            status=metadata.status,
        )

    def _build_metadata(self, payload: dict[str, Any]) -> CandidateMetadata:
        """Build CandidateMetadata from JSON payload."""
        job_data = payload.get("job") or {}
        return CandidateMetadata(
            candidate_name=str(payload.get("candidate_name", "unknown")),
            generated_at=str(payload.get("generated_at", "")),
            source_profile=payload.get("source_profile") or {},
            git=payload.get("git") or {},
            objective=str(job_data.get("objective", "unknown")),
            status=str(payload.get("status", "unknown")),
        )

    def _to_trial_item(self, raw: dict[str, Any]) -> CandidateTrialItem:
        """Map a trial dict to CandidateTrialItem."""
        return CandidateTrialItem(
            trial_number=int(raw.get("trial_number") or 0),
            objective_value=raw.get("objective_value"),
            sharpe_ratio=raw.get("sharpe_ratio"),
            sortino_ratio=raw.get("sortino_ratio"),
            total_return=float(_to_decimal(raw.get("total_return")) or Decimal("0")) if raw.get("total_return") is not None else None,
            max_drawdown=float(_to_decimal(raw.get("max_drawdown")) or Decimal("0")) if raw.get("max_drawdown") is not None else None,
            total_trades=int(raw.get("total_trades") or 0),
            win_rate=raw.get("win_rate"),
            params=raw.get("params") or {},
            completed_at=raw.get("completed_at"),
        )

