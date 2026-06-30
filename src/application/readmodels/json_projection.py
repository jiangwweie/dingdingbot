from __future__ import annotations

from typing import Any


def jsonable_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return dict(value)
    payload: dict[str, Any] = {}
    for key in dir(value):
        if key.startswith("_"):
            continue
        attr = getattr(value, key, None)
        if callable(attr):
            continue
        if isinstance(attr, (str, int, float, bool, type(None), list, dict)):
            payload[key] = attr
        else:
            payload[key] = str(attr)
    return payload
