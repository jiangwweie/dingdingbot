"""JSONL-backed sink for minimal decision trace events."""

from __future__ import annotations

import json
from pathlib import Path

from src.application.decision_trace import TraceEvent


class JsonlTraceSink:
    """Append trace events as JSON lines."""

    def __init__(self, path: Path | str):
        self._path = Path(path)

    def emit(self, event: TraceEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = event.model_dump(mode="json")
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
