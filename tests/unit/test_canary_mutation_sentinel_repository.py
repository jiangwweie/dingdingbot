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
