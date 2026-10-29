"""Bounded readonly verification of the effective budget and its Owner lineage."""

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.directional_risk import RULE_DIGEST, RULE_ID
from src.trading_kernel.domain.risk_budget import (
    RiskBudgetChangeRequest,
    policy_budget_is_valid,
)
from src.trading_kernel.infrastructure.pg_directional_risk_repository import (
    PostgresDirectionalRiskRepository,
)
from src.trading_kernel.infrastructure.pg_models import (
    directional_risk_events,
    owner_policy_events,
    runtime_profiles,
)


async def risk_budget_authority_valid(connection: AsyncConnection, policy) -> bool:
    if policy is None or not policy_budget_is_valid(policy):
        return False
    try:
        identities = (
            await connection.execute(
                sa.select(runtime_profiles.c.venue_id, runtime_profiles.c.account_id)
                .distinct()
                .limit(3)
            )
        ).all()
        if len(identities) != 1:
            return False
        venue_id, account_id = identities[0]
        control = await PostgresDirectionalRiskRepository(connection).get(
            venue_id, account_id
        )
        if control is None:
            return False
        event = (
            (
                await connection.execute(
                    sa.select(owner_policy_events)
                    .where(
                        owner_policy_events.c.owner_policy_id
                        == policy["owner_policy_id"],
                        owner_policy_events.c.operation == "owner_control_risk_budget",
                        owner_policy_events.c.policy_version
                        <= policy["policy_version"],
                    )
                    .order_by(owner_policy_events.c.policy_version.desc())
                    .limit(1)
                )
            )
            .mappings()
            .one_or_none()
        )
        if event is None:
            return policy["max_ticket_stop_risk_fraction"] == Decimal(".02")
        payload = event["payload"]
        request_id = payload["request_id"]
        journal = await connection.scalar(
            sa.select(directional_risk_events.c.payload).where(
                directional_risk_events.c.event_id == request_id
            )
        )
        effective = await connection.scalar(
            sa.select(directional_risk_events.c.payload).where(
                directional_risk_events.c.event_id == request_id + ":effective"
            )
        )
        if journal is None or effective is None:
            return False
        request = RiskBudgetChangeRequest.model_validate(journal["request"])
        return bool(
            request.venue_id == venue_id
            and request.account_id == account_id
            and request.owner_policy_id == policy["owner_policy_id"]
            and request.baseline
            == policy["max_ticket_stop_risk_fraction"]
            == Decimal(payload["baseline"])
            and payload["rule_id"] == RULE_ID
            and payload["rule_digest"] == RULE_DIGEST
            and journal["authentication_strength"] == "totp_step_up"
            and effective["result"]["status"] == "effective"
            and effective["result"]["policy_version"] == event["policy_version"]
        )
    except (ValueError, KeyError, TypeError):
        return False
