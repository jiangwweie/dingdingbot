"""Paper-only observation packets for Personal Leveraged Campaign previews."""

from __future__ import annotations

from typing import Any

from src.domain.personal_campaign import (
    PaperObservationPacket,
    PaperObservationReviewStatus,
    ReadOnlyRuntimeAdapterPreview,
)


def build_paper_observation_packet(
    *,
    preview: ReadOnlyRuntimeAdapterPreview,
    created_at_ms: int,
    operator_notes: list[str] | None = None,
    review_status: PaperObservationReviewStatus = PaperObservationReviewStatus.PENDING_REVIEW,
    reviewed_by: str | None = None,
    reviewed_at_ms: int | None = None,
) -> PaperObservationPacket:
    """Wrap a read-only runtime preview in a paper-only observation packet."""

    packet_id = f"paper-{preview.strategy_contract_id}-{preview.source_snapshot_id}"
    return PaperObservationPacket(
        packet_id=packet_id,
        created_at_ms=created_at_ms,
        preview=preview,
        review_status=review_status,
        operator_notes=operator_notes or [],
        reviewed_by=reviewed_by,
        reviewed_at_ms=reviewed_at_ms,
    )


def export_paper_observation_packet(packet: PaperObservationPacket) -> dict[str, Any]:
    """Return a JSON-ready packet dict without writing files or calling services."""

    return packet.model_dump(mode="json")
