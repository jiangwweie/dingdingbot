from __future__ import annotations

from src.trading_kernel.domain.instrument_certification import (
    CertificationBatchMemberResult,
    CertificationBatchStatus,
    build_certification_manifest_digest,
    evaluate_certification_batch,
)


def test_certification_batch_completes_only_with_exact_eligible_manifest_window() -> None:
    """Catches completing a release batch from partial or short-lived evidence."""

    instruments = (
        "binance-usdm:BTCUSDT:perpetual",
        "binance-usdm:ETHUSDT:perpetual",
    )
    digest = build_certification_manifest_digest(instruments)
    assert digest == build_certification_manifest_digest(tuple(reversed(instruments)))

    first = CertificationBatchMemberResult(
        exchange_instrument_id=instruments[0],
        status="eligible",
        blocker_code=None,
        facts_digest="sha256:" + "a" * 64,
        product_rules_digest="sha256:" + "b" * 64,
        observed_at_ms=1_000,
        valid_until_ms=20_000,
    )
    second = first.model_copy(
        update={
            "exchange_instrument_id": instruments[1],
            "facts_digest": "sha256:" + "c" * 64,
            "product_rules_digest": "sha256:" + "d" * 64,
            "valid_until_ms": 15_000,
        }
    )

    pending = evaluate_certification_batch(
        manifest=instruments,
        member_results=(first,),
        minimum_valid_until_ms=10_000,
    )
    assert pending.status is CertificationBatchStatus.PENDING
    assert pending.valid_until_ms is None

    complete = evaluate_certification_batch(
        manifest=instruments,
        member_results=(first, second),
        minimum_valid_until_ms=10_000,
    )
    assert complete.status is CertificationBatchStatus.COMPLETED
    assert complete.valid_until_ms == 15_000

    too_short = evaluate_certification_batch(
        manifest=instruments,
        member_results=(
            first,
            second.model_copy(update={"valid_until_ms": 9_999}),
        ),
        minimum_valid_until_ms=10_000,
    )
    assert too_short.status is CertificationBatchStatus.PENDING
    assert too_short.valid_until_ms is None


def test_owner_action_member_blocks_batch_without_shrinking_manifest() -> None:
    """Catches silently omitting a blocked instrument from deployment scope."""

    instruments = (
        "binance-usdm:BTCUSDT:perpetual",
        "binance-usdm:ETHUSDT:perpetual",
    )
    blocked = CertificationBatchMemberResult(
        exchange_instrument_id=instruments[1],
        status="owner_action_required",
        blocker_code="configured_leverage_mismatch",
        facts_digest="sha256:" + "e" * 64,
        product_rules_digest="sha256:" + "f" * 64,
        observed_at_ms=1_000,
        valid_until_ms=20_000,
    )

    result = evaluate_certification_batch(
        manifest=instruments,
        member_results=(blocked,),
        minimum_valid_until_ms=10_000,
    )

    assert result.status is CertificationBatchStatus.BLOCKED
    assert result.blocker_code == "configured_leverage_mismatch"
    assert result.completed_member_count == 1
    assert result.required_member_count == 2
