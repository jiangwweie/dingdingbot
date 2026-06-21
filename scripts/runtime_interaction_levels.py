"""Shared interaction-level taxonomy for runtime/deploy helper scripts."""

from __future__ import annotations

from typing import Any


INTERACTION_LEVELS: dict[str, dict[str, Any]] = {
    "L0": {
        "rank": 0,
        "owner_label": "本地读取",
        "remote_interaction_allowed": False,
        "remote_mutation_allowed": False,
        "approaches_real_order": False,
        "exchange_write_allowed": False,
        "description": "Local cache, local files, or local computation only.",
    },
    "L1": {
        "rank": 1,
        "owner_label": "只读低交互",
        "remote_interaction_allowed": True,
        "remote_mutation_allowed": False,
        "approaches_real_order": False,
        "exchange_write_allowed": False,
        "description": "Read-only remote checks, deploy plans, and status snapshots.",
    },
    "L2": {
        "rank": 2,
        "owner_label": "非执行演练",
        "remote_interaction_allowed": True,
        "remote_mutation_allowed": False,
        "approaches_real_order": False,
        "exchange_write_allowed": False,
        "description": "Dry-run, mock-signal, and non-executing proof preparation.",
    },
    "L3": {
        "rank": 3,
        "owner_label": "有界服务器变更",
        "remote_interaction_allowed": True,
        "remote_mutation_allowed": True,
        "approaches_real_order": False,
        "exchange_write_allowed": False,
        "description": "Bounded deploy apply, service refresh, or static publish.",
    },
    "L4": {
        "rank": 4,
        "owner_label": "执行前检查",
        "remote_interaction_allowed": True,
        "remote_mutation_allowed": True,
        "approaches_real_order": True,
        "exchange_write_allowed": False,
        "description": "Official action-time FinalGate and Operation Layer readiness.",
    },
    "L5": {
        "rank": 5,
        "owner_label": "官方实盘动作",
        "remote_interaction_allowed": True,
        "remote_mutation_allowed": True,
        "approaches_real_order": True,
        "exchange_write_allowed": True,
        "description": "Official in-boundary tiny real order through Operation Layer.",
    },
}


def interaction_prefix(level: str | None) -> str:
    text = str(level or "").strip()
    if "_" in text:
        text = text.split("_", 1)[0]
    return text if text in INTERACTION_LEVELS else "unknown"


def interaction_rank(level: str | None) -> int:
    return int(INTERACTION_LEVELS.get(interaction_prefix(level), {}).get("rank") or 0)


def interaction_policy(level: str | None) -> dict[str, Any]:
    prefix = interaction_prefix(level)
    policy = dict(INTERACTION_LEVELS.get(prefix) or {})
    if not policy:
        return {
            "level_prefix": "unknown",
            "rank": 0,
            "owner_label": "未知交互",
            "remote_interaction_allowed": False,
            "remote_mutation_allowed": False,
            "approaches_real_order": False,
            "exchange_write_allowed": False,
            "description": "Unknown interaction level.",
        }
    policy["level_prefix"] = prefix
    return policy


def annotate_interaction(interaction: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(interaction)
    level = str(annotated.get("level") or "unknown")
    annotated["policy"] = interaction_policy(level)
    return annotated
