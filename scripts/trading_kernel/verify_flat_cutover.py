#!/usr/bin/env python3
"""Verify exact flat-state and identity preconditions for destructive cutover."""

from __future__ import annotations

import argparse
import asyncio
from enum import StrEnum
import importlib
import inspect
import json
from pathlib import Path
import re
import sys
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, field_validator


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


_COMMIT_IDENTITY = re.compile(r"^[0-9a-f]{40}$")
_SHA256_IDENTITY = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


class CutoverBlocker(StrEnum):
    SERVER_IDENTITY_MISMATCH = "server_identity_mismatch"
    DATABASE_IDENTITY_MISMATCH = "database_identity_mismatch"
    VENUE_IDENTITY_MISMATCH = "venue_identity_mismatch"
    ACCOUNT_IDENTITY_MISMATCH = "account_identity_mismatch"
    ACCOUNT_MODE_INVALID = "account_mode_invalid"
    POSITIONS_NOT_FLAT = "positions_not_flat"
    OPEN_ORDERS_PRESENT = "open_orders_present"
    PROTECTION_RESIDUE_PRESENT = "protection_residue_present"
    OLD_TICKETS_NONTERMINAL = "old_tickets_nonterminal"
    ACTIVE_BUDGETS_PRESENT = "active_budgets_present"
    COMMAND_OUTCOME_UNKNOWN = "command_outcome_unknown"
    RUNTIME_INCIDENT_OPEN = "runtime_incident_open"
    TARGET_COMMIT_MISMATCH = "target_commit_mismatch"
    TARGET_SCHEMA_MISMATCH = "target_schema_mismatch"
    TARGET_SEED_IDENTITY_MISMATCH = "target_seed_identity_mismatch"
    OLD_WRITER_ACTIVE = "old_writer_active"
    NEW_WRITER_ACTIVE = "new_writer_active"
    WRITER_FENCE_MISSING = "writer_fence_missing"


class CutoverPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cutover_id: str
    server_id: str
    database_identity: str
    venue_id: str
    account_id: str
    runtime_profile_id: str
    application_schema: str
    target_commit: str
    target_schema_revision: str
    target_seed_identity: str
    target_release_id: str

    @field_validator(
        "cutover_id",
        "server_id",
        "database_identity",
        "venue_id",
        "account_id",
        "runtime_profile_id",
        "target_release_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("cutover identities must be non-blank")
        return normalized

    @field_validator("application_schema", mode="before")
    @classmethod
    def _require_schema_name(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if _SCHEMA_NAME.fullmatch(normalized) is None:
            raise ValueError("application schema must be a simple PostgreSQL identity")
        return normalized

    @field_validator("target_commit", mode="before")
    @classmethod
    def _require_commit(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if _COMMIT_IDENTITY.fullmatch(normalized) is None:
            raise ValueError("target commit must be an exact forty-character git SHA")
        return normalized

    @field_validator("target_schema_revision", mode="before")
    @classmethod
    def _require_schema_revision(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if normalized != "0001_initial":
            raise ValueError("target schema revision must be 0001_initial")
        return normalized

    @field_validator("target_seed_identity", mode="before")
    @classmethod
    def _require_seed_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if _SHA256_IDENTITY.fullmatch(normalized) is None:
            raise ValueError("target seed identity must be an exact sha256 identity")
        return normalized


class CutoverFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    server_id: str
    database_identity: str
    venue_id: str
    account_id: str
    account_mode: str
    target_commit: str
    target_schema_revision: str
    target_seed_identity: str
    non_flat_positions: int
    open_orders: int
    protection_orders: int
    nonterminal_tickets: int
    active_budgets: int
    unresolved_outcomes: int
    open_incidents: int
    active_old_writers: tuple[str, ...]
    active_new_writers: tuple[str, ...]
    exchange_writes_fenced: bool

    @field_validator(
        "server_id",
        "database_identity",
        "venue_id",
        "account_id",
        "account_mode",
        "target_commit",
        "target_schema_revision",
        "target_seed_identity",
        mode="before",
    )
    @classmethod
    def _require_fact_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("cutover fact identities must be non-blank")
        return normalized

    @field_validator(
        "non_flat_positions",
        "open_orders",
        "protection_orders",
        "nonterminal_tickets",
        "active_budgets",
        "unresolved_outcomes",
        "open_incidents",
    )
    @classmethod
    def _require_nonnegative_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("cutover fact counts must be nonnegative")
        return value


class CutoverVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    blockers: tuple[CutoverBlocker, ...]
    require_writer_fence: bool
    facts: CutoverFacts


class CutoverFactsAdapter(Protocol):
    async def inspect_preconditions(self, plan: CutoverPlan) -> CutoverFacts: ...


def verify_cutover_facts(
    plan: CutoverPlan,
    facts: CutoverFacts,
    *,
    require_writer_fence: bool,
) -> CutoverVerification:
    blockers: list[CutoverBlocker] = []
    checks = (
        (
            facts.server_id != plan.server_id,
            CutoverBlocker.SERVER_IDENTITY_MISMATCH,
        ),
        (
            facts.database_identity != plan.database_identity,
            CutoverBlocker.DATABASE_IDENTITY_MISMATCH,
        ),
        (facts.venue_id != plan.venue_id, CutoverBlocker.VENUE_IDENTITY_MISMATCH),
        (
            facts.account_id != plan.account_id,
            CutoverBlocker.ACCOUNT_IDENTITY_MISMATCH,
        ),
        (
            facts.account_mode != "independent_sides",
            CutoverBlocker.ACCOUNT_MODE_INVALID,
        ),
        (facts.non_flat_positions != 0, CutoverBlocker.POSITIONS_NOT_FLAT),
        (facts.open_orders != 0, CutoverBlocker.OPEN_ORDERS_PRESENT),
        (
            facts.protection_orders != 0,
            CutoverBlocker.PROTECTION_RESIDUE_PRESENT,
        ),
        (
            facts.nonterminal_tickets != 0,
            CutoverBlocker.OLD_TICKETS_NONTERMINAL,
        ),
        (facts.active_budgets != 0, CutoverBlocker.ACTIVE_BUDGETS_PRESENT),
        (
            facts.unresolved_outcomes != 0,
            CutoverBlocker.COMMAND_OUTCOME_UNKNOWN,
        ),
        (facts.open_incidents != 0, CutoverBlocker.RUNTIME_INCIDENT_OPEN),
        (
            facts.target_commit != plan.target_commit,
            CutoverBlocker.TARGET_COMMIT_MISMATCH,
        ),
        (
            facts.target_schema_revision != plan.target_schema_revision,
            CutoverBlocker.TARGET_SCHEMA_MISMATCH,
        ),
        (
            facts.target_seed_identity != plan.target_seed_identity,
            CutoverBlocker.TARGET_SEED_IDENTITY_MISMATCH,
        ),
    )
    blockers.extend(blocker for failed, blocker in checks if failed)
    if require_writer_fence:
        if facts.active_old_writers:
            blockers.append(CutoverBlocker.OLD_WRITER_ACTIVE)
        if facts.active_new_writers:
            blockers.append(CutoverBlocker.NEW_WRITER_ACTIVE)
        if not facts.exchange_writes_fenced:
            blockers.append(CutoverBlocker.WRITER_FENCE_MISSING)
    return CutoverVerification(
        status="pass" if not blockers else "fail",
        blockers=tuple(blockers),
        require_writer_fence=require_writer_fence,
        facts=facts,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-factory", required=True, help="module:callable")
    parser.add_argument("--cutover-id", required=True)
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--database-identity", required=True)
    parser.add_argument("--venue-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--runtime-profile-id", required=True)
    parser.add_argument("--application-schema", default="public")
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--target-schema-revision", default="0001_initial")
    parser.add_argument("--target-seed-identity", required=True)
    parser.add_argument("--target-release-id", required=True)
    parser.add_argument("--require-writer-fence", action="store_true")
    return parser


def build_plan_from_args(args: argparse.Namespace) -> CutoverPlan:
    return CutoverPlan(
        cutover_id=args.cutover_id,
        server_id=args.server_id,
        database_identity=args.database_identity,
        venue_id=args.venue_id,
        account_id=args.account_id,
        runtime_profile_id=args.runtime_profile_id,
        application_schema=args.application_schema,
        target_commit=args.target_commit,
        target_schema_revision=args.target_schema_revision,
        target_seed_identity=args.target_seed_identity,
        target_release_id=args.target_release_id,
    )


async def load_cutover_adapter(spec: str) -> CutoverFactsAdapter:
    module_name, separator, attribute_name = spec.partition(":")
    if not separator or not module_name.strip() or not attribute_name.strip():
        raise ValueError("cutover adapter factory must use module:callable")
    factory = getattr(importlib.import_module(module_name), attribute_name)
    if not callable(factory):
        raise TypeError("cutover adapter factory target is not callable")
    adapter = factory()
    if inspect.isawaitable(adapter):
        adapter = await adapter
    if not callable(getattr(adapter, "inspect_preconditions", None)):
        raise TypeError("cutover adapter must expose inspect_preconditions")
    return cast(CutoverFactsAdapter, adapter)


async def _run(args: argparse.Namespace) -> int:
    plan = build_plan_from_args(args)
    adapter = await load_cutover_adapter(args.adapter_factory)
    try:
        facts = await adapter.inspect_preconditions(plan)
        verification = verify_cutover_facts(
            plan,
            facts,
            require_writer_fence=args.require_writer_fence,
        )
        print(json.dumps(verification.model_dump(mode="json"), sort_keys=True))
        return 0 if verification.status == "pass" else 1
    finally:
        close = getattr(adapter, "close", None)
        if callable(close):
            closed = close()
            if inspect.isawaitable(closed):
                await closed


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
