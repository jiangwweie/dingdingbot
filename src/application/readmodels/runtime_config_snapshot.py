"""Console Config Snapshot ReadModel - 第三批只读 API"""

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
        if profile_name and profile_name != "unknown":
            hints.append(f"config_provider:runtime_profile:{profile_name}")
        if summary.get("strategy"):
            hints.append("strategy:resolved_from_profile")
        if summary.get("risk"):
            hints.append("risk:resolved_from_profile")
        if summary.get("execution"):
            hints.append("execution:resolved_from_profile")
        if not hints:
            hints.append("no_active_source")

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
