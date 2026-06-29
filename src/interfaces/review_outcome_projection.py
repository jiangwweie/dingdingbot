from __future__ import annotations

from typing import Any

from src.application.readmodels.json_projection import jsonable_mapping


def review_outcome_storage_projection(
    value: Any,
    *,
    result_source_role: str | None = None,
) -> dict[str, Any]:
    payload = jsonable_mapping(value)
    storage_decision = payload.pop("decision", None)
    if "review_outcome" not in payload:
        payload["review_outcome"] = storage_decision
    if result_source_role is not None:
        payload["result_source_role"] = result_source_role
    return payload
