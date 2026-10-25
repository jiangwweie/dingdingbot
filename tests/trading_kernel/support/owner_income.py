"""Shared disposable Owner income SQL fixtures, without test-module imports."""
from __future__ import annotations

import json

import asyncpg
from sqlalchemy.engine import make_url

from tests.trading_kernel.integration.owner_console_support import ADMIN_DSN


async def _execute_owner_console_admin(
    dsn: str,
    statement: str,
    *args: object,
) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    try:
        await connection.execute(statement, *args)
    finally:
        await connection.close()

async def _seed_owner_console_trades(
    dsn: str,
    *,
    sparse_candidate_count: int = 0,
    sparse_complete_ordinals: tuple[int, ...] = (),
) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    digest = "sha256:" + "a" * 64
    created_at_ms = 1_800_000_000_000
    tickets = (
        (
            "ticket:z",
            "strategy-group:alpha",
            "BTCUSDT",
            "long",
            "issued",
            created_at_ms,
            None,
            "active:ticket:z",
        ),
        (
            "ticket:y",
            "strategy-group:alpha",
            "ETHUSDT",
            "short",
            "terminal",
            created_at_ms,
            created_at_ms + 30_000,
            None,
        ),
        (
            "ticket:x",
            "strategy-group:beta",
            "BTCUSDT",
            "short",
            "terminal",
            created_at_ms,
            created_at_ms + 30_000,
            None,
        ),
        (
            "ticket:w",
            "strategy-group:beta",
            "SOLUSDT",
            "long",
            "terminal",
            created_at_ms - 100,
            created_at_ms + 30_000,
            None,
        ),
        (
            "ticket:v",
            "strategy-group:gamma",
            "BNBUSDT",
            "long",
            "terminal",
            created_at_ms - 200,
            created_at_ms + 30_000,
            None,
        ),
    )
    sparse_complete = set(sparse_complete_ordinals)
    sparse_ticket_ids = tuple(
        f"ticket:sparse:{ordinal:04d}"
        for ordinal in range(sparse_candidate_count)
    )
    tickets = (
        *tickets,
        *(
            (
                ticket_id,
                "strategy-group:sparse",
                f"SPARSE{ordinal:04d}USDT",
                "long",
                "terminal",
                created_at_ms - 1_000 - ordinal,
                created_at_ms + 20_000 - ordinal,
                None,
            )
            for ordinal, ticket_id in enumerate(sparse_ticket_ids)
        ),
    )
    try:
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms, activated_at_ms, retired_at_ms,
                    abandoned_at_ms, abandon_reason_code
                ) VALUES (
                    'universe:owner-console-trades', 'strategy-group:test',
                    'event-spec:test', 1, $1, 'active', $2, $2,
                    NULL, NULL, NULL
                )
                """,
                digest,
                created_at_ms,
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_tickets (
                    ticket_id, exposure_episode_id, signal_event_id,
                    strategy_group_id, strategy_version_id, event_spec_id,
                    universe_version_id, universe_semantic_digest,
                    runtime_profile_id, owner_policy_id, owner_policy_version,
                    runtime_scope_id, runtime_scope_version, account_id,
                    venue_id, exchange_instrument_id, position_side,
                    netting_domain_key, active_netting_domain_key,
                    exposure_family, active_family_ticket_count_at_claim,
                    family_ticket_limit, directional_risk_at_stop_at_claim,
                    directional_stop_risk_limit_fraction,
                    min_materialization_ratio, minimum_stop_risk_budget,
                    exit_policy_id, exit_policy_semantic_hash,
                    entry_reference_price, quantity, notional,
                    capacity_claim_id, planned_stop_risk_budget,
                    post_fill_stop_risk_limit, selected_leverage,
                    leverage_change_required, reserved_margin,
                    risk_reservation_basis, margin_mode,
                    cross_margin_stress_model_id, post_stop_stress_multiple,
                    claim_stress_proof_digest, risk_at_stop,
                    entry_order_type, entry_limit_price, initial_stop_price,
                    pre_tp1_reclaim_price, exposure_session_end_ms,
                    take_profit_prices, take_profit_quantities, fact_digest,
                    decision_digest, status, created_at_ms, expires_at_ms,
                    terminal_at_ms
                ) VALUES (
                    $1::varchar(160), 'episode:' || $1::varchar(160),
                    'signal:' || $1::varchar(160), $2::varchar(160),
                    'strategy-version:test', 'event-spec:test',
                    'universe:owner-console-trades', $9::text,
                    'profile:owner-console', 'policy:owner-console', 1,
                    'runtime-scope:test', 1, 'owner-console-account',
                    'binance-usdm', $3::varchar(160), $4::varchar(160),
                    'binance-usdm:owner-console-account:'
                        || $3::varchar(160) || ':' || $4::varchar(160),
                    $8::varchar(160), 'opening_range', 0, 3, 0, 0.04, 0.5, 1,
                    'exit-policy:test', 'sha256:' || repeat('b', 64),
                    100, 1, 100, 'claim:' || $1::varchar(160),
                    1, 1.1, 1, false, 100,
                    'stop_risk', 'cross', 'stress:test', 2,
                    'sha256:' || repeat('c', 64), 1, 'market', NULL, 99,
                    NULL, NULL, '[]'::jsonb, '[]'::jsonb,
                    'sha256:' || repeat('d', 64),
                    'sha256:' || repeat('e', 64), $5::varchar(160),
                    $6::bigint, $6::bigint + 60_000, $7::bigint
                )
                """,
                tuple((*ticket, digest) for ticket in tickets),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_aggregates (
                    ticket_id, status, version, last_event_sequence,
                    entry_lane_held, position_qty, average_fill_price,
                    actual_stop_risk, venue_reported_liquidation_price,
                    post_fill_risk_status, post_fill_disposition,
                    post_fill_stress_status, post_fill_stress_proof_digest,
                    protected_qty, entry_exchange_order_id,
                    initial_stop_exchange_order_id,
                    active_stop_exchange_order_id, active_stop_price,
                    tp1_exchange_order_id, tp1_target_qty, tp1_filled_qty,
                    break_even_floor_price,
                    pending_replaced_stop_exchange_order_id,
                    pending_stop_price, pending_stop_watermark_ms,
                    runner_stop_watermark_ms, pending_cancel_exchange_order_id,
                    exit_exchange_order_id, review_id, lifecycle_due_at_ms,
                    reconciliation_due_at_ms, updated_at_ms
                ) VALUES (
                    $1::varchar(160), $2::varchar(160),
                    1, 1, false, 0, 100, 1, NULL,
                    'within_limit', 'continue', 'within_limit',
                    'sha256:' || repeat('f', 64), 0,
                    'entry:' || $1::varchar(160),
                    NULL, NULL, NULL, NULL, 0, 0, NULL, NULL, NULL,
                    NULL, NULL, NULL, 'exit:' || $1::varchar(160),
                    $3::varchar(160), NULL, NULL, $4::bigint
                )
                """,
                (
                    ("ticket:z", "position_protected", None, created_at_ms),
                    ("ticket:y", "terminal", "review:y:v2", created_at_ms),
                    ("ticket:x", "terminal", None, created_at_ms),
                    ("ticket:w", "terminal", "review:w:v1", created_at_ms),
                    ("ticket:v", "terminal", "review:v:v1", created_at_ms),
                    *(
                        (
                            ticket_id,
                            "terminal",
                            f"review:sparse:{ordinal:04d}",
                            created_at_ms + 20_000 - ordinal,
                        )
                        for ordinal, ticket_id in enumerate(sparse_ticket_ids)
                    ),
                ),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_reviews (
                    review_id, ticket_id, revision, supersedes_review_id,
                    outcome, metrics, decision_impact, created_at_ms
                ) VALUES (
                    $1::varchar(160), $2::varchar(160), $3::bigint,
                    $4::varchar(160), 'terminal_flat', $5::jsonb, '{}',
                    $6::bigint
                )
                """,
                (
                    (
                        "review:y:v1",
                        "ticket:y",
                        1,
                        None,
                        json.dumps(
                            {
                                "economics_completeness": "complete",
                                "gross_realized_pnl_quote": "1000",
                                "trading_fees_quote": "1",
                                "funding_quote": "0",
                                "net_pnl_quote": "999",
                                "planned_r_multiple": "99",
                            }
                        ),
                        created_at_ms + 50_000,
                    ),
                    (
                        "review:y:v2",
                        "ticket:y",
                        2,
                        "review:y:v1",
                        json.dumps(
                            {
                                "economics_completeness": "complete",
                                "gross_realized_pnl_quote": "4.0000",
                                "trading_fees_quote": "0.4000",
                                "funding_quote": "-0.0900",
                                "net_pnl_quote": "3.5100",
                                "planned_r_multiple": "0.4800",
                            }
                        ),
                        created_at_ms + 40_000,
                    ),
                    (
                        "review:w:v1",
                        "ticket:w",
                        1,
                        None,
                        json.dumps(
                            {
                                "economics_completeness": "funding_unavailable",
                                "gross_realized_pnl_quote": "4.0000",
                                "trading_fees_quote": "0.4000",
                                "funding_quote": None,
                                "net_pnl_quote": None,
                                "planned_r_multiple": None,
                                "funding_unavailable_reason": (
                                    "overlapping_instrument_exposure"
                                ),
                            }
                        ),
                        created_at_ms + 40_000,
                    ),
                    (
                        "review:v:v1",
                        "ticket:v",
                        1,
                        None,
                        json.dumps(
                            {
                                "economics_completeness": "complete",
                                "gross_realized_pnl_quote": "4.0000",
                                "trading_fees_quote": "0.4000",
                                "funding_quote": "-0.0900",
                                "planned_r_multiple": "0.4800",
                            }
                        ),
                        created_at_ms + 40_000,
                    ),
                    *(
                        (
                            f"review:sparse:{ordinal:04d}",
                            ticket_id,
                            1,
                            None,
                            json.dumps(
                                {
                                    "economics_completeness": "complete",
                                    "gross_realized_pnl_quote": "4.0000",
                                    "trading_fees_quote": "0.4000",
                                    "funding_quote": "-0.0900",
                                    "net_pnl_quote": "3.5100",
                                    "planned_r_multiple": "0.4800",
                                }
                                if ordinal in sparse_complete
                                else {
                                    "economics_completeness": (
                                        "funding_unavailable"
                                    ),
                                    "gross_realized_pnl_quote": "4.0000",
                                    "trading_fees_quote": "0.4000",
                                    "funding_quote": None,
                                    "net_pnl_quote": None,
                                    "planned_r_multiple": None,
                                    "funding_unavailable_reason": (
                                        "overlapping_instrument_exposure"
                                    ),
                                }
                            ),
                            created_at_ms + 40_000 - ordinal,
                        )
                        for ordinal, ticket_id in enumerate(sparse_ticket_ids)
                    ),
                ),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_events (
                    event_id, ticket_id, sequence, event_type, payload,
                    occurred_at_ms
                ) VALUES (
                    $1::varchar(160), 'ticket:y', $2::bigint,
                    'ExitRequested', $3::jsonb, $4::bigint
                )
                """,
                (
                    (
                        "event:y:exit-requested",
                        10,
                        json.dumps(
                            {
                                "event_id": "event:y:exit-requested",
                                "ticket_id": "ticket:y",
                                "sequence": 10,
                                "occurred_at_ms": created_at_ms + 20_000,
                                "reason": "strategy_exit",
                            }
                        ),
                        created_at_ms + 20_000,
                    ),
                    (
                        "event:y:exit-retry",
                        11,
                        json.dumps(
                            {
                                "event_id": "event:y:exit-retry",
                                "ticket_id": "ticket:y",
                                "sequence": 11,
                                "occurred_at_ms": created_at_ms + 21_000,
                                "reason": "recover_exit_rejection",
                            }
                        ),
                        created_at_ms + 21_000,
                    ),
                ),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_events (
                    event_id, ticket_id, sequence, event_type, payload,
                    occurred_at_ms
                ) VALUES (
                    $1::varchar(160), 'ticket:y', $2::bigint,
                    $3::varchar(160), $4::jsonb, $5::bigint
                )
                """,
                (
                    (
                        "event:y:entry-rejected",
                        1,
                        "EntryRejected",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 1_000,
                    ),
                    (
                        "event:y:entry-filled",
                        2,
                        "EntryFilled",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 2_000,
                    ),
                    (
                        "event:y:initial-stop-rejected",
                        3,
                        "InitialStopRejected",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 3_000,
                    ),
                    (
                        "event:y:initial-stop-confirmed",
                        4,
                        "InitialStopConfirmed",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 4_000,
                    ),
                    (
                        "event:y:position-flat-confirmed",
                        12,
                        "PositionFlatConfirmed",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 27_000,
                    ),
                    (
                        "event:y:reconciliation-matched",
                        13,
                        "ReconciliationMatched",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 28_000,
                    ),
                    (
                        "event:y:budget-settled",
                        14,
                        "BudgetSettled",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 29_000,
                    ),
                ),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_events (
                    event_id, ticket_id, sequence, event_type, payload,
                    occurred_at_ms
                ) VALUES (
                    'event:' || $1::varchar(160) || ':' || lower($3::text),
                    $1::varchar(160), $2::bigint, $3::varchar(160),
                    $4::jsonb, $5::bigint
                )
                """,
                tuple(
                    (
                        ticket_id,
                        sequence,
                        event_type,
                        json.dumps(
                            {
                                "event_id": (
                                    f"event:{ticket_id}:{event_type.lower()}"
                                ),
                                "ticket_id": ticket_id,
                                "sequence": sequence,
                                "occurred_at_ms": (
                                    created_at_ms + occurred_offset
                                ),
                                **(
                                    {"reason": "strategy_exit"}
                                    if event_type == "ExitRequested"
                                    else {}
                                ),
                            }
                        ),
                        created_at_ms + occurred_offset,
                    )
                    for ticket_id in (
                        "ticket:x",
                        "ticket:w",
                        "ticket:v",
                        *sparse_ticket_ids,
                    )
                    for sequence, event_type, occurred_offset in (
                        (1, "EntryFilled", 1_000),
                        (2, "InitialStopConfirmed", 2_000),
                        (3, "ExitRequested", 20_000),
                        (4, "PositionFlatConfirmed", 27_000),
                        (5, "ReconciliationMatched", 28_000),
                        (6, "BudgetSettled", 29_000),
                    )
                    if not (
                        ticket_id == "ticket:v"
                        and event_type == "ExitRequested"
                    )
                ),
            )
            await connection.execute(
                """
                INSERT INTO brc_runtime_incidents (
                    incident_id, ticket_id, incident_kind, status,
                    first_blocker, entry_block_scope, entry_block_key,
                    details, opened_at_ms, resolved_at_ms
                ) VALUES (
                    'incident:z:older-open', 'ticket:z', 'entry_outcome_unknown',
                    'open', 'exact recovery required', 'none', NULL, '{}',
                    $1, NULL
                )
                """,
                created_at_ms - 120_000,
            )
            await connection.executemany(
                """
                INSERT INTO brc_runtime_incidents (
                    incident_id, ticket_id, incident_kind, status,
                    first_blocker, entry_block_scope, entry_block_key,
                    details, opened_at_ms, resolved_at_ms
                ) VALUES (
                    'incident:z:resolved:' || $1::integer::text, 'ticket:z',
                    'recovered_incident', 'resolved', 'resolved', 'none', NULL,
                    '{}', $2::bigint, $2::bigint + 1
                )
                """,
                tuple(
                    (number, created_at_ms - 30_000 + number)
                    for number in range(1, 22)
                ),
            )
            await connection.executemany(
                """
                INSERT INTO brc_runtime_incidents (
                    incident_id, ticket_id, incident_kind, status,
                    first_blocker, entry_block_scope, entry_block_key,
                    details, opened_at_ms, resolved_at_ms
                ) VALUES (
                    $1::varchar(160), $2::varchar(160), $3::varchar(160),
                    $4::varchar(160), $5::text, 'none', NULL, '{}',
                    $6::bigint, $7::bigint
                )
                """,
                (
                    (
                        "incident:y:resolved",
                        "ticket:y",
                        "exit_outcome_unknown",
                        "resolved",
                        "automatic recovery complete",
                        created_at_ms + 25_000,
                        created_at_ms + 26_000,
                    ),
                    (
                        "incident:w:open",
                        "ticket:w",
                        "funding_attribution_unavailable",
                        "open",
                        "exact evidence unavailable",
                        created_at_ms + 25_000,
                        None,
                    ),
                ),
            )
    finally:
        await connection.close()
