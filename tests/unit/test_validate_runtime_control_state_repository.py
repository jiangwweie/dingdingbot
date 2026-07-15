from __future__ import annotations

import json

from scripts import validate_runtime_control_state_repository as script


def test_validator_uses_deploy_profile_without_full_control_state(
    monkeypatch,
    capsys,
) -> None:
    calls: list[str] = []

    class FakeRepository:
        def __init__(self, _conn):
            pass

        def read_control_state(self):
            raise AssertionError("deploy validation must not read full control state")

        def read_deploy_validation_state(self):
            calls.append("deploy_validation")
            return {
                "source_mode": "db_backed",
                "projection_target": "production_current",
                "read_profile": "deploy_validation",
                "strategy_group_count": 5,
                "table_counts": {
                    "strategy_side_event_specs": 6,
                    "candidate_scope": 22,
                    "runtime_scope_bindings": 22,
                    "current_projection_ownership": 6,
                },
            }

    class FakeConnection:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        def dispose(self):
            calls.append("disposed")

    monkeypatch.setattr(script.sa, "create_engine", lambda _dsn: FakeEngine())
    monkeypatch.setattr(
        script,
        "PgBackedRuntimeControlStateRepository",
        FakeRepository,
    )

    exit_code = script.main(
        [
            "--database-url",
            "sqlite://",
            "--allow-non-postgres-for-test",
            "--json",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["strategy_group_count"] == 5
    assert calls == ["deploy_validation", "disposed"]
