"""
Unit tests for RuntimeProfileRepository.

Focus:
- readonly protection
- version auto-increment
- active profile mutual exclusion
- JSON corruption visibility
"""

import json

import aiosqlite
import pytest

from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository


@pytest.fixture
async def repo():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    repository = RuntimeProfileRepository(connection=db)
    await repository.initialize()
    try:
        yield repository, db
    finally:
        await repository.close()
        await db.close()


@pytest.mark.asyncio
async def test_readonly_profile_rejects_update(repo):
    repository, _db = repo
    await repository.upsert_profile(
        "sim1_eth_runtime",
        {"market": {}, "strategy": {}, "risk": {}, "execution": {}},
        is_active=True,
        is_readonly=True,
        allow_readonly_update=True,
    )

    with pytest.raises(ValueError):
        await repository.upsert_profile(
            "sim1_eth_runtime",
            {"market": {}, "strategy": {}, "risk": {}, "execution": {}},
            is_active=True,
            is_readonly=True,
        )


@pytest.mark.asyncio
async def test_version_increments_on_update(repo):
    repository, _db = repo
    created = await repository.upsert_profile(
        "p1",
        {"market": {}, "strategy": {}, "risk": {}, "execution": {}},
        allow_readonly_update=True,
    )
    updated = await repository.upsert_profile(
        "p1",
        {"market": {"primary_symbol": "ETH/USDT:USDT"}, "strategy": {}, "risk": {}, "execution": {}},
        allow_readonly_update=True,
    )
    assert created.version == 1
    assert updated.version == 2


@pytest.mark.asyncio
async def test_active_profile_is_mutually_exclusive(repo):
    repository, _db = repo
    await repository.upsert_profile(
        "p1",
        {"market": {}, "strategy": {}, "risk": {}, "execution": {}},
        is_active=True,
        allow_readonly_update=True,
    )
    await repository.upsert_profile(
        "p2",
        {"market": {}, "strategy": {}, "risk": {}, "execution": {}},
        is_active=True,
        allow_readonly_update=True,
    )

    active = await repository.get_active_profile()
    assert active is not None
    assert active.name == "p2"

    p1 = await repository.get_profile("p1")
    assert p1 is not None
    assert p1.is_active is False


@pytest.mark.asyncio
async def test_corrupted_profile_json_raises(repo):
    repository, db = repo
    await db.execute(
        """
        INSERT INTO runtime_profiles (
            name, description, profile_json, is_active, is_readonly,
            created_at, updated_at, version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("bad", None, "not-json", False, False, 0, 0, 1),
    )
    await db.commit()

    with pytest.raises(json.JSONDecodeError):
        await repository.get_profile("bad")

