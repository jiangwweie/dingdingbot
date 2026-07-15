from __future__ import annotations

from pathlib import Path


def test_revision_124_adds_proof_columns_and_bounded_indexes():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-07-15-124_persist_lifecycle_mutation_enablement_proof.py"
    )
    source = path.read_text(encoding="utf-8")
    assert 'revision: str = "124"' in source
    assert 'down_revision: Union[str, None] = "123"' in source
    assert '"proof_schema"' in source
    assert '"proof_payload"' in source
    assert "idx_brc_runtime_outcome_lane_process_latest" in source
    assert "scope_kind = 'runtime_lane'" in source
    assert "idx_brc_runtime_outcome_canary_window" in source

