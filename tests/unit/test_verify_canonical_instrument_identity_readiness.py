from __future__ import annotations

import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/verify_canonical_instrument_identity_readiness.py"
)


def test_readiness_certification_requires_six_rules_for_22_active_lanes(
    monkeypatch, capsys
) -> None:
    subject = _load_module()
    identity = SimpleNamespace(exchange_instrument_id="instrument-1")
    targets = tuple(SimpleNamespace(identity=identity) for _ in range(6))
    calls: list[str] = []

    monkeypatch.setattr(subject, "normalize_sync_postgres_dsn", lambda value: value)
    monkeypatch.setattr(subject.sa, "create_engine", lambda _: _FakeEngine((1000, 22)))
    monkeypatch.setattr(
        subject,
        "load_active_instrument_rule_targets",
        lambda *_, **__: targets,
    )
    monkeypatch.setattr(
        subject,
        "load_exact_instrument_identity",
        lambda _, instrument_id: identity,
    )
    monkeypatch.setattr(
        subject,
        "load_current_instrument_rule_snapshot",
        lambda _, *, exchange_instrument_id, **__: calls.append(exchange_instrument_id),
    )

    assert subject.main(["--database-url", "sqlite://", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "canonical_instrument_identity_readiness_certified"
    assert payload["active_lane_count"] == 22
    assert payload["canonical_instrument_count"] == 6
    assert payload["current_v2_rule_count"] == 6
    assert calls == ["instrument-1"] * 6


def test_readiness_certification_rejects_wrong_active_lane_count(monkeypatch) -> None:
    subject = _load_module()
    monkeypatch.setattr(subject, "normalize_sync_postgres_dsn", lambda value: value)
    monkeypatch.setattr(subject.sa, "create_engine", lambda _: _FakeEngine((1000, 21)))
    monkeypatch.setattr(
        subject,
        "load_active_instrument_rule_targets",
        lambda *_, **__: (SimpleNamespace(identity=SimpleNamespace(exchange_instrument_id="instrument-1")),) * 6,
    )

    with pytest.raises(RuntimeError, match="canonical_instrument_readiness_lane_count_invalid"):
        subject.main(["--database-url", "sqlite://", "--json"])


class _FakeResult:
    def __init__(self, value: int):
        self._value = value

    def scalar_one(self) -> int:
        return self._value


class _FakeConnection:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, values: tuple[int, ...]):
        self._values = iter(values)

    def execute(self, *_args, **_kwargs):
        return _FakeResult(next(self._values))


class _FakeEngine:
    def __init__(self, values: tuple[int, ...]):
        self._connection = _FakeConnection(values)

    @contextmanager
    def connect(self):
        yield self._connection

    def dispose(self) -> None:
        return None


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_canonical_instrument_identity_readiness_test_subject", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
