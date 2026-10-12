#!/usr/bin/env python3
"""Promote the already deployed release from fenced safety operation to ENTRY."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ENTRY_SERVICE = "brc-trading-kernel-entry-worker.service"
SAFETY_SERVICES = (
    "brc-trading-kernel-observation-worker.service",
    "brc-trading-kernel-lifecycle-worker.service",
    "brc-trading-kernel-reconciliation-worker.service",
)
WRITE_FENCE = "/etc/brc/trading-kernel.write-fenced"


class EntryPromotionBlocked(RuntimeError):
    pass


class EntryPromotionBackend(Protocol):
    def certification(self) -> Mapping[str, object]: ...

    def external_state_and_rules_match(
        self,
        certification: Mapping[str, object],
    ) -> bool: ...

    def safety_workers_active_stable(self) -> bool: ...

    def entry_is_inactive_disabled_and_fenced(self) -> bool: ...

    def start_entry_while_fenced(self) -> None: ...

    def entry_is_active_while_fenced(self) -> bool: ...

    def remove_entry_fence(self) -> None: ...

    def entry_is_active(self) -> bool: ...

    def restore_entry_fence(self) -> None: ...


def promote_entry(backend: EntryPromotionBackend) -> str:
    """Perform the one-way promotion; every failure leaves ENTRY fenced."""

    entry_already_started_fenced = False
    if not backend.entry_is_inactive_disabled_and_fenced():
        certification = backend.certification()
        if (
            _authority_is_armed(certification)
            and backend.entry_is_active()
            and backend.external_state_and_rules_match(certification)
            and backend.safety_workers_active_stable()
        ):
            return "already_promoted"
        if backend.entry_is_active_while_fenced():
            entry_already_started_fenced = True
        else:
            raise EntryPromotionBlocked(
                "entry_service_not_fenced_inactive_disabled"
            )
    else:
        certification = backend.certification()
    if not _authority_is_armed(certification):
        policy = certification.get("owner_policy")
        if isinstance(policy, Mapping) and (
            policy.get("new_entry_submit_enabled") is not True
            or certification.get("owner_entry_resume_authorized") is not True
        ):
            raise EntryPromotionBlocked("entry_promotion_gate_failed:owner_entry_resume_required")
        raise EntryPromotionBlocked("entry_promotion_gate_failed")
    if not backend.external_state_and_rules_match(certification):
        raise EntryPromotionBlocked("exchange_state_or_rule_gate_failed")
    if not backend.safety_workers_active_stable():
        raise EntryPromotionBlocked("safety_worker_gate_failed")
    try:
        if not entry_already_started_fenced:
            backend.start_entry_while_fenced()
        if not backend.entry_is_active_while_fenced():
            raise EntryPromotionBlocked("entry_not_active_while_fenced")
        postflight = backend.certification()
        if (
            not _authority_is_armed(postflight)
            or postflight.get("entry_recovery_basis_digest")
            != certification.get("entry_recovery_basis_digest")
            or not backend.external_state_and_rules_match(postflight)
            or not backend.safety_workers_active_stable()
            or not _authority_is_armed(postflight)
        ):
            raise EntryPromotionBlocked("final_postflight_failed")
        backend.remove_entry_fence()
        if not backend.entry_is_active():
            raise EntryPromotionBlocked("entry_not_active_after_unfence")
    except Exception:
        backend.restore_entry_fence()
        raise
    return "promoted"


def _authority_is_armed(certification: Mapping[str, object]) -> bool:
    owner_policy = certification.get("owner_policy")
    capabilities = certification.get("capabilities")
    return bool(
        certification.get("status") == "pass"
        and certification.get("entry_recovery_ready") is True
        and certification.get("owner_entry_resume_authorized") is True
        and isinstance(certification.get("entry_recovery_basis_digest"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", str(certification["entry_recovery_basis_digest"])) is not None
        and type(certification.get("entry_recovery_valid_until_ms")) is int
        and int(str(certification["entry_recovery_valid_until_ms"])) > int(time.time() * 1000)
        and certification.get("flatness_pass") is True
        and isinstance(owner_policy, Mapping)
        and _is_positive_policy_version(owner_policy.get("policy_version"))
        and owner_policy.get("new_entry_submit_enabled") is True
        and isinstance(capabilities, Mapping)
        and capabilities.get("exchange_commands") is True
    )


def _is_positive_policy_version(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class LocalEntryPromotionBackend:
    """Server-local operational backend; never contacts the exchange for mutation."""

    def __init__(self, *, python: str, database_url: str) -> None:
        self._python = python
        self._database_url = database_url

    def certification(self) -> Mapping[str, object]:
        result = self._json_script("certify_readonly.py")
        identity = result.get("runtime_identity")
        if (
            not isinstance(identity, Mapping)
            or type(result.get("certified_at_ms")) is not int
            or not 0 < int(str(result["certified_at_ms"])) <= int(time.time() * 1000)
            or not os.environ.get("TRADING_KERNEL_RUNTIME_COMMIT")
            or identity.get("runtime_commit") != os.environ.get("TRADING_KERNEL_RUNTIME_COMMIT")
            or identity.get("schema_revision") != os.environ.get("TRADING_KERNEL_SCHEMA_REVISION")
            or not os.environ.get("TRADING_KERNEL_ACCOUNT_ID")
            or result.get("entry_recovery_account_id") != os.environ.get("TRADING_KERNEL_ACCOUNT_ID")
        ):
            raise EntryPromotionBlocked("deployed_runtime_identity_mismatch")
        return result

    def external_state_and_rules_match(
        self,
        certification: Mapping[str, object],
    ) -> bool:
        probe = self._json_script("probe_production_runtime.py")
        rules = probe.get("rules")
        manifest = probe.get("probe_manifest")
        members = certification.get("entry_recovery_members")
        now_ms = int(time.time() * 1000)
        return bool(
            probe.get("environment") == "live"
            and probe.get("venue_id") == "binance-usdm"
            and probe.get("account_id") == certification.get("entry_recovery_account_id")
            and probe.get("account_position_mode") == "independent_sides"
            and probe.get("account_margin_mode") == "cross"
            and certification.get("flatness_pass") is True
            and probe.get("non_flat_domain_count") == 0
            and probe.get("open_order_domain_count") == 0
            and isinstance(manifest, list)
            and isinstance(members, list)
            and bool(members)
            and manifest == members == sorted(set(members))
            and isinstance(rules, list)
            and len(rules) == len(members) == probe.get("instrument_rule_count")
            and type(probe.get("observed_at_ms")) is int
            and 0 < int(str(probe["observed_at_ms"])) <= now_ms
            and {str(row.get("exchange_instrument_id")) for row in rules if isinstance(row, Mapping)}
            == {str(item) for item in manifest}
            and all(
                isinstance(row, Mapping) and type(row.get("configured_leverage")) is int
                and row.get("configured_leverage") == 5
                and type(row.get("valid_until_ms")) is int
                and int(row["valid_until_ms"]) > now_ms
                for row in rules
            )
        )

    def safety_workers_active_stable(self) -> bool:
        return all(self._active(service) for service in SAFETY_SERVICES)

    def entry_is_inactive_disabled_and_fenced(self) -> bool:
        return self._fence_exists() and not self._active(ENTRY_SERVICE) and not self._enabled(ENTRY_SERVICE)

    def start_entry_while_fenced(self) -> None:
        self._run("sudo", "systemctl", "enable", "--now", ENTRY_SERVICE)

    def entry_is_active_while_fenced(self) -> bool:
        return self._fence_exists() and self._active(ENTRY_SERVICE)

    def remove_entry_fence(self) -> None:
        self._run("sudo", "rm", "-f", WRITE_FENCE)

    def entry_is_active(self) -> bool:
        return not self._fence_exists() and self._active(ENTRY_SERVICE)

    def restore_entry_fence(self) -> None:
        self._run("sudo", "touch", WRITE_FENCE, check=False)
        self._run("sudo", "systemctl", "disable", "--now", ENTRY_SERVICE, check=False)

    def _json_script(self, script: str, *args: str) -> Mapping[str, object]:
        result = subprocess.run(
            (self._python, str(REPO_ROOT / "scripts/trading_kernel" / script), *args),
            check=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "TRADING_KERNEL_DATABASE_URL": self._database_url,
            },
            timeout=120,
        )
        payload = json.loads(result.stdout)
        if not isinstance(payload, Mapping):
            raise EntryPromotionBlocked("promotion_script_payload_invalid")
        return payload

    def _active(self, service: str) -> bool:
        return self._run("sudo", "systemctl", "is-active", "--quiet", service, check=False).returncode == 0

    def _enabled(self, service: str) -> bool:
        return self._run("sudo", "systemctl", "is-enabled", "--quiet", service, check=False).returncode == 0

    def _fence_exists(self) -> bool:
        return self._run("sudo", "test", "-f", WRITE_FENCE, check=False).returncode == 0

    @staticmethod
    def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, check=check, capture_output=True, text=True, timeout=30)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = str(args.database_url).strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser = _parser()
        parser.error("database URL must use postgresql+asyncpg")
    try:
        status = promote_entry(
            LocalEntryPromotionBackend(python=sys.executable, database_url=database_url)
        )
    except EntryPromotionBlocked as exc:
        print(f"status=blocked reason={exc}", file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("status=failed reason=operation_failed", file=sys.stderr)
        return 1
    print(f"status={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
