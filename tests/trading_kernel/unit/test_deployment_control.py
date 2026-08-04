from __future__ import annotations

import pytest

from scripts.trading_kernel.deployment_control import (
    DeploymentDrainBlocked,
    run_deployment_drain,
)


def test_deployment_drain_requests_once_then_observes_flatness() -> None:
    backend = _DrainBackend(["eligible", "in_progress", "flat"])

    run_deployment_drain(
        backend,
        release="/opt/brc/current",
        source_schema_revision="0002_sor_v3_strategy_group_capacity",
        authorization_id="deploy-20260804-01",
        target_commit="a" * 40,
        timeout_seconds=30,
        sleep=lambda _seconds: None,
    )

    assert backend.request_count == 1
    assert backend.inspect_count == 3


def test_deployment_drain_resume_never_creates_a_second_request() -> None:
    backend = _DrainBackend(["in_progress", "flat"])

    run_deployment_drain(
        backend,
        release="/opt/brc/current",
        source_schema_revision="0002_sor_v3_strategy_group_capacity",
        authorization_id="deploy-20260804-01",
        target_commit="a" * 40,
        timeout_seconds=30,
        sleep=lambda _seconds: None,
    )

    assert backend.request_count == 0


def test_deployment_drain_timeout_is_fail_closed() -> None:
    backend = _DrainBackend(["in_progress"])
    clock = _Clock()

    with pytest.raises(DeploymentDrainBlocked, match="timed out"):
        run_deployment_drain(
            backend,
            release="/opt/brc/current",
            source_schema_revision="0002_sor_v3_strategy_group_capacity",
            authorization_id="deploy-20260804-01",
            target_commit="a" * 40,
            timeout_seconds=10,
            clock=clock,
            sleep=clock.advance,
        )

    assert backend.request_count == 0


def test_deployment_drain_blocker_never_requests_exit() -> None:
    backend = _DrainBackend(["blocked"])

    with pytest.raises(DeploymentDrainBlocked, match="blocked"):
        run_deployment_drain(
            backend,
            release="/opt/brc/current",
            source_schema_revision="0002_sor_v3_strategy_group_capacity",
            authorization_id="deploy-20260804-01",
            target_commit="a" * 40,
            timeout_seconds=30,
        )

    assert backend.request_count == 0


class _DrainBackend:
    def __init__(self, statuses: list[str]) -> None:
        self._statuses = statuses
        self.inspect_count = 0
        self.request_count = 0

    def inspect_deployment_drain(self, *_args) -> dict[str, object]:
        index = min(self.inspect_count, len(self._statuses) - 1)
        self.inspect_count += 1
        return {"status": self._statuses[index]}

    def request_deployment_drain(self, *_args) -> dict[str, object]:
        self.request_count += 1
        return {"status": "requested"}


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds
