#!/usr/bin/env python3
"""Project current V2 instrument rules from bounded Binance read-only GET facts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import sys

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402
from src.application.action_time.instrument_rule_projector import (  # noqa: E402
    load_active_instrument_rule_targets,
    parse_binance_usdm_instrument_rule_observations,
    project_current_instrument_rules,
)
from src.infrastructure.binance_usdm_rule_source import (  # noqa: E402
    DEFAULT_BASE_URL,
    fetch_binance_usdm_rule_source,
)


DEFAULT_ENV_FILE = Path("/home/ubuntu/brc-deploy/env/live-readonly.env")
DEFAULT_RUNTIME_PROFILE_ID = "owner-runtime-console-v1"
DEFAULT_VALIDITY_MS = 86_400_000
EXPECTED_INSTRUMENT_COUNT = 6


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    engine = sa.create_engine(normalize_sync_postgres_dsn(args.database_url))
    with engine.connect() as conn:
        targets = load_active_instrument_rule_targets(
            conn,
            runtime_profile_id=args.runtime_profile_id,
            expected_instrument_count=EXPECTED_INSTRUMENT_COUNT,
        )
    if not args.apply:
        print(
            json.dumps(
                {
                    "status": "plan_only",
                    "target_count": len(targets),
                    "exchange_write_called": False,
                    "files_written": 0,
                },
                sort_keys=True,
            )
        )
        return 0

    api_key = _env_value(
        ("EXCHANGE_API_KEY", "BINANCE_API_KEY", "binance_exchange_key"),
        env_file=args.env_file,
    )
    api_secret = _env_value(
        ("EXCHANGE_API_SECRET", "BINANCE_SECRET_KEY", "binance_exchange_secret"),
        env_file=args.env_file,
    )
    source = fetch_binance_usdm_rule_source(
        api_key=api_key or "",
        api_secret=api_secret or "",
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
    )
    observations = parse_binance_usdm_instrument_rule_observations(
        targets=targets,
        exchange_info_payload=source.exchange_info,
        leverage_bracket_payload=source.leverage_brackets,
        observed_at_ms=source.observed_at_ms,
        valid_until_ms=source.observed_at_ms + args.validity_ms,
        source_ref=source.source_ref,
    )
    with engine.begin() as conn:
        current_targets = load_active_instrument_rule_targets(
            conn,
            runtime_profile_id=args.runtime_profile_id,
            expected_instrument_count=EXPECTED_INSTRUMENT_COUNT,
        )
        if current_targets != targets:
            raise RuntimeError("instrument_rule_target_scope_changed_during_fetch")
        result = project_current_instrument_rules(
            conn,
            observations=observations,
            runtime_profile_id=args.runtime_profile_id,
            expected_instrument_count=EXPECTED_INSTRUMENT_COUNT,
        )
    print(
        json.dumps(
            {
                "status": "instrument_rules_projected",
                **result.model_dump(mode="json"),
                "exchange_write_called": False,
                "order_created": False,
                "files_written": 0,
            },
            sort_keys=True,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL") or os.getenv("DATABASE_URL") or "",
        required=not bool(os.getenv("PG_DATABASE_URL") or os.getenv("DATABASE_URL")),
    )
    parser.add_argument("--runtime-profile-id", default=DEFAULT_RUNTIME_PROFILE_ID)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-seconds", type=float, default=12)
    parser.add_argument("--validity-ms", type=int, default=DEFAULT_VALIDITY_MS)
    args = parser.parse_args(argv)
    if args.validity_ms <= 0:
        parser.error("--validity-ms must be positive")
    return args


def _env_value(names: tuple[str, ...], *, env_file: Path) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    values = _parse_env_file(env_file)
    for name in names:
        if values.get(name):
            return values[name]
    return None


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        try:
            parts = shlex.split(raw_value, comments=False, posix=True)
        except ValueError:
            parts = []
        values[key.strip()] = (
            parts[0] if len(parts) == 1 else raw_value.strip().strip("\"'")
        )
    return values


if __name__ == "__main__":
    raise SystemExit(main())
