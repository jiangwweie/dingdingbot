"""Phase 5B runtime symbol-isolation audit records.

This module is deliberately pure: it records what is locally proven, what still
needs review, and what remains blocked before multi-symbol runtime expansion.
It does not start runtime services or call exchanges.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SymbolIsolationStatus(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    BLOCKED = "blocked"


class SymbolIsolationCheck(BaseModel):
    check_id: str
    component: str
    status: SymbolIsolationStatus
    evidence: str
    remaining_work: str | None = None


class SymbolIsolationAuditReport(BaseModel):
    audit_version: Literal["phase5b_symbol_isolation_audit_v1"] = (
        "phase5b_symbol_isolation_audit_v1"
    )
    runtime_scope: Literal["single_symbol_eth_runtime"] = "single_symbol_eth_runtime"
    multi_symbol_runtime_authorized: Literal[False] = False
    checks: list[SymbolIsolationCheck] = Field(default_factory=list)
    verdict: str


def build_phase5b_symbol_isolation_audit() -> SymbolIsolationAuditReport:
    """Return the current Phase 5B symbol-isolation audit snapshot."""

    checks = [
        SymbolIsolationCheck(
            check_id="P5B-SYM-001",
            component="order_watch_lifecycle",
            status=SymbolIsolationStatus.PASS,
            evidence=(
                "Order-watch keeps a symbol-keyed running-state map while "
                "retaining the legacy global shutdown flag for compatibility."
            ),
        ),
        SymbolIsolationCheck(
            check_id="P5B-SYM-002",
            component="order_confirmation_recent_update_cache",
            status=SymbolIsolationStatus.PASS,
            evidence=(
                "Recent order-update evidence is indexed by symbol before "
                "confirmation, preventing same-id cross-symbol overwrite from "
                "becoming confirmation evidence."
            ),
        ),
        SymbolIsolationCheck(
            check_id="P5B-SYM-003",
            component="reconciliation",
            status=SymbolIsolationStatus.REVIEW,
            evidence=(
                "Reconciliation read-model paths accept symbol-specific "
                "inputs and Phase 4/5 ETH testnet evidence is clean."
            ),
            remaining_work=(
                "Run a dedicated two-symbol synthetic reconciliation proof "
                "before enabling multi-symbol runtime."
            ),
        ),
        SymbolIsolationCheck(
            check_id="P5B-SYM-004",
            component="runtime_read_models_and_caches",
            status=SymbolIsolationStatus.REVIEW,
            evidence=(
                "Console execution routes expose symbol filters for orders, "
                "intents, signals, and attempts; portfolio/positions remain "
                "account-level views."
            ),
            remaining_work=(
                "Add a two-symbol fixture suite for read-model filtering and "
                "account-level aggregation semantics."
            ),
        ),
        SymbolIsolationCheck(
            check_id="P5B-SYM-005",
            component="multi_symbol_runtime",
            status=SymbolIsolationStatus.BLOCKED,
            evidence=(
                "Current execution rehearsal remains ETH-only under "
                "sim1_eth_runtime."
            ),
            remaining_work=(
                "Owner must separately authorize any multi-symbol runtime "
                "profile, repeated rehearsal, or exchange-connected expansion."
            ),
        ),
    ]
    return SymbolIsolationAuditReport(
        checks=checks,
        verdict=(
            "single_symbol_repeated_testnet_ready_for_review / "
            "multi_symbol_runtime_still_blocked"
        ),
    )
