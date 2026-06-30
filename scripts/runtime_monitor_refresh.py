"""Shared monitor-refresh classification helpers for runtime monitor scripts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


MONITOR_REFRESH_STATUS = "waiting_for_market_monitor_refresh_needed"
DEPLOYMENT_ISSUE_STATUS = "temporarily_unavailable_deployment_issue"
TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS = (
    "temporarily_unavailable_monitor_refresh_needed"
)


@dataclass(frozen=True)
class MonitorRefreshClassification:
    monitor_status: str
    refresh_needed: bool
    deployment_issue: bool
    reasons: list[str]


@dataclass(frozen=True)
class OwnerRuntimeStateProjection:
    runtime_status: str
    monitor_status: str
    owner_status: str
    owner_intervention_required: bool
    monitor_refresh_needed: bool
    monitor_refresh_reasons: list[str]
    waiting_for_market: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "runtime_status": self.runtime_status,
            "monitor_status": self.monitor_status,
            "owner_status": self.owner_status,
            "owner_intervention_required": self.owner_intervention_required,
            "monitor_refresh_needed": self.monitor_refresh_needed,
            "monitor_refresh_reasons": self.monitor_refresh_reasons,
            "waiting_for_market": self.waiting_for_market,
        }


@dataclass(frozen=True)
class MonitorStatusProjection:
    runtime_status: str
    monitor_status: str
    owner_status: str
    owner_runtime_state: dict[str, Any]
    monitor_refresh_needed: bool
    monitor_refresh_reasons: list[str]


@dataclass(frozen=True)
class MonitorRefreshGateProjection:
    status: str
    runtime_status: str
    monitor_status: str
    owner_status: str
    owner_runtime_state: dict[str, Any]
    visibility: dict[str, Any]
    notification: dict[str, Any]


@dataclass(frozen=True)
class OwnerRuntimeIssuesProjection:
    blockers: list[str]
    non_market_gaps: list[Any]

    def as_dict(
        self,
        *,
        include_counts: bool = False,
        gap_key: str = "non_market_gaps",
        gap_count_key: str = "non_market_gap_count",
    ) -> dict[str, Any]:
        projection = {
            "blockers": list(self.blockers),
            gap_key: list(self.non_market_gaps),
        }
        if include_counts:
            projection["blocker_count"] = len(self.blockers)
            projection[gap_count_key] = len(self.non_market_gaps)
        return projection


def owner_runtime_state_projection(
    *,
    runtime_status: str,
    monitor_status: str,
    owner_status: str,
    owner_intervention_required: bool,
    monitor_refresh_needed: bool,
    monitor_refresh_reasons: list[str],
    waiting_for_market: bool,
) -> dict[str, Any]:
    return OwnerRuntimeStateProjection(
        runtime_status=runtime_status,
        monitor_status=monitor_status,
        owner_status=owner_status,
        owner_intervention_required=owner_intervention_required,
        monitor_refresh_needed=monitor_refresh_needed,
        monitor_refresh_reasons=_dedupe_text(monitor_refresh_reasons),
        waiting_for_market=waiting_for_market,
    ).as_dict()


def monitor_refresh_needed_for_status(monitor_status: str) -> bool:
    return monitor_status in {"needs_refresh", "deployment_issue"}


def monitor_owner_runtime_state(
    *,
    runtime_status: str,
    monitor_status: str,
    owner_status: str,
    owner_intervention_required: bool,
    waiting_for_market: bool,
    monitor_refresh_reasons: list[str] | None = None,
    monitor_refresh_needed: bool | None = None,
) -> dict[str, Any]:
    refresh_needed = (
        monitor_refresh_needed
        if monitor_refresh_needed is not None
        else monitor_refresh_needed_for_status(monitor_status)
    )
    return owner_runtime_state_projection(
        runtime_status=runtime_status,
        monitor_status=monitor_status,
        owner_status=owner_status,
        owner_intervention_required=owner_intervention_required,
        monitor_refresh_needed=refresh_needed,
        monitor_refresh_reasons=monitor_refresh_reasons or [],
        waiting_for_market=waiting_for_market,
    )


def artifact_declared_runtime_status(artifact: dict[str, Any]) -> str:
    if not isinstance(artifact, dict):
        return ""
    explicit = str(artifact.get("runtime_status") or "")
    if explicit:
        return explicit
    owner_runtime_state = _artifact_dict(artifact, "owner_runtime_state")
    return str(owner_runtime_state.get("runtime_status") or "")


def first_artifact_declared_runtime_status(
    artifacts: Iterable[dict[str, Any]],
) -> str:
    for artifact in artifacts:
        runtime_status = artifact_declared_runtime_status(artifact)
        if runtime_status:
            return runtime_status
    return ""


def artifact_owner_intervention_required(artifact: dict[str, Any]) -> bool:
    if not isinstance(artifact, dict):
        return False
    if artifact.get("owner_intervention_required") is True:
        return True
    for key in ("owner_summary", "owner_state", "owner_runtime_state", "notification"):
        section = _artifact_dict(artifact, key)
        if section.get("owner_intervention_required") is True:
            return True
    return False


def owner_intervention_required_from_sources(
    *,
    artifacts: Iterable[dict[str, Any]],
    execution_blockers: Iterable[str] = (),
    engineering_gaps: Iterable[Any] = (),
) -> bool:
    if any(artifact_owner_intervention_required(artifact) for artifact in artifacts):
        return True
    owner_tokens = (
        "owner_policy",
        "owner_intervention",
        "capital_adjustment",
        "pause_policy",
        "risk_acceptance",
    )
    for item in [*execution_blockers, *[str(gap) for gap in engineering_gaps]]:
        lowered = str(item).lower()
        if any(token in lowered for token in owner_tokens):
            return True
    return False


def combined_artifact_monitor_refresh_reasons(
    artifacts: Iterable[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    for artifact in artifacts:
        reasons.extend(artifact_monitor_refresh_reasons(artifact))
    return _dedupe_text(reasons)


def monitor_status_projection(
    *,
    status: str,
    artifacts: Iterable[dict[str, Any]] = (),
    runtime_status: str | None = None,
    monitor_status: str | None = None,
    owner_status: str | None = None,
    owner_intervention_required: bool = False,
    waiting_for_market: bool | None = None,
    monitor_refresh_reasons: list[str] | None = None,
    monitor_refresh_needed: bool | None = None,
    default_runtime_status: str = "temporarily_unavailable",
    default_monitor_status: str = "unknown",
) -> MonitorStatusProjection:
    artifact_list = [artifact for artifact in artifacts if isinstance(artifact, dict)]
    resolved_monitor_status = monitor_status or combined_artifact_monitor_status(
        status=status,
        artifacts=artifact_list,
        default_status="",
    )
    if not resolved_monitor_status:
        resolved_monitor_status = default_monitor_status

    resolved_reasons = (
        _dedupe_text(monitor_refresh_reasons)
        if monitor_refresh_reasons is not None
        else combined_artifact_monitor_refresh_reasons(artifact_list)
    )
    refresh_needed = (
        monitor_refresh_needed
        if monitor_refresh_needed is not None
        else (
            monitor_refresh_needed_for_status(resolved_monitor_status)
            or any(
                classify_artifact_monitor_refresh(artifact).refresh_needed
                for artifact in artifact_list
            )
        )
    )

    artifact_runtime_status = first_artifact_declared_runtime_status(artifact_list)
    resolved_runtime_status = runtime_status or artifact_runtime_status
    resolved_waiting_for_market = (
        waiting_for_market
        if waiting_for_market is not None
        else resolved_runtime_status == "waiting_for_market"
    )
    if not resolved_runtime_status:
        resolved_runtime_status = monitor_runtime_status_for(
            status=status,
            waiting_for_market=resolved_waiting_for_market,
            default_status=default_runtime_status,
        )
    if waiting_for_market is None:
        resolved_waiting_for_market = resolved_runtime_status == "waiting_for_market"

    resolved_owner_status = owner_status or monitor_owner_status_for(
        runtime_status=resolved_runtime_status,
        monitor_status=resolved_monitor_status,
        owner_intervention_required=owner_intervention_required,
    )
    owner_runtime_state = monitor_owner_runtime_state(
        runtime_status=resolved_runtime_status,
        monitor_status=resolved_monitor_status,
        owner_status=resolved_owner_status,
        owner_intervention_required=owner_intervention_required,
        waiting_for_market=resolved_waiting_for_market,
        monitor_refresh_reasons=resolved_reasons,
        monitor_refresh_needed=refresh_needed,
    )
    return MonitorStatusProjection(
        runtime_status=resolved_runtime_status,
        monitor_status=resolved_monitor_status,
        owner_status=resolved_owner_status,
        owner_runtime_state=owner_runtime_state,
        monitor_refresh_needed=bool(owner_runtime_state["monitor_refresh_needed"]),
        monitor_refresh_reasons=list(owner_runtime_state["monitor_refresh_reasons"]),
    )


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def monitor_refresh_reasons_from_mapping(values: dict[str, Any]) -> list[str]:
    return [str(item) for item in values.get("monitor_refresh_reasons") or []]


def monitor_refresh_notification_reason(values: dict[str, Any]) -> str:
    reasons = monitor_refresh_reasons_from_mapping(values)
    if reasons:
        return reasons[0]
    return "runtime_monitor_refresh_needed"


def monitor_notification_projection(
    *,
    monitor_refresh_needed: bool,
    owner_notify: bool,
    owner_intervention_required: bool,
    monitor_refresh_reasons: Iterable[str] = (),
    source_notification: Mapping[str, Any] | None = None,
    source_prefix: str | None = None,
    include_monitor_refresh_fields: bool = False,
) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "refresh_required": bool(monitor_refresh_needed),
        "automation_notify": bool(monitor_refresh_needed),
        "owner_notify": bool(owner_notify),
        "owner_intervention_required": bool(owner_intervention_required),
    }
    if source_notification and source_prefix:
        projection[f"{source_prefix}_notification_result"] = source_notification.get(
            "notification_result"
        )
        projection[f"{source_prefix}_reason"] = source_notification.get("reason")
    if include_monitor_refresh_fields:
        projection["monitor_refresh_needed"] = bool(monitor_refresh_needed)
        projection["monitor_refresh_reasons"] = _dedupe_text(
            [str(item) for item in monitor_refresh_reasons]
        )
    return projection


def monitor_refresh_gate_projection(
    *,
    runtime_status: str,
    reason: str,
    detail: str,
) -> MonitorRefreshGateProjection:
    monitor_status = "needs_refresh"
    owner_status = monitor_owner_status_for(
        runtime_status=runtime_status,
        monitor_status=monitor_status,
    )
    status = (
        MONITOR_REFRESH_STATUS
        if runtime_status == "waiting_for_market"
        else TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS
    )
    owner_state_label = monitor_owner_state_label(status) or "监控状态需刷新"
    owner_action_label = (
        monitor_owner_action_label(status) or "刷新本地 runtime monitor 缓存"
    )
    monitor_refresh_reasons = [str(reason)]
    return MonitorRefreshGateProjection(
        status=status,
        runtime_status=runtime_status,
        monitor_status=monitor_status,
        owner_status=owner_status,
        owner_runtime_state=monitor_owner_runtime_state(
            runtime_status=runtime_status,
            monitor_status=monitor_status,
            owner_status=owner_status,
            owner_intervention_required=False,
            waiting_for_market=runtime_status == "waiting_for_market",
            monitor_refresh_reasons=monitor_refresh_reasons,
            monitor_refresh_needed=True,
        ),
        visibility={
            "category": "monitor_refresh",
            "label": owner_state_label,
            "detail": detail,
            "non_authority_checkpoint": owner_action_label,
            "owner_intervention_required": False,
        },
        notification={
            "notification_result": "NOTIFY",
            "reason": str(reason),
            "message": detail,
            "refresh_required": True,
            "monitor_refresh_needed": True,
            "monitor_refresh_reasons": monitor_refresh_reasons,
            "automation_notify": True,
            "owner_notify": False,
            "owner_intervention_required": False,
        },
    )


def owner_runtime_issues_projection(
    *,
    blockers: Iterable[Any] = (),
    non_market_gaps: Iterable[Any] = (),
    include_counts: bool = False,
    gap_key: str = "non_market_gaps",
    gap_count_key: str = "non_market_gap_count",
) -> dict[str, Any]:
    return OwnerRuntimeIssuesProjection(
        blockers=[str(item) for item in blockers],
        non_market_gaps=list(non_market_gaps),
    ).as_dict(
        include_counts=include_counts,
        gap_key=gap_key,
        gap_count_key=gap_count_key,
    )


def _artifact_dict(artifact: dict[str, Any], key: str) -> dict[str, Any]:
    section = artifact.get(key)
    return section if isinstance(section, dict) else {}


def artifact_owner_runtime_issues(artifact: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return owner_runtime_issues_projection()
    owner_runtime_issues = _artifact_dict(artifact, "owner_runtime_issues")
    legacy_checks = _artifact_dict(artifact, "checks")
    blockers = owner_runtime_issues.get("blockers", legacy_checks.get("blockers"))
    non_market_gaps = owner_runtime_issues.get(
        "non_market_gaps",
        legacy_checks.get("non_market_gaps"),
    )
    return owner_runtime_issues_projection(
        blockers=blockers or [],
        non_market_gaps=non_market_gaps or [],
    )


def artifact_monitor_refresh_reasons(artifact: dict[str, Any]) -> list[str]:
    if not isinstance(artifact, dict):
        return []
    notification = _artifact_dict(artifact, "notification")
    if "monitor_refresh_reasons" in notification:
        return [str(item) for item in notification.get("monitor_refresh_reasons") or []]
    owner_runtime_state = _artifact_dict(artifact, "owner_runtime_state")
    if "monitor_refresh_reasons" in owner_runtime_state:
        return [
            str(item)
            for item in owner_runtime_state.get("monitor_refresh_reasons") or []
        ]
    return []


def monitor_owner_state_label(status: str) -> str:
    if status in {"waiting_for_market", MONITOR_REFRESH_STATUS}:
        return "等待机会"
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "暂不可用"
    if status in {"needs_refresh", TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS}:
        return "监控状态需刷新"
    return ""


def monitor_owner_action_label(status: str) -> str:
    if status == "waiting_for_market":
        return "继续等待市场机会"
    if status in {
        MONITOR_REFRESH_STATUS,
        "needs_refresh",
        TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS,
    }:
        return "刷新本地 runtime monitor 缓存"
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "刷新或修复 runtime monitor 权威状态"
    return ""


def monitor_owner_state_label_for(
    status: str,
    *,
    local_labels: Mapping[str, str],
    default_label: str,
) -> str:
    shared_label = monitor_owner_state_label(status)
    if shared_label:
        return shared_label
    return local_labels.get(status, default_label)


def monitor_owner_action_label_for(
    status: str,
    *,
    local_labels: Mapping[str, str],
    default_label: str,
) -> str:
    shared_label = monitor_owner_action_label(status)
    if shared_label:
        return shared_label
    return local_labels.get(status, default_label)


def monitor_runtime_status_for(
    *,
    status: str,
    waiting_for_market: bool = False,
    default_status: str = "temporarily_unavailable",
) -> str:
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "temporarily_unavailable"
    if waiting_for_market or status == "waiting_for_market":
        return "waiting_for_market"
    if status == "processing":
        return "processing"
    if status in {"ready", "running"}:
        return "running"
    if status in {"complete", "completed"}:
        return "completed"
    if status in {
        "blocked",
        "degraded",
        TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS,
    }:
        return "temporarily_unavailable"
    return default_status


def monitor_owner_status_for(
    *,
    runtime_status: str,
    monitor_status: str,
    owner_intervention_required: bool = False,
    default_status: str = "temporarily_unavailable",
) -> str:
    if owner_intervention_required:
        return "needs_intervention"
    if runtime_status == "waiting_for_market":
        return "waiting_for_opportunity"
    if runtime_status == "processing":
        return "processing"
    if runtime_status == "completed":
        return "completed"
    if runtime_status == "running":
        return "running"
    if runtime_status == "temporarily_unavailable":
        return "temporarily_unavailable"
    if monitor_status == "deployment_issue":
        return "temporarily_unavailable"
    return default_status


def artifact_monitor_status(artifact: dict[str, Any]) -> str:
    if not isinstance(artifact, dict):
        return ""
    status = str(artifact.get("status") or "")
    if status in {
        "needs_refresh",
        MONITOR_REFRESH_STATUS,
        TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS,
    }:
        return "needs_refresh"
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "deployment_issue"
    explicit = str(artifact.get("monitor_status") or "")
    if explicit:
        return explicit
    owner_runtime_state = _artifact_dict(artifact, "owner_runtime_state")
    explicit = str(owner_runtime_state.get("monitor_status") or "")
    if explicit:
        return explicit
    checks = _artifact_dict(artifact, "checks")
    if checks.get("deployment_issue") is True:
        return "deployment_issue"
    return ""


def artifact_monitor_refresh_needed(artifact: dict[str, Any]) -> bool:
    if not isinstance(artifact, dict):
        return False
    monitor_status = artifact_monitor_status(artifact)
    if monitor_status in {"needs_refresh", "deployment_issue"}:
        return True
    notification = _artifact_dict(artifact, "notification")
    if "monitor_refresh_needed" in notification:
        return notification.get("monitor_refresh_needed") is True
    owner_runtime_state = _artifact_dict(artifact, "owner_runtime_state")
    if "monitor_refresh_needed" in owner_runtime_state:
        return owner_runtime_state.get("monitor_refresh_needed") is True
    return False


def monitor_step_returncode_is_refresh(
    *,
    step_name: str,
    returncode: int,
    artifact: dict[str, Any],
    monitored_steps: Iterable[str] = ("daily_check", "goal_progress"),
) -> bool:
    if step_name not in set(monitored_steps):
        return False
    if int(returncode or 0) == 0:
        return False
    blockers = artifact_owner_runtime_issues(artifact)["blockers"]
    return artifact_monitor_refresh_needed(artifact) and not blockers


def monitor_step_returncode_is_deployment_issue(
    *,
    step_name: str,
    returncode: int,
    artifact: dict[str, Any],
    monitored_steps: Iterable[str] = ("daily_check", "goal_progress"),
) -> bool:
    if step_name not in set(monitored_steps):
        return False
    if int(returncode or 0) == 0:
        return False
    return artifact_monitor_status(artifact) == "deployment_issue" or str(
        artifact.get("status") or ""
    ) == DEPLOYMENT_ISSUE_STATUS


def classify_artifact_monitor_refresh(
    artifact: dict[str, Any],
) -> MonitorRefreshClassification:
    monitor_status = artifact_monitor_status(artifact)
    return MonitorRefreshClassification(
        monitor_status=monitor_status,
        refresh_needed=artifact_monitor_refresh_needed(artifact),
        deployment_issue=monitor_status == "deployment_issue",
        reasons=artifact_monitor_refresh_reasons(artifact),
    )


def monitor_refresh_sequence_status(
    artifacts: Iterable[dict[str, Any]],
    *,
    waiting_status: str = MONITOR_REFRESH_STATUS,
    unavailable_status: str = TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS,
) -> str:
    artifact_list = [artifact for artifact in artifacts if isinstance(artifact, dict)]
    if not any(artifact_monitor_refresh_needed(artifact) for artifact in artifact_list):
        return ""
    if any(
        artifact_declared_runtime_status(artifact) == "waiting_for_market"
        for artifact in artifact_list
    ):
        return waiting_status
    return unavailable_status


def combined_artifact_monitor_status(
    *,
    status: str,
    artifacts: list[dict[str, Any]],
    default_status: str = "unknown",
) -> str:
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "deployment_issue"

    monitor_statuses: list[str] = []
    for artifact in artifacts:
        classification = classify_artifact_monitor_refresh(artifact)
        monitor_status = classification.monitor_status
        if monitor_status:
            monitor_statuses.append(monitor_status)
        if classification.deployment_issue:
            return "deployment_issue"
        if classification.refresh_needed:
            return "needs_refresh"

    if status in {"needs_refresh", TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS}:
        return "needs_refresh"
    if "fresh" in monitor_statuses:
        return "fresh"
    return default_status
