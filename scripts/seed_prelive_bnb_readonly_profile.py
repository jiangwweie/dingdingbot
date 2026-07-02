#!/usr/bin/env python3
"""Prepare the MI-001 BNB prelive read-only runtime profile.

Default behavior is DRY-RUN. APPLY writes PG runtime profile metadata only
after explicit Owner approval environment guards are present. This script does
not grant order permission, start runtime, or call exchange action APIs.

To apply after a separate Owner-approved runtime metadata task:
    OWNER_APPROVED_RUNTIME_PROFILE_SEED=prelive_bnb_readonly_runtime \
    APPLY=true \
    python3 scripts/seed_prelive_bnb_readonly_profile.py
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.seed_strategy_trial_bnb_profile import BNB_STRATEGY_TRIAL_PROFILE
from src.application.runtime_config import RuntimeConfigResolver
from src.infrastructure.runtime_profile_repository import RuntimeProfile


PROFILE_NAME = "prelive_bnb_readonly_runtime"
DESCRIPTION = (
    "MI-001 BNB prelive read-only runtime profile; BNB/USDT:USDT LONG-only, "
    "1x leverage, metadata-only activation"
)
APPROVAL_ENV = "OWNER_APPROVED_RUNTIME_PROFILE_SEED"
UPDATE_APPROVAL_ENV = "OWNER_APPROVED_RUNTIME_PROFILE_UPDATE"
EVIDENCE_PATH_ENV = "RUNTIME_PROFILE_SEED_EVIDENCE_PATH"


class InMemoryRuntimeProfileRepository:
    def __init__(self, profile: RuntimeProfile) -> None:
        self.profile = profile

    async def get_profile(self, name: str) -> RuntimeProfile | None:
        return self.profile if name == self.profile.name else None

    async def get_active_profile(self) -> RuntimeProfile | None:
        return self.profile if self.profile.is_active else None


def _bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def build_candidate_payload() -> dict:
    """Return the audited BNB payload with prelive metadata labels."""
    payload = copy.deepcopy(BNB_STRATEGY_TRIAL_PROFILE)
    payload["brc"]["controlled_playbook_id"] = "PB-PRELIVE-MI001-BNB-READONLY"
    payload["brc"]["profile_source"] = "strategy_trial_bnb_profile"
    validate_candidate_payload(payload)
    return payload


def validate_candidate_payload(payload: Mapping) -> None:
    """Fail closed if the candidate profile drifts from the approved scope."""
    market = payload.get("market", {})
    strategy = payload.get("strategy", {})
    risk = payload.get("risk", {})
    brc = payload.get("brc", {})
    caps = brc.get("fixed_caps", {}).get("BNB/USDT:USDT", {})
    non_permissions = brc.get("non_permissions", {})

    checks = {
        "primary_symbol": market.get("primary_symbol") == "BNB/USDT:USDT",
        "symbols": market.get("symbols") == ["BNB/USDT:USDT"],
        "directions": strategy.get("allowed_directions") == ["LONG"],
        "carrier": brc.get("carrier_id") == "MI-001-BNB-LONG",
        "symbol_sequence": brc.get("symbol_sequence") == ["BNB/USDT:USDT"],
        "max_leverage": risk.get("max_leverage") == 1,
        "max_total_exposure": str(risk.get("max_total_exposure")) == "10",
        "daily_max_trades": risk.get("daily_max_trades") == 1,
        "cap_amount": str(caps.get("amount")) == "0.01",
        "cap_notional": str(caps.get("max_notional")) == "20",
        "cap_leverage": caps.get("leverage") == 1,
        "live_ready_false": non_permissions.get("live_ready") is False,
        "auto_execution_ready_false": non_permissions.get("auto_execution_ready") is False,
        "no_arbitrary_symbol": non_permissions.get("no_arbitrary_symbol") is True,
        "no_arbitrary_side": non_permissions.get("no_arbitrary_side") is True,
        "no_arbitrary_leverage": non_permissions.get("no_arbitrary_leverage") is True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise ValueError("candidate BNB readonly profile scope drift: " + ", ".join(failed))


def guard_apply_environment(env: Mapping[str, str]) -> None:
    """Require explicit live/read-only metadata approval before PG mutation."""
    expected = {
        APPROVAL_ENV: PROFILE_NAME,
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
    }
    failures: list[str] = []
    for name, expected_value in expected.items():
        actual = (env.get(name) or "").strip().lower()
        if actual != expected_value:
            failures.append(f"{name}={env.get(name)!r}, expected {expected_value!r}")

    if (env.get("RUNTIME_PROFILE") or "").strip():
        failures.append("RUNTIME_PROFILE must be unset for live startup profile selection")
    if not (env.get("PG_DATABASE_URL") or "").strip():
        failures.append("PG_DATABASE_URL is required")
    if failures:
        raise ValueError("unsafe runtime profile seed environment: " + "; ".join(failures))


def _summary_env() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "PG_DATABASE_URL": "postgresql://user:pass@localhost:5432/preflight",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
        "TRADING_ENV": "live",
        "EXCHANGE_NAME": "binance",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "EXCHANGE_API_KEY": "x" * 64,
        "EXCHANGE_API_SECRET": "y" * 64,
        "FEISHU_WEBHOOK_URL": "https://example.invalid/webhook",
        "BACKEND_PORT": "18082",
    }


async def build_resolved_summary() -> dict:
    payload = build_candidate_payload()
    profile = RuntimeProfile(
        name=PROFILE_NAME,
        profile_payload=payload,
        description=DESCRIPTION,
        is_active=True,
        is_readonly=True,
        version=1,
    )
    resolved = await RuntimeConfigResolver(
        InMemoryRuntimeProfileRepository(profile),
        env=_summary_env(),
    ).resolve_startup()
    return {
        "profile_name": resolved.profile_name,
        "description": DESCRIPTION,
        "is_active": True,
        "is_readonly": True,
        "config_hash": resolved.config_hash,
        "trading_env": resolved.environment.trading_env,
        "exchange_testnet": resolved.environment.exchange_testnet,
        "permission_max": resolved.environment.brc_execution_permission_max.value_name,
        "primary_symbol": resolved.market.primary_symbol,
        "symbols": resolved.market.symbols,
        "allowed_directions": [
            direction.value if hasattr(direction, "value") else str(direction)
            for direction in resolved.strategy.allowed_directions
        ],
        "max_leverage": resolved.risk.max_leverage,
        "max_total_exposure": str(resolved.risk.max_total_exposure),
        "daily_max_trades": resolved.risk.daily_max_trades,
        "brc": payload["brc"],
    }


def build_seed_evidence(
    *,
    candidate_summary: Mapping[str, Any],
    before_report: Mapping[str, Any],
    after_report: Mapping[str, Any],
    seeded_profile: RuntimeProfile,
) -> dict[str, Any]:
    """Build non-secret pre/post evidence for a controlled profile seed."""
    return {
        "evidence_type": "runtime_profile_seed_prepost",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_name": seeded_profile.name,
        "seeded_profile": {
            "name": seeded_profile.name,
            "description": seeded_profile.description,
            "is_active": seeded_profile.is_active,
            "is_readonly": seeded_profile.is_readonly,
            "version": seeded_profile.version,
            "created_at": seeded_profile.created_at,
            "updated_at": seeded_profile.updated_at,
        },
        "candidate_summary": dict(candidate_summary),
        "before": dict(before_report),
        "after": dict(after_report),
        "safety": {
            "profile_payload_omitted": True,
            "order_permission_granted": False,
            "runtime_started": False,
            "exchange_action_called": False,
        },
    }


def _default_evidence_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("reports") / f"runtime-profile-seed-evidence-{PROFILE_NAME}-{stamp}.json"


def write_seed_evidence(evidence: Mapping[str, Any], env: Mapping[str, str]) -> Path:
    raw_path = (env.get(EVIDENCE_PATH_ENV) or "").strip()
    path = Path(raw_path) if raw_path else _default_evidence_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n")
    return path


def print_dry_run_sql(payload: dict, summary: dict) -> None:
    print("DRY RUN - PG runtime profile metadata that would be applied:")
    print("-" * 72)
    print(
        f"""
UPSERT runtime_profiles
  name={PROFILE_NAME}
  description={DESCRIPTION}
  is_active=true
  is_readonly=true
  config_hash={summary["config_hash"]}
  profile_payload={json.dumps(payload, indent=2, ensure_ascii=False)}
"""
    )
    print("-" * 72)
    print("Required APPLY guard:")
    print(f"  APPLY=true")
    print(f"  {APPROVAL_ENV}={PROFILE_NAME}")
    print("  TRADING_ENV=live")
    print("  EXCHANGE_TESTNET=false")
    print("  BRC_EXECUTION_PERMISSION_MAX=read_only")
    print("  RUNTIME_PROFILE must be unset")


async def apply_profile() -> None:
    guard_apply_environment(os.environ)
    payload = build_candidate_payload()
    summary = await build_resolved_summary()

    from src.infrastructure.connection_pool import close_all_connections
    from scripts.inspect_runtime_profiles_readonly import inspect_runtime_profiles
    from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository

    repo = RuntimeProfileRepository()
    allow_update = os.getenv(UPDATE_APPROVAL_ENV) == PROFILE_NAME
    try:
        before_report = await inspect_runtime_profiles()
        await repo.initialize()
        active = await repo.get_active_profile()
        if active is not None and active.name != PROFILE_NAME:
            raise ValueError(f"refusing to replace active runtime profile: {active.name}")
        existing = await repo.get_profile(PROFILE_NAME)
        if existing is not None and existing.is_readonly and not allow_update:
            raise ValueError(
                f"{UPDATE_APPROVAL_ENV}={PROFILE_NAME} is required to update readonly profile"
            )
        profile = await repo.upsert_profile(
            PROFILE_NAME,
            payload,
            description=DESCRIPTION,
            is_active=True,
            is_readonly=True,
            allow_readonly_update=allow_update,
        )
        after_report = await inspect_runtime_profiles()
        evidence = build_seed_evidence(
            candidate_summary=summary,
            before_report=before_report,
            after_report=after_report,
            seeded_profile=profile,
        )
        evidence_path = write_seed_evidence(evidence, os.environ)
    finally:
        await repo.close()
        await close_all_connections()

    print(f"Profile '{PROFILE_NAME}' seeded successfully")
    print(f"  version={profile.version}")
    print(f"  active={profile.is_active}")
    print(f"  readonly={profile.is_readonly}")
    print("  symbols=['BNB/USDT:USDT']")
    print("  permission grant: none")
    print(f"  evidence={evidence_path}")


async def main() -> None:
    apply = _bool_env(os.getenv("APPLY"))
    payload = build_candidate_payload()
    summary = await build_resolved_summary()

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print()
    if apply:
        print("Applying prelive BNB read-only runtime profile metadata...")
        await apply_profile()
    else:
        print_dry_run_sql(payload, summary)
        print()
        print("No PG mutation performed.")


if __name__ == "__main__":
    asyncio.run(main())
