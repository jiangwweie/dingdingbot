import pytest

from src.infrastructure import canary_mutation_sentinel_repository as repository
from src.infrastructure.canary_mutation_sentinel_repository import _bounded_scope_ids


def test_bounded_scope_ids_prioritizes_required_references_before_recent_rows():
    selected = _bounded_scope_ids(
        required_ids={"lane-fact-a", "lane-fact-b"},
        recent_ids=["recent-1", "recent-2", "recent-3", "recent-4"],
        limit=4,
        overflow_error="scope_overflow",
    )

    assert selected == {"lane-fact-a", "lane-fact-b", "recent-1", "recent-2"}


def test_bounded_scope_ids_rejects_required_references_above_limit():
    try:
        _bounded_scope_ids(
            required_ids={"required-1", "required-2", "required-3"},
            recent_ids=[],
            limit=2,
            overflow_error="scope_overflow",
        )
    except ValueError as exc:
        assert str(exc) == "scope_overflow"
    else:
        raise AssertionError("required scope overflow must fail closed")


def test_bounded_scope_ids_does_not_add_recent_rows_when_required_scope_is_full():
    selected = _bounded_scope_ids(
        required_ids={"required-1", "required-2"},
        recent_ids=["recent-1", "recent-2"],
        limit=2,
        overflow_error="scope_overflow",
    )

    assert selected == {"required-1", "required-2"}


def test_storage_schema_allows_additive_columns_but_rejects_missing_required_columns(monkeypatch):
    class Inspector:
        def __init__(self, columns):
            self.columns = columns

        def get_columns(self, relation):
            return [{"name": value} for value in self.columns]

    monkeypatch.setattr(repository, "expected_storage_columns", lambda: {"rows": frozenset({"id", "state"})})
    monkeypatch.setattr(repository.sa, "inspect", lambda conn: Inspector({"id", "state", "new_column"}))
    repository._verify_storage_schemas(object())

    monkeypatch.setattr(repository.sa, "inspect", lambda conn: Inspector({"id"}))
    with pytest.raises(ValueError, match="canary_sentinel_storage_schema_mismatch:rows"):
        repository._verify_storage_schemas(object())
