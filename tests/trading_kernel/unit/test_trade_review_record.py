from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.ports import TradeReviewRecord


def _review(**updates: object) -> TradeReviewRecord:
    values = {
        "review_id": "review:ticket-1:v1",
        "ticket_id": "ticket-1",
        "revision": 1,
        "supersedes_review_id": None,
        "outcome": "terminal_flat",
        "metrics": {"net_pnl": "1.0"},
        "decision_impact": {"status": "recorded"},
        "created_at_ms": 2_000,
    }
    values.update(updates)
    return TradeReviewRecord.model_validate(values)


def test_initial_review_has_no_superseded_identity() -> None:
    review = _review()

    assert review.revision == 1
    assert review.supersedes_review_id is None


def test_later_review_requires_superseded_identity() -> None:
    review = _review(
        review_id="review:ticket-1:v2",
        revision=2,
        supersedes_review_id="review:ticket-1:v1",
    )

    assert review.revision == 2
    assert review.supersedes_review_id == "review:ticket-1:v1"


@pytest.mark.parametrize(
    "updates",
    [
        {"revision": 0},
        {"revision": 1, "supersedes_review_id": "review:ticket-1:v0"},
        {"revision": 2, "supersedes_review_id": None},
        {"review_id": ""},
        {"ticket_id": ""},
    ],
)
def test_review_revision_chain_rejects_invalid_identity(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _review(**updates)
