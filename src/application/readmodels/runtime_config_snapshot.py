"""Console Config Snapshot ReadModel - 第三批只读 API

Source-of-truth hint taxonomy:
  runtime_profile       — config comes from a resolved runtime profile (DB-backed)
  resolved_from_profile — a section (strategy/risk/execution) was resolved from the profile
  environment           — a value comes from .env / process environment
  no_provider           — no RuntimeConfigProvider was supplied (config unavailable)
  provider_error        — provider.to_safe_summary() raised an exception
  legacy_fallback       — value fell back to a legacy/default path (no explicit source)
"""

from __future__ import annotations

from typing import Any, Optional

from src.application.readmodels.console_models import ConfigIdentity, ConfigSnapshotResponse


class RuntimeConfigSnapshotReadModel:
    def build(self, *, runtime_config_provider: Optional[Any] = None) -> ConfigSnapshotResponse:
        if runtime_config_provider is None:
            identity = ConfigIdentity(profile="unavailable", version=0, hash="")
            return ConfigSnapshotResponse(
                identity=identity,
                profile="unavailable",
                version=0,
                hash="",
                source_of_truth_hints=["no_provider"],
            )

        try:
            summary = runtime_config_provider.to_safe_summary()
        except Exception:
            identity = ConfigIdentity(profile="error", version=0, hash="")
            return ConfigSnapshotResponse(
                identity=identity,
                profile="error",
                version=0,
                hash="",
                source_of_truth_hints=["provider_error"],
            )

        profile_name = summary.get("profile_name", "unknown")
        version = summary.get("version", 0)
        config_hash = summary.get("config_hash", "")

        identity = ConfigIdentity(
            profile=profile_name,
            version=version,
            hash=config_hash,
        )

        # Backend: extract from environment summary
        env = summary.get("environment") or {}
        backend = {
            "exchange_name": env.get("exchange_name", "unknown"),
            "exchange_testnet": env.get("exchange_testnet", True),
            "mode": env.get("mode", "unknown"),
        }

        # Source of truth hints: describe where each data domain comes from
        hints: list[str] = []

        # 1. Profile identity — the config was resolved from a named runtime profile
        if profile_name and profile_name != "unknown":
            hints.append(f"runtime_profile:{profile_name}")

        # 2. Per-section resolution — each section was resolved from the profile
        for section in ("strategy", "risk", "execution"):
            if summary.get(section):
                hints.append(f"{section}:resolved_from_profile")

        # 3. Environment — backend/exchange settings come from process environment
        if env and any(env.get(k) for k in ("exchange_name", "exchange_testnet", "backend_port")):
            hints.append("backend:environment")

        # 4. Market section — if present, resolved from profile
        if summary.get("market"):
            hints.append("market:resolved_from_profile")

        # 5. Fallback when nothing was resolved
        if not hints:
            hints.append("legacy_fallback")

        return ConfigSnapshotResponse(
            identity=identity,
            market=summary.get("market") or {},
            strategy=summary.get("strategy") or {},
            risk=summary.get("risk") or {},
            execution=summary.get("execution") or {},
            backend=backend,
            source_of_truth_hints=hints,
            profile=profile_name,
            version=version,
            hash=config_hash,
            environment=env,
        )
