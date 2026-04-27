"""Compare ReadModel — build side-by-side metric comparison from candidate artifacts."""

from __future__ import annotations

from typing import Any, Optional

from src.application.readmodels.candidate_service import CandidateArtifactService
from src.application.readmodels.console_models import CompareResponse, CompareRow


# Core metrics to compare, in display order.
# (display_label, artifact_key)
_COMPARE_METRICS: list[tuple[str, str]] = [
    ("Total Return", "total_return"),
    ("Sharpe", "sharpe_ratio"),
    ("Max Drawdown", "max_drawdown"),
    ("Win Rate", "win_rate"),
    ("Trades", "total_trades"),
]


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val: Any) -> Optional[float]:
    """Return int metrics as float for uniform CompareRow values."""
    if val is None:
        return None
    try:
        return float(int(val))
    except (TypeError, ValueError):
        return None


def _extract_metrics(payload: dict[str, Any] | None) -> dict[str, Optional[float]]:
    """Extract comparable metrics from a candidate artifact payload."""
    if payload is None:
        return {key: None for _, key in _COMPARE_METRICS}

    best_trial = payload.get("best_trial") or {}
    result: dict[str, Optional[float]] = {}
    for _, key in _COMPARE_METRICS:
        raw = best_trial.get(key)
        if key == "total_trades":
            result[key] = _safe_int(raw)
        else:
            result[key] = _safe_float(raw)
    return result


def _compute_diff(baseline: Optional[float], candidate: Optional[float]) -> Optional[float]:
    """Compute relative diff (candidate - baseline). Return None if either is missing."""
    if baseline is None or candidate is None:
        return None
    return round(candidate - baseline, 6)


class CompareReadModel:
    """Build a CompareResponse from candidate artifacts.

    Default strategy (when no explicit refs given):
    - baseline = first candidate in the list (sorted by generated_at desc)
    - candidate_a = second candidate
    - candidate_b = third candidate (optional)
    """

    def __init__(self, artifact_dir: Any = None) -> None:
        self._service = CandidateArtifactService(artifact_dir=artifact_dir)

    def build(
        self,
        *,
        baseline_ref: Optional[str] = None,
        candidate_a: Optional[str] = None,
        candidate_b: Optional[str] = None,
    ) -> CompareResponse:
        candidates = self._service.list_candidates(limit=10)

        if not candidates:
            return CompareResponse()

        names = [c.candidate_name for c in candidates]

        # 1. Resolve baseline
        bl_name = baseline_ref if baseline_ref in names else (names[0] if names else "")

        # 2. Build pool excluding baseline to prevent self-comparison
        pool = [n for n in names if n != bl_name]

        # 3. Resolve candidate_a — explicit wins, but reject if same as baseline
        if candidate_a and candidate_a != bl_name and candidate_a in names:
            ca_name = candidate_a
        elif candidate_a and candidate_a == bl_name:
            # Explicit request to compare baseline with itself — decline
            ca_name = pool[0] if pool else ""
        else:
            ca_name = pool[0] if pool else ""

        # 4. Resolve candidate_b — must differ from both baseline and candidate_a
        pool_after_a = [n for n in pool if n != ca_name]
        if candidate_b and candidate_b != bl_name and candidate_b != ca_name and candidate_b in names:
            cb_name = candidate_b
        elif candidate_b and (candidate_b == bl_name or candidate_b == ca_name):
            # Explicit request for duplicate — decline
            cb_name = pool_after_a[0] if pool_after_a else None
        else:
            cb_name = pool_after_a[0] if pool_after_a else None

        # Load full payloads for metric extraction
        bl_payload = self._service._find_candidate(bl_name) if bl_name else None
        ca_payload = self._service._find_candidate(ca_name) if ca_name else None
        cb_payload = self._service._find_candidate(cb_name) if cb_name else None

        bl_metrics = _extract_metrics(bl_payload)
        ca_metrics = _extract_metrics(ca_payload)
        cb_metrics = _extract_metrics(cb_payload)

        rows: list[CompareRow] = []
        for label, key in _COMPARE_METRICS:
            bl_val = bl_metrics.get(key)
            ca_val = ca_metrics.get(key)
            cb_val = cb_metrics.get(key) if cb_name else None

            rows.append(CompareRow(
                metric=label,
                baseline=bl_val,
                candidate_a=ca_val,
                candidate_b=cb_val,
                diff_a=_compute_diff(bl_val, ca_val),
                diff_b=_compute_diff(bl_val, cb_val) if cb_name else None,
            ))

        return CompareResponse(
            baseline_label=bl_name,
            candidate_a_label=ca_name,
            candidate_b_label=cb_name,
            rows=rows,
        )
