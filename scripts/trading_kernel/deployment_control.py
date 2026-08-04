"""Pure control-plane sequencing for one optional Deployment Drain."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Protocol


class DeploymentDrainBlocked(RuntimeError):
    """Drain state cannot safely progress to a flat cutover."""


class DeploymentDrainBackend(Protocol):
    def inspect_deployment_drain(
        self,
        release: str,
        source_schema_revision: str,
        target_commit: str,
    ) -> Mapping[str, object]: ...

    def request_deployment_drain(
        self,
        release: str,
        source_schema_revision: str,
        authorization_id: str,
        target_commit: str,
    ) -> Mapping[str, object]: ...


def run_deployment_drain(
    backend: DeploymentDrainBackend,
    *,
    release: str,
    source_schema_revision: str,
    authorization_id: str,
    target_commit: str,
    timeout_seconds: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Request at most once, then observe the source runtime until flat."""

    if timeout_seconds <= 0:
        raise ValueError("Deployment Drain timeout must be positive")
    deadline = clock() + timeout_seconds
    requested = False
    while True:
        state = backend.inspect_deployment_drain(
            release,
            source_schema_revision,
            target_commit,
        )
        status = _status(state)
        if status == "flat":
            return
        if status == "blocked":
            raise DeploymentDrainBlocked("Deployment Drain source state is blocked")
        if status == "eligible" and not requested:
            result = backend.request_deployment_drain(
                release,
                source_schema_revision,
                authorization_id,
                target_commit,
            )
            if _status(result) not in {"requested", "in_progress", "flat"}:
                raise DeploymentDrainBlocked(
                    "Deployment Drain request did not enter a safe state"
                )
            requested = True
            continue
        if status not in {"eligible", "in_progress"}:
            raise DeploymentDrainBlocked("Deployment Drain status is invalid")
        remaining = deadline - clock()
        if remaining <= 0:
            raise DeploymentDrainBlocked("Deployment Drain timed out before flatness")
        sleep(min(5.0, remaining))


def _status(payload: Mapping[str, object]) -> str:
    return str(payload.get("status", "")).strip()
