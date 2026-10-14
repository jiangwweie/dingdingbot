from __future__ import annotations

import asyncio
from collections.abc import Mapping
from uuid import uuid4

import pytest

from scripts.trading_kernel.certify_readonly import _certify
from scripts.trading_kernel.promote_entry import (
    EntryPromotionBlocked,
    promote_entry,
)
from tests.trading_kernel.support.postgres import (
    SAFE_TEST_DATABASE as SAFE_DATABASE,
)
from tests.trading_kernel.support.postgres import (
    async_database_url as _database_url,
)
from tests.trading_kernel.support.promotion_rehearsal import (
    RecordingPromotionBackend,
    _cleanup,
    _owner_resume,
    _seed_and_bootstrap,
)
from tests.trading_kernel.unit.detectors.fixtures import NOW_MS


def test_entry_promotion_rehearses_arm_failure_resume_and_idempotence() -> None:
    """Exercise promotion with compatible-upgrade safety capability already on."""

    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    database_url = _database_url(database_name)
    asyncio.run(_seed_and_bootstrap(database_name, database_url))
    promotion_now_ms = NOW_MS + 10_000
    try:
        paused = RecordingPromotionBackend(database_url=database_url, now_ms=promotion_now_ms)
        with pytest.raises(EntryPromotionBlocked, match="entry_promotion_gate_failed"):
            promote_entry(paused)
        assert paused.fenced and paused.calls == ["preflight", "certification"]
        asyncio.run(_owner_resume(database_url, promotion_now_ms))
        failed = RecordingPromotionBackend(
            database_url=database_url,
            now_ms=promotion_now_ms,
            fail_start=True,
        )
        with pytest.raises(
            EntryPromotionBlocked,
            match="entry_not_active_while_fenced",
        ):
            promote_entry(failed)

        armed_after_failure = asyncio.run(
            _certify(
                database_url,
                require_flat=True,
                now_ms=promotion_now_ms,
            )
        )
        armed_owner_policy = armed_after_failure["owner_policy"]
        armed_capabilities = armed_after_failure["capabilities"]
        assert isinstance(armed_owner_policy, Mapping)
        assert isinstance(armed_capabilities, Mapping)
        assert armed_owner_policy["policy_version"] == 5
        assert armed_owner_policy["new_entry_submit_enabled"] is True
        assert armed_capabilities["exchange_commands"] is True
        assert failed.fenced is True
        assert failed.entry_active is False
        assert failed.calls[-1] == "restore"

        retry = RecordingPromotionBackend(
            database_url=database_url,
            now_ms=promotion_now_ms,
        )
        assert promote_entry(retry) == "promoted"
        assert "arm" not in retry.calls
        assert retry.exchange_mutations == []

        assert promote_entry(retry) == "already_promoted"
        final = asyncio.run(
            _certify(
                database_url,
                require_flat=True,
                now_ms=promotion_now_ms,
            )
        )
        final_owner_policy = final["owner_policy"]
        final_capabilities = final["capabilities"]
        assert isinstance(final_owner_policy, Mapping)
        assert isinstance(final_capabilities, Mapping)
        assert final_owner_policy["policy_version"] == 5
        assert final_capabilities["exchange_commands"] is True
    finally:
        asyncio.run(_cleanup(database_name))
