#!/usr/bin/env python3
"""Promote the already deployed release from fenced safety operation to ENTRY."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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

    def arm_entry_authority(self) -> Mapping[str, object]: ...

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
        if _authority_is_armed(certification) and backend.entry_is_active():
            return "already_promoted"
        if (
            certification.get("entry_promotion_pass") is True
            and backend.entry_is_active_while_fenced()
        ):
            entry_already_started_fenced = True
        else:
            raise EntryPromotionBlocked(
                "entry_service_not_fenced_inactive_disabled"
            )
    else:
        certification = backend.certification()
    requires_arm = certification.get("entry_promotion_pass") is True
    if not requires_arm and not _authority_is_armed(certification):
        raise EntryPromotionBlocked("entry_promotion_gate_failed")
    if not backend.external_state_and_rules_match(certification):
        raise EntryPromotionBlocked("exchange_state_or_rule_gate_failed")
    if not backend.safety_workers_active_stable():
        raise EntryPromotionBlocked("safety_worker_gate_failed")
    try:
        if requires_arm:
            armed = backend.arm_entry_authority()
            if (
                armed.get("new_entry_submit_enabled") is not True
                or armed.get("policy_version") != 2
            ):
                raise EntryPromotionBlocked("entry_authority_arm_failed")
        if not entry_already_started_fenced:
            backend.start_entry_while_fenced()
        if not backend.entry_is_active_while_fenced():
            raise EntryPromotionBlocked("entry_not_active_while_fenced")
        postflight = backend.certification()
        if (
            not _authority_is_armed(postflight)
            or not backend.external_state_and_rules_match(postflight)
            or not backend.safety_workers_active_stable()
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
        certification.get("universe_bootstrap_pass") is True
        and certification.get("certification_batch_pass") is True
        and (
            certification.get("flatness_pass") is True
            or certification.get("protected_promotion_pass") is True
        )
        and isinstance(owner_policy, Mapping)
        and owner_policy.get("policy_version") == 2
        and owner_policy.get("new_entry_submit_enabled") is True
        and isinstance(capabilities, Mapping)
        and capabilities.get("exchange_commands") is True
    )


class LocalEntryPromotionBackend:
    """Server-local operational backend; never contacts the exchange for mutation."""

    def __init__(self, *, python: str, database_url: str) -> None:
        self._python = python
        self._database_url = database_url

    def certification(self) -> Mapping[str, object]:
        return self._json_script("certify_readonly.py")

    def external_state_and_rules_match(
        self,
        certification: Mapping[str, object],
    ) -> bool:
        protected = certification.get("protected_tickets")
        if not isinstance(protected, list) or any(
            not isinstance(item, Mapping) for item in protected
        ):
            return False
        probe_args: list[str] = []
        for item in protected:
            probe_args.extend(
                (
                    "--protected-ticket-json",
                    json.dumps(item, separators=(",", ":"), sort_keys=True),
                )
            )
        probe = self._json_script("probe_production_runtime.py", *probe_args)
        rules = probe.get("rules")
        manifest = probe.get("probe_manifest")
        probe_protected = probe.get("protected_tickets")
        protected_mode = certification.get("protected_promotion_pass") is True
        exposure_matches = (
            probe.get("non_flat_domain_count") == len(protected)
            and probe.get("open_order_domain_count") == len(protected)
            and isinstance(probe_protected, list)
            and len(probe_protected) == len(protected)
            if protected_mode
            else (
                certification.get("flatness_pass") is True
                and not protected
                and probe.get("non_flat_domain_count") == 0
                and probe.get("open_order_domain_count") == 0
            )
        )
        return bool(
            probe.get("venue_id") == "binance-usdm"
            and probe.get("account_position_mode") == "independent_sides"
            and probe.get("account_margin_mode") == "cross"
            and exposure_matches
            and isinstance(manifest, list)
            and len(manifest) == 7
            and isinstance(rules, list)
            and len(rules) == 7
            and {str(row.get("exchange_instrument_id")) for row in rules if isinstance(row, Mapping)}
            == {str(item) for item in manifest}
            and all(
                isinstance(row, Mapping) and row.get("configured_leverage") == 5
                for row in rules
            )
        )

    def safety_workers_active_stable(self) -> bool:
        return all(self._active(service) for service in SAFETY_SERVICES)

    def entry_is_inactive_disabled_and_fenced(self) -> bool:
        return self._fence_exists() and not self._active(ENTRY_SERVICE) and not self._enabled(ENTRY_SERVICE)

    def arm_entry_authority(self) -> Mapping[str, object]:
        return self._json_script("seed_runtime_authority.py", "arm-acceptance")

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
        return subprocess.run(args, check=check, capture_output=True, text=True)


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
    except subprocess.CalledProcessError:
        print("status=failed reason=operation_failed", file=sys.stderr)
        return 1
    print(f"status={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
