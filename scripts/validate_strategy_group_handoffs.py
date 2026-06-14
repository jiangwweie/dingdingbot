#!/usr/bin/env python3
"""Validate Strategy Group Handoff Pack JSON files.

The validator is intentionally local and read-only. It checks that research
handoff packs expose the stable main-control contract without implying runtime
registration or execution authority.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL_FIELDS = (
    "strategy_group_id",
    "version",
    "supported_symbols",
    "supported_sides",
    "signal_ready_rule",
    "required_facts",
    "risk_defaults",
    "hard_stops",
    "sample_signal_packet",
    "sample_no_signal_packet",
)

RECOMMENDED_PACKET_FIELDS = (
    "sample_stale_signal_packet",
    "sample_conflict_packet",
)

SIGNAL_READY_FIELDS = (
    "status_name",
    "freshness_window_seconds",
    "must_include",
    "stale_behavior",
    "conflict_behavior",
)

SAMPLE_PACKET_FIELDS = (
    "packet_type",
    "strategy_group_id",
    "strategy_group_version",
    "status",
    "generated_at",
    "symbol",
    "direction",
    "candidate_prepare_allowed_by_research",
    "execution_allowed_by_research",
)

EXECUTION_BOUNDARY_FALSE_FIELDS = (
    "runtime_registration",
    "exchange_write",
    "order_intent",
    "final_gate_authority",
    "operation_layer_authority",
    "order_lifecycle_authority",
    "order_sizing_authority",
)


@dataclass(frozen=True)
class ValidationResult:
    group_id: str
    json_path: Path
    markdown_path: Path
    symbols_count: int
    sides: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _warn(condition: bool, warnings: list[str], message: str) -> None:
    if not condition:
        warnings.append(message)


def validate_handoff(json_path: Path) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ValidationResult(
            group_id=json_path.parent.name,
            json_path=json_path,
            markdown_path=json_path.with_suffix(".md"),
            symbols_count=0,
            sides=(),
            errors=(f"invalid JSON: {exc}",),
            warnings=(),
        )

    group_id = str(payload.get("strategy_group_id") or json_path.parent.name)
    markdown_path = json_path.with_suffix(".md")

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        _require(field in payload, errors, f"missing required field: {field}")

    for field in RECOMMENDED_PACKET_FIELDS:
        _warn(field in payload, warnings, f"missing recommended field: {field}")

    _require(markdown_path.exists(), errors, f"missing paired Markdown file: {markdown_path}")
    _require(payload.get("strategy_group_id") == json_path.parent.name, errors, "strategy_group_id must match directory name")
    _require(bool(payload.get("version")), errors, "version must be non-empty")

    symbols = _as_list(payload.get("supported_symbols"))
    sides = _as_list(payload.get("supported_sides"))
    hard_stops = _as_list(payload.get("hard_stops"))

    _require(bool(symbols), errors, "supported_symbols must be a non-empty list")
    _require(all(isinstance(item, str) and item for item in symbols), errors, "supported_symbols must contain non-empty strings")
    _require(bool(sides), errors, "supported_sides must be a non-empty list")
    _require(all(isinstance(item, str) and item for item in sides), errors, "supported_sides must contain non-empty strings")
    _require(bool(hard_stops), errors, "hard_stops must be a non-empty list")

    signal_ready_rule = payload.get("signal_ready_rule")
    _require(isinstance(signal_ready_rule, dict), errors, "signal_ready_rule must be an object")
    if isinstance(signal_ready_rule, dict):
        for field in SIGNAL_READY_FIELDS:
            _require(field in signal_ready_rule, errors, f"signal_ready_rule missing field: {field}")
        _require(
            isinstance(signal_ready_rule.get("freshness_window_seconds"), int)
            and signal_ready_rule.get("freshness_window_seconds", 0) > 0,
            errors,
            "signal_ready_rule.freshness_window_seconds must be a positive integer",
        )

    required_facts = payload.get("required_facts")
    _require(isinstance(required_facts, dict), errors, "required_facts must be an object")
    if isinstance(required_facts, dict):
        _require(bool(required_facts), errors, "required_facts must not be empty")
        _warn("account" in required_facts, warnings, "required_facts.account is recommended for main-control readiness")
        _warn("exchange" in required_facts, warnings, "required_facts.exchange is recommended for main-control readiness")

    risk_defaults = payload.get("risk_defaults")
    _require(isinstance(risk_defaults, dict), errors, "risk_defaults must be an object")
    if isinstance(risk_defaults, dict):
        interpretation = str(risk_defaults.get("interpretation", ""))
        _require(
            "research_proposal_only" in interpretation,
            errors,
            "risk_defaults.interpretation must declare research_proposal_only",
        )

    execution_boundary = payload.get("execution_boundary", {})
    if isinstance(execution_boundary, dict):
        for field in EXECUTION_BOUNDARY_FALSE_FIELDS:
            _require(execution_boundary.get(field) is not True, errors, f"execution_boundary.{field} must not be true")
    else:
        errors.append("execution_boundary must be an object when present")

    expected_packet_group_id = payload.get("strategy_group_id")
    expected_packet_version = payload.get("version")
    for packet_field in ("sample_signal_packet", "sample_no_signal_packet"):
        packet = payload.get(packet_field)
        _require(isinstance(packet, dict), errors, f"{packet_field} must be an object")
        if not isinstance(packet, dict):
            continue
        for field in SAMPLE_PACKET_FIELDS:
            _require(field in packet, errors, f"{packet_field} missing field: {field}")
        _require(packet.get("strategy_group_id") == expected_packet_group_id, errors, f"{packet_field}.strategy_group_id mismatch")
        _require(packet.get("strategy_group_version") == expected_packet_version, errors, f"{packet_field}.strategy_group_version mismatch")
        _require(packet.get("execution_allowed_by_research") is False, errors, f"{packet_field}.execution_allowed_by_research must be false")

    return ValidationResult(
        group_id=group_id,
        json_path=json_path,
        markdown_path=markdown_path,
        symbols_count=len(symbols),
        sides=tuple(str(side) for side in sides),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def discover_handoffs(base_dir: Path) -> list[Path]:
    return sorted(path for path in base_dir.glob("*/handoff.json") if path.is_file())


def render_markdown(results: list[ValidationResult]) -> str:
    total = len(results)
    passed = sum(1 for result in results if result.ok)
    lines = [
        "# Strategy Group Handoff Validation Report",
        "",
        f"Validated handoffs: `{total}`",
        f"Passed: `{passed}`",
        f"Failed: `{total - passed}`",
        "",
        "| Strategy Group | Status | Symbols | Sides | Warnings |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        lines.append(
            f"| `{result.group_id}` | `{status}` | `{result.symbols_count}` | "
            f"`{','.join(result.sides)}` | `{len(result.warnings)}` |"
        )

    failed = [result for result in results if not result.ok]
    if failed:
        lines.extend(["", "## Errors", ""])
        for result in failed:
            lines.append(f"### `{result.group_id}`")
            for error in result.errors:
                lines.append(f"- {error}")

    warnings = [result for result in results if result.warnings]
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for result in warnings:
            lines.append(f"### `{result.group_id}`")
            for warning in result.warnings:
                lines.append(f"- {warning}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("docs/strategy-research/strategy-group-handoffs"),
        help="Directory containing */handoff.json packs.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print a Markdown validation report instead of terse lines.",
    )
    args = parser.parse_args()

    handoffs = discover_handoffs(args.base_dir)
    results = [validate_handoff(path) for path in handoffs]

    if args.markdown:
        print(render_markdown(results), end="")
    else:
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            print(
                f"{status} {result.group_id} "
                f"symbols={result.symbols_count} sides={','.join(result.sides)} "
                f"errors={len(result.errors)} warnings={len(result.warnings)}"
            )
            for error in result.errors:
                print(f"  ERROR {error}")
            for warning in result.warnings:
                print(f"  WARN {warning}")

    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
