"""One canonical health predicate for PG watcher coverage rows."""

from __future__ import annotations

from typing import Any, Mapping


ACCEPTED_LIVENESS_STATES = frozenset({"healthy", "ok", "active"})


def runtime_coverage_is_healthy(
    coverage: Mapping[str, Any] | None,
    *,
    now_ms: int | None = None,
) -> bool:
    if not coverage:
        return False
    if str(coverage.get("coverage_state") or "") != "covered":
        return False
    if str(coverage.get("liveness_state") or "") not in ACCEPTED_LIVENESS_STATES:
        return False
    if coverage.get("is_current") is not True:
        return False
    return now_ms is None or int(coverage.get("valid_until_ms") or 0) > now_ms
