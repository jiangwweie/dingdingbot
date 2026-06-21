from __future__ import annotations

import json

from src.application.runtime_advisory_event_adapter import (
    build_completion_audit_advisory_event,
    build_daily_check_advisory_event,
    build_review_due_advisory_event,
    build_trade_closed_advisory_event,
    build_watcher_packet_advisory_event,
)
from src.domain.llm_advisory import (
    LlmAdvisoryAllowedAction,
    LlmAdvisoryDeliveryChannel,
    LlmConsumableEventType,
)


NOW_MS = 1234567890


def test_daily_check_healthy_waiting_builds_ledger_only_digest():
    event = build_daily_check_advisory_event(
        {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
            "generated_at_utc": "2026-06-21T00:00:00Z",
            "notification": {
                "decision": "DONT_NOTIFY",
                "reason": "healthy_waiting_for_market",
            },
            "owner_summary": {
                "state": "等待机会",
                "current_action": "继续等待市场机会",
            },
            "checks": {
                "waiting_for_market": True,
                "blockers": [],
                "product_gaps": [],
                "fresh_signal_notification_policy_checked": True,
            },
        },
        now=NOW_MS,
        source_ref="output/runtime-monitor/latest-daily-check.json",
    )

    assert event.event_type == LlmConsumableEventType.DAILY_AUDIT_DIGEST
    assert event.delivery_policy == [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
    assert event.allowed_llm_actions == [LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT]
    assert event.dedupe_key == (
        "daily_check:waiting_for_market:healthy_waiting_for_market:none"
    )
    assert event.context_packet.safety["llm_not_execution_authority"] is True
    assert event.context_packet.safety["feishu_push_only"] is True
    assert event.execution_intent_created is False
    assert event.order_created is False
    assert event.exchange_called is False
    assert event.context_packet.source_refs == ["output/runtime-monitor/latest-daily-check.json"]


def test_daily_check_blocker_builds_feishu_push_explanation_event():
    event = build_daily_check_advisory_event(
        {
            "status": "temporarily_unavailable_deployment_issue",
            "notification": {"decision": "NOTIFY", "reason": "blocker_present"},
            "checks": {
                "blockers": ["owner_console_backend_inactive"],
                "waiting_for_market": False,
            },
        },
        now=NOW_MS,
    )

    assert event.delivery_policy == [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
    assert event.severity == "warning"
    assert event.allowed_llm_actions == [
        LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT,
        LlmAdvisoryAllowedAction.EXPLAIN_BLOCKER,
    ]
    assert "owner_console_backend_inactive" in event.dedupe_key
    assert event.owner_action_enabled is False
    assert event.live_ready is False


def test_monitor_refresh_needed_stays_ledger_only_when_owner_notify_false():
    event = build_daily_check_advisory_event(
        {
            "status": "waiting_for_market_monitor_refresh_needed",
            "runtime_status": "waiting_for_market",
            "notification": {
                "decision": "NOTIFY",
                "reason": "runtime_progress_cache_stale",
                "automation_notify": True,
                "owner_notify": False,
            },
            "checks": {"blockers": [], "waiting_for_market": True},
        },
        now=NOW_MS,
    )

    assert event.delivery_policy == [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
    assert event.event_type == LlmConsumableEventType.DAILY_AUDIT_DIGEST
    assert event.context_packet.runtime["notification"]["owner_notify"] is False
    assert event.context_packet.runtime["checks"]["waiting_for_market"] is True


def test_completion_audit_waiting_for_market_builds_digest_without_push():
    event = build_completion_audit_advisory_event(
        {
            "status": "not_complete_waiting_for_market",
            "runtime_status": "waiting_for_market",
            "goal_complete": False,
            "market_dependent_remaining": 5,
            "non_market_gaps": [],
        },
        now=NOW_MS,
    )

    assert event.event_type == LlmConsumableEventType.DAILY_AUDIT_DIGEST
    assert event.delivery_policy == [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
    assert event.context_packet.runtime["goal_complete"] is False
    assert event.context_packet.runtime["market_dependent_remaining"] == 5


def test_watcher_prepared_signal_builds_push_only_strategy_event_without_order_params():
    event = build_watcher_packet_advisory_event(
        {
            "status": "prepared_shadow_evidence_ready_for_owner_review",
            "packet_id": "watcher-ready-1",
            "notification": {"required": True, "reason": "owner_attention_required"},
            "latest_summary": {
                "blockers": [],
                "runtime_signal_summaries": [
                    {
                        "strategy_family_id": "MPG-001",
                        "symbol": "BTC/USDT:USDT",
                        "timeframe": "1h",
                        "side": "long",
                        "signal_summary": {
                            "status": "ready",
                            "signal_type": "would_enter",
                            "confidence": "0.81",
                            "reason_codes": ["fresh_signal"],
                            "side": "long",
                            "leverage": "3",
                            "entry_price": "100",
                        },
                    }
                ],
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "webhook_secret": "must-not-leak",
            },
        },
        now=NOW_MS,
        source_ref="watcher-tick.json",
    )

    payload_text = json.dumps(event.context_packet.model_dump(mode="json"), sort_keys=True)
    assert event.event_type == LlmConsumableEventType.STRATEGY_CANDIDATE_OBSERVED
    assert event.delivery_policy == [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
    assert event.strategy_family_ids == ["MPG-001"]
    assert event.symbol == "BTC/USDT:USDT"
    assert event.allowed_llm_actions == [
        LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT,
        LlmAdvisoryAllowedAction.EXPLAIN_MARKET_CONTEXT,
    ]
    assert "leverage" not in payload_text
    assert "entry_price" not in payload_text
    assert "webhook_secret" not in payload_text
    assert event.not_execution_authority is True
    assert event.order_created is False
    assert event.exchange_called is False


def test_watcher_no_signal_stays_ledger_only_digest():
    event = build_watcher_packet_advisory_event(
        {
            "status": "watching_no_signal",
            "notification": {
                "required": False,
                "reason": "waiting_for_market_no_owner_attention_needed",
            },
            "latest_summary": {
                "runtime_signal_summaries": [
                    {
                        "strategy_family_id": "MPG-001",
                        "symbol": "BTC/USDT:USDT",
                        "signal_summary": {
                            "signal_type": "no_action",
                            "reason_codes": ["no_signal"],
                        },
                    }
                ]
            },
        },
        now=NOW_MS,
    )

    assert event.event_type == LlmConsumableEventType.DAILY_AUDIT_DIGEST
    assert event.delivery_policy == [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
    assert event.strategy_family_ids == ["MPG-001"]


def test_trade_closed_and_review_due_events_are_push_only_review_inputs():
    trade_event = build_trade_closed_advisory_event(
        {
            "trade_id": "trade-1",
            "symbol": "BTC/USDT:USDT",
            "status": "closed",
            "review_status": "review_due",
            "outcome_summary": {"realized_pnl": "12.3", "side": "long"},
        },
        now=NOW_MS,
    )
    review_event = build_review_due_advisory_event(
        {
            "review_id": "review-1",
            "reason": "trade_closed_review_due",
            "strategy_family_ids": ["MPG-001"],
        },
        now=NOW_MS,
    )

    assert trade_event.event_type == LlmConsumableEventType.TRADE_CLOSED
    assert trade_event.delivery_policy == [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
    assert LlmAdvisoryAllowedAction.REVIEW_CLOSED_TRADE in trade_event.allowed_llm_actions
    assert "side" not in json.dumps(trade_event.context_packet.model_dump(mode="json"))
    assert review_event.event_type == LlmConsumableEventType.REVIEW_DUE
    assert review_event.delivery_policy == [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
    assert review_event.strategy_family_ids == ["MPG-001"]
