#!/usr/bin/env python3
"""Prepare an exact local manual release record; performs no SSH or deployment."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.owner_console.certify_release_candidate import (
    validate_owner_api_release_certification,
)
from scripts.owner_console.certify_static_release_candidate import (
    validate_owner_static_release_certification,
)
from scripts.trading_kernel.certify_release_candidate import (
    ReleaseCertificationLevel,
    load_release_certification_manifest,
)
from src.trading_kernel.domain.product_identity import (
    PRODUCT_ID,
    ManualReleaseBinding,
    require_manual_release_identity,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


def build_preparation(*, commit: str, schema_revision: str,
                      expected: ManualReleaseBinding | None = None,
                      observed: ManualReleaseBinding | None = None) -> dict[str, object]:
    if (expected is None) != (observed is None):
        raise ValueError("expected and fresh observed bindings are required together")
    if expected is not None and observed is not None:
        require_manual_release_identity(expected, observed)
        if expected.release_commit != commit or expected.schema_revision != schema_revision:
            raise ValueError("binding differs from exact candidate")
    return {
        "product_id": PRODUCT_ID,
        "release_commit": commit,
        "schema_revision": schema_revision,
        "deployment_authorized": False,
        "server_binding": "missing" if expected is None else "local_comparison_only",
        "remaining_gates": ["owner_deployment_confirmation", "fresh_server_account_database_identity",
            "real_app_protocol_acceptance", "new_server_provisioning_and_postflight"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-binding", type=Path)
    parser.add_argument("--observed-binding", type=Path)
    args = parser.parse_args(argv)
    commit = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=REPO_ROOT, text=True).strip()
    load_release_certification_manifest(REPO_ROOT, commit, ReleaseCertificationLevel.R4)
    validate_owner_api_release_certification(REPO_ROOT, commit)
    validate_owner_static_release_certification(REPO_ROOT, commit)
    def read(path: Path | None) -> ManualReleaseBinding | None:
        return None if path is None else ManualReleaseBinding.model_validate_json(path.read_text())
    result = build_preparation(commit=commit, schema_revision=CURRENT_SCHEMA_REVISION,
        expected=read(args.expected_binding), observed=read(args.observed_binding))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
