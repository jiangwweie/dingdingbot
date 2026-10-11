"""Deployment revision discovery is readonly, not migration authorization."""

from contextlib import asynccontextmanager

import pytest

from scripts.trading_kernel import verify_schema


@pytest.mark.asyncio
@pytest.mark.parametrize("revision, expected", [
    ("0007_exit_profile_authority_v1", "pass"),
    ("0009_capacity_policy_v0", "pass"),
    ("0008_generic_dynamic_selection_v1", "fail"),
    ("unknown_revision", "fail"),
    (None, "fail"),
])
async def test_deployment_revision_recognizes_exact_generic_source_readonly(
    monkeypatch: pytest.MonkeyPatch, revision: str | None, expected: str,
) -> None:
    calls: list[str] = []

    class Connection:
        async def execute(self, statement: object) -> None:
            calls.append(str(statement))

        async def rollback(self) -> None:
            calls.append("rollback")

    class Engine:
        @asynccontextmanager
        async def connect(self):
            yield Connection()

        async def dispose(self) -> None:
            calls.append("dispose")

    async def read_revision(connection: object) -> str | None:
        assert calls == ["SET TRANSACTION READ ONLY"]
        return revision

    monkeypatch.setattr(verify_schema, "_create_engine", lambda _: Engine())
    monkeypatch.setattr(verify_schema, "_alembic_revision", read_revision)
    result = await verify_schema._inspect_deployment_revision("disposable")
    assert result == {"schema": verify_schema.SCHEMA, "status": expected,
                      "alembic_revision": revision}
    assert calls == ["SET TRANSACTION READ ONLY", "rollback", "dispose"]
