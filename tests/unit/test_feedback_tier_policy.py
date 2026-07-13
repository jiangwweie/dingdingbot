from __future__ import annotations

from pathlib import Path

import pytest

import tests.feedback_tier_plugin as feedback_plugin
import tests.feedback_tier_policy as policy
from tests.feedback_tier_policy import (
    FeedbackEnvironmentError,
    FeedbackTier,
    classify_nodeid,
    preflight_release_postgres,
    selected_for_tier,
    validate_tier_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("nodeid", "expected"),
    [
        (
            "tests/unit/test_execution_sizing.py::test_stop_risk_budget",
            FeedbackTier.FAST,
        ),
        (
            "tests/unit/test_runtime_process_outcome.py::test_outcome",
            FeedbackTier.MAINLINE,
        ),
        (
            "tests/integration/test_new_postgres_boundary.py::test_boundary",
            FeedbackTier.RELEASE,
        ),
        (
            "tests/unit/test_action_time_full_chain_impact.py::"
            "test_each_active_candidate_scope_reaches_mock_real_submit_and_closure_from_raw_pg_input"
            "[MI-001-AVAXUSDT-long]",
            FeedbackTier.RELEASE,
        ),
        (
            "tests/unit/test_action_time_full_chain_impact.py::"
            "test_raw_pg_input_reaches_real_gateway_submit_boundary",
            FeedbackTier.MAINLINE,
        ),
        (
            "external/test_unknown.py::test_unknown",
            FeedbackTier.RELEASE,
        ),
    ],
)
def test_classify_nodeid_uses_conservative_tier_defaults(nodeid, expected):
    assert classify_nodeid(nodeid) is expected


@pytest.mark.parametrize(
    ("selected_tier", "fast", "mainline", "release"),
    [
        (FeedbackTier.FAST, True, False, False),
        (FeedbackTier.MAINLINE, True, True, False),
        (FeedbackTier.RELEASE, True, True, True),
    ],
)
def test_selected_for_tier_is_cumulative(
    selected_tier,
    fast,
    mainline,
    release,
):
    assert selected_for_tier(
        "tests/unit/test_execution_sizing.py::test_fast",
        selected_tier,
    ) is fast
    assert selected_for_tier(
        "tests/unit/test_runtime_process_outcome.py::test_mainline",
        selected_tier,
    ) is mainline
    assert selected_for_tier(
        "tests/integration/test_pg.py::test_release",
        selected_tier,
    ) is release


def test_tier_manifest_matches_current_test_tree():
    assert validate_tier_manifest(REPO_ROOT) == ()


def test_tier_manifest_rejects_release_file_without_matching_sentinel(
    monkeypatch,
):
    monkeypatch.setattr(
        policy,
        "MAINLINE_SENTINELS_BY_FILE",
        {
            "tests/unit/test_action_time_full_chain_impact.py": frozenset(
                {
                    "tests/unit/test_pg_promotion_action_time_lane_materialization.py::"
                    "test_materializes_promotion_lane_budget_protection_and_ticket"
                }
            )
        },
    )

    issues = validate_tier_manifest(REPO_ROOT)

    assert "sentinel_file_mismatch" in issues
    assert "release_file_without_mainline_sentinel" in issues


class _FakeCursor:
    def __init__(self, row=(1,)):
        self.row = row
        self.statements: list[str] = []

    def execute(self, statement: str):
        self.statements.append(statement)
        return self

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_release_postgres_preflight_executes_bounded_select_one():
    calls: list[dict] = []
    cursor = _FakeCursor()

    def connect_fn(**kwargs):
        calls.append(kwargs)
        return _FakeConnection(cursor)

    preflight_release_postgres(
        "postgresql+psycopg://owner:secret@127.0.0.1:5432/postgres",
        connect_fn=connect_fn,
    )

    assert calls == [
        {
            "host": "127.0.0.1",
            "port": 5432,
            "dbname": "postgres",
            "user": "owner",
            "password": "secret",
            "connect_timeout": 3,
        }
    ]
    assert cursor.statements == ["SELECT 1"]


@pytest.mark.parametrize(
    ("raised", "expected_code"),
    [
        (
            ModuleNotFoundError("No module named 'psycopg'"),
            "release_postgres_dependency_missing",
        ),
        (
            RuntimeError("password=do-not-leak"),
            "release_postgres_unavailable",
        ),
    ],
)
def test_release_postgres_preflight_masks_dependency_and_connection_failures(
    raised,
    expected_code,
):
    def connect_fn(**kwargs):
        del kwargs
        raise raised

    with pytest.raises(FeedbackEnvironmentError) as captured:
        preflight_release_postgres(
            "postgresql+psycopg://owner:super-secret@127.0.0.1:5432/postgres",
            connect_fn=connect_fn,
        )

    message = str(captured.value)
    assert expected_code in message
    assert "super-secret" not in message
    assert "do-not-leak" not in message


def test_release_postgres_preflight_masks_invalid_url():
    with pytest.raises(
        FeedbackEnvironmentError,
        match="release_postgres_url_invalid",
    ):
        preflight_release_postgres("not-a-database-url:super-secret")


class _FakeHook:
    def __init__(self):
        self.deselected: list = []

    def pytest_deselected(self, *, items):
        self.deselected.extend(items)


class _FakeConfig:
    def __init__(self, selected_tier):
        self.selected_tier = selected_tier
        self.hook = _FakeHook()

    def getoption(self, name):
        assert name == "test_tier"
        return self.selected_tier


class _FakeItem:
    def __init__(self, nodeid):
        self.nodeid = nodeid
        self.markers: list[str] = []

    def add_marker(self, marker):
        self.markers.append(marker)


def test_pytest_plugin_fast_deselects_non_fast_and_adds_markers(monkeypatch):
    monkeypatch.setattr(
        feedback_plugin,
        "preflight_release_postgres",
        lambda *_args, **_kwargs: pytest.fail("unexpected_preflight"),
    )
    fast = _FakeItem("tests/unit/test_execution_sizing.py::test_fast")
    mainline = _FakeItem(
        "tests/unit/test_runtime_process_outcome.py::test_mainline"
    )
    release = _FakeItem("tests/integration/test_pg.py::test_release")
    items = [fast, mainline, release]
    config = _FakeConfig("fast")

    feedback_plugin.pytest_collection_modifyitems(config, items)

    assert items == [fast]
    assert config.hook.deselected == [mainline, release]
    assert fast.markers == ["feedback_fast", "feedback_mainline"]


def test_pytest_plugin_plain_run_is_release_and_preflights_integration(
    monkeypatch,
):
    calls: list[str | None] = []
    monkeypatch.setattr(
        feedback_plugin,
        "preflight_release_postgres",
        lambda admin_url=None: calls.append(admin_url),
    )
    unit = _FakeItem("tests/unit/test_execution_sizing.py::test_fast")
    integration = _FakeItem(
        "tests/integration/test_runtime_causal_integrity_postgres.py::"
        "test_release"
    )
    items = [unit, integration]
    config = _FakeConfig(None)

    feedback_plugin.pytest_collection_modifyitems(config, items)

    assert items == [unit, integration]
    assert config.hook.deselected == []
    assert calls == [None]
    assert "feedback_release_only" in integration.markers
