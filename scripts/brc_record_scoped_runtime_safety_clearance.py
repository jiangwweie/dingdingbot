"""Record scoped runtime-safety clearance metadata for the BNB one-shot trial.

This script writes PG metadata only. It does not create an ExecutionIntent,
place orders, grant execution/order permission, enable auto execution, start
runtime, or call exchange APIs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from src.application.strategy_trial_architecture_governance import (
    build_bnb_strategy_trial_architecture_governance,
)
from src.infrastructure.database import get_pg_session_maker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record scoped GKS and startup-guard clearance metadata for MI-001-BNB-LONG."
    )
    parser.add_argument("--authorization-id", default=None)
    parser.add_argument("--actor", default="owner")
    parser.add_argument("--source", default="owner_console_runtime_safety_handoff")
    parser.add_argument("--ttl-minutes", type=int, default=120)
    parser.add_argument(
        "--reason",
        default="Owner-authorized MI-001-BNB-LONG scoped runtime safety clearance",
    )
    return parser


async def main() -> None:
    args = _parser().parse_args()
    if args.ttl_minutes <= 0:
        raise SystemExit("ttl-minutes must be positive")
    carrier = (
        build_bnb_strategy_trial_architecture_governance().owner_review_artifact.carrier
    )
    now_ms = int(time.time() * 1000)
    expires_at_ms = now_ms + args.ttl_minutes * 60 * 1000
    session_maker = get_pg_session_maker()
    async with session_maker() as session:
        async with session.begin():
            auth = await _read_authorization(
                session,
                authorization_id=args.authorization_id,
                carrier=carrier,
            )
            if auth is None:
                raise SystemExit("matching unconsumed Owner authorization not found")
            auth_id = str(auth["authorization_id"])
            rows = []
            for clearance_type in ["gks", "startup_guard"]:
                clearance_id = f"{clearance_type}-{auth_id}"
                await _upsert_clearance(
                    session,
                    clearance_id=clearance_id,
                    clearance_type=clearance_type,
                    authorization=auth,
                    expires_at_ms=expires_at_ms,
                    actor=args.actor,
                    source=args.source,
                    reason=args.reason,
                    now_ms=now_ms,
                )
                rows.append(
                    {
                        "clearance_id": clearance_id,
                        "clearance_type": clearance_type,
                        "authorization_id": auth_id,
                        "carrier_id": auth["carrier_id"],
                        "symbol": auth["symbol"],
                        "side": auth["side"],
                        "expires_at_ms": expires_at_ms,
                        "status": "active",
                    }
                )
    print(
        json.dumps(
            {
                "recorded": rows,
                "metadata_only": True,
                "execution_intent_created": False,
                "order_created": False,
                "order_permission_granted": False,
                "execution_permission_granted": False,
                "auto_execution_enabled": False,
            },
            sort_keys=True,
        )
    )


async def _read_authorization(session: Any, *, authorization_id: str | None, carrier: Any) -> Any:
    auth_filter = "AND authorization_id = :authorization_id" if authorization_id else ""
    result = await session.execute(
        text(
            f"""
            SELECT
                authorization_id,
                carrier_id,
                symbol,
                side,
                max_notional,
                quantity,
                leverage,
                protection_plan_type
            FROM brc_bounded_live_trial_authorizations
            WHERE carrier_id = :carrier_id
              AND symbol IN (:symbol, :runtime_symbol)
              AND side = :side
              AND max_notional = :max_notional
              AND quantity = :quantity
              AND leverage = :leverage
              AND protection_plan_type = :protection_plan_type
              AND single_use = :true_value
              AND consumed = :false_value
              AND live_authorized = :true_value
              AND live_ready = :false_value
              AND order_permission_granted = :false_value
              AND execution_permission_granted = :false_value
              AND execution_intent_created = :false_value
              AND order_created = :false_value
              AND auto_execution_enabled = :false_value
              {auth_filter}
            ORDER BY created_at_ms DESC
            LIMIT 1
            """
        ),
        {
            "authorization_id": authorization_id,
            "carrier_id": carrier.carrier_id,
            "symbol": carrier.symbol,
            "runtime_symbol": carrier.runtime_symbol,
            "side": carrier.side,
            "max_notional": carrier.max_notional,
            "quantity": carrier.quantity,
            "leverage": carrier.leverage,
            "protection_plan_type": carrier.protection_plan_type,
            "true_value": True,
            "false_value": False,
        },
    )
    return result.mappings().first()


async def _upsert_clearance(
    session: Any,
    *,
    clearance_id: str,
    clearance_type: str,
    authorization: Any,
    expires_at_ms: int,
    actor: str,
    source: str,
    reason: str,
    now_ms: int,
) -> None:
    metadata = {
        "scope": "MI-001-BNB-LONG_one_shot_runtime_safety",
        "metadata_only": True,
        "does_not_grant_execution_permission": True,
        "does_not_create_execution_intent": True,
        "does_not_create_order": True,
    }
    await session.execute(
        text(
            """
            INSERT INTO brc_scoped_runtime_safety_clearances (
                clearance_id,
                clearance_type,
                authorization_id,
                carrier_id,
                symbol,
                side,
                max_notional,
                quantity,
                leverage,
                protection_plan_type,
                status,
                expires_at_ms,
                actor,
                source,
                reason,
                metadata,
                created_at_ms,
                updated_at_ms
            )
            VALUES (
                :clearance_id,
                :clearance_type,
                :authorization_id,
                :carrier_id,
                :symbol,
                :side,
                :max_notional,
                :quantity,
                :leverage,
                :protection_plan_type,
                'active',
                :expires_at_ms,
                :actor,
                :source,
                :reason,
                CAST(:metadata AS jsonb),
                :now_ms,
                :now_ms
            )
            ON CONFLICT (clearance_id) DO UPDATE SET
                status = 'active',
                expires_at_ms = EXCLUDED.expires_at_ms,
                actor = EXCLUDED.actor,
                source = EXCLUDED.source,
                reason = EXCLUDED.reason,
                metadata = EXCLUDED.metadata,
                updated_at_ms = EXCLUDED.updated_at_ms
            """
        ),
        {
            "clearance_id": clearance_id,
            "clearance_type": clearance_type,
            "authorization_id": authorization["authorization_id"],
            "carrier_id": authorization["carrier_id"],
            "symbol": authorization["symbol"],
            "side": authorization["side"],
            "max_notional": Decimal(authorization["max_notional"]),
            "quantity": Decimal(authorization["quantity"]),
            "leverage": Decimal(authorization["leverage"]),
            "protection_plan_type": authorization["protection_plan_type"],
            "expires_at_ms": expires_at_ms,
            "actor": actor,
            "source": source,
            "reason": reason,
            "metadata": json.dumps(metadata, sort_keys=True),
            "now_ms": now_ms,
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
