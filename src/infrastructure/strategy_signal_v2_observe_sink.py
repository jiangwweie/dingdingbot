"""JSONL sidecar sink for observe-only StrategySignalV2 snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_STRATEGY_SIGNAL_V2_OBSERVE_PATH = "logs/runtime/strategy_signal_v2_observe.jsonl"


class StrategySignalV2ObserveSink:
    """Append observe-only StrategySignalV2 snapshots as JSON lines."""

    def __init__(self, path: Path | str = DEFAULT_STRATEGY_SIGNAL_V2_OBSERVE_PATH):
        self._path = Path(path)

    def write(self, snapshot: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
