"""Pytest hooks for deterministic developer feedback tiers."""

from __future__ import annotations

import os

import pytest

from tests.feedback_tier_policy import (
    FeedbackEnvironmentError,
    FeedbackTier,
    marker_names_for_nodeid,
    preflight_release_postgres,
    selected_for_tier,
)


POSTGRES_CERTIFICATION_PREFIX = (
    "tests/integration/test_runtime_causal_integrity_postgres.py::"
)


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--test-tier",
        action="store",
        dest="test_tier",
        choices=tuple(tier.value for tier in FeedbackTier),
        default=None,
        help="Run fast, mainline, or complete release feedback tier.",
    )


def pytest_collection_modifyitems(config, items) -> None:
    selected_tier = FeedbackTier(
        config.getoption("test_tier") or FeedbackTier.RELEASE.value
    )
    selected = []
    deselected = []
    for item in items:
        for marker_name in marker_names_for_nodeid(item.nodeid):
            item.add_marker(marker_name)
        if selected_for_tier(item.nodeid, selected_tier):
            selected.append(item)
        else:
            deselected.append(item)
    if selected_tier is FeedbackTier.RELEASE and any(
        item.nodeid.startswith(POSTGRES_CERTIFICATION_PREFIX)
        for item in selected
    ):
        try:
            preflight_release_postgres(
                os.environ.get("BRC_TEST_POSTGRES_ADMIN_URL")
            )
        except FeedbackEnvironmentError as exc:
            raise pytest.UsageError(str(exc)) from exc
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected
