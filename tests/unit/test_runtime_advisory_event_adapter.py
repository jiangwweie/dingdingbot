from __future__ import annotations

import json

from src.application.runtime_advisory_event_adapter import (
    build_completion_audit_advisory_event,
    build_daily_check_advisory_event,
    build_review_due_advisory_event,
    build_trade_closed_advisory_event,
    build_watcher_artifact_advisory_event,
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
                "notification_result": "DONT_NOTIFY",
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
    assert event.context_artifact.safety["llm_not_execution_authority"] is True
    assert event.context_artifact.safety["feishu_push_only"] is True
    assert event.execution_intent_created is False
    assert event.order_created is False
    assert event.exchange_called is False
    assert event.context_artifact.source_refs == ["output/runtime-monitor/latest-daily-check.json"]


def test_daily_check_blocker_builds_feishu_push_explanation_event():
    event = build_daily_check_advisory_event(
        {
            "status": "temporarily_unavailable_deployment_issue",
            "notification": {"notification_result": "NOTIFY", "reason": "blocker_present"},
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


def test_daily_check_ignores_legacy_packet_id_for_event_identity():
    event = build_daily_check_advisory_event(
        {
            "packet_id": "legacy-daily-packet-id",
            "status": "waiting_for_market",
            "notification": {
                "notification_result": "DONT_NOTIFY",
                "reason": "healthy_waiting_for_market",
            },
            "checks": {"blockers": [], "waiting_for_market": True},
        },
        now=NOW_MS,
    )

    assert event.source_id == "strategygroup_runtime_daily_check"
    assert event.context_artifact.artifact_id == "llm-daily-check-waiting_for_market"
    assert "legacy-daily-packet-id" not in event.context_artifact.artifact_id


def test_monitor_refresh_needed_stays_ledger_only_when_owner_notify_false():
    event = build_daily_check_advisory_event(
        {
            "status": "waiting_for_market_monitor_refresh_needed",
            "runtime_status": "waiting_for_market",
            "notification": {
                "notification_result": "NOTIFY",
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
    assert event.context_artifact.runtime["notification"]["owner_notify"] is False
    assert event.context_artifact.runtime["checks"]["waiting_for_market"] is True


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
    assert event.context_artifact.runtime["goal_complete"] is False
    assert event.context_artifact.runtime["market_dependent_remaining"] == 5


def test_watcher_prepared_signal_builds_push_only_strategy_event_without_order_params():
    event = build_watcher_artifact_advisory_event(
        {
            "status": "prepared_shadow_evidence_ready_for_owner_review",
            "artifact_id": "watcher-ready-1",
            "notification": {"required": True, "reason": "owner_attention_required"},
            "operator_command_plan": {"next_step": "legacy_should_not_surface"},
            "watcher_tick_plan": {
                "non_authority_checkpoint": "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope",
                "not_execution_authority": True,
            },
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
                "webhookSecret": "must-not-leak-camel",
                "ApiKey": "must-not-leak-pascal",
                "client-order-id": "must-not-leak-kebab",
                "ExchangeOrderId": "must-not-leak-exchange",
                "accessToken": "must-not-leak-token",
                "X-Signature": "must-not-leak-signature",
                "preparedAuthorizationId": "must-not-leak-authorization",
            },
            "operator_evidence": {"status": "operator_projection_ready"},
            "wakeup_evidence": {"status": "wakeup_projection_ready"},
        },
        now=NOW_MS,
        source_ref="watcher-tick.json",
    )

    payload_text = json.dumps(event.context_artifact.model_dump(mode="json"), sort_keys=True)
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
    assert "webhookSecret" not in payload_text
    assert "ApiKey" not in payload_text
    assert "client-order-id" not in payload_text
    assert "ExchangeOrderId" not in payload_text
    assert "accessToken" not in payload_text
    assert "X-Signature" not in payload_text
    assert "preparedAuthorizationId" not in payload_text
    assert "operator_command_plan" not in payload_text
    assert "legacy_should_not_surface" not in payload_text
    assert event.context_artifact.runtime["watcher_tick_plan"][
        "not_execution_authority"
    ] is True
    assert "must-not-leak" not in payload_text
    assert event.not_execution_authority is True
    assert event.order_created is False
    assert event.exchange_called is False
    assert event.context_artifact.audit["operator_evidence_status"] == (
        "operator_projection_ready"
    )
    assert event.context_artifact.audit["wakeup_evidence_status"] == (
        "wakeup_projection_ready"
    )
    assert "operator_packet_status" not in event.context_artifact.audit
    assert "wakeup_packet_status" not in event.context_artifact.audit


def test_watcher_no_signal_stays_ledger_only_digest():
    event = build_watcher_artifact_advisory_event(
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


def test_watcher_ignores_legacy_wakeup_packet_for_current_status():
    event = build_watcher_artifact_advisory_event(
        {
            "artifact_id": "watcher-legacy-input",
            "notification": {"required": True, "reason": "legacy_input"},
            "wakeup_packet": {"status": "fresh_signal_processing"},
            "latest_summary": {
                "runtime_signal_summaries": [
                    {
                        "strategy_family_id": "MPG-001",
                        "symbol": "BTC/USDT:USDT",
                        "signal_summary": {
                            "signal_type": "would_enter",
                            "reason_codes": ["legacy_wakeup_packet"],
                        },
                    }
                ]
            },
        },
        now=NOW_MS,
    )

    assert event.context_artifact.market["status"] == "unknown"
    assert event.event_type == LlmConsumableEventType.DAILY_AUDIT_DIGEST
    assert event.context_artifact.audit["wakeup_evidence_status"] == ""
    assert "wakeup_packet_status" not in event.context_artifact.audit


def test_watcher_ignores_legacy_packet_id_for_event_identity():
    event = build_watcher_artifact_advisory_event(
        {
            "packet_id": "legacy-watcher-packet-id",
            "status": "watching_no_signal",
            "notification": {
                "required": False,
                "reason": "waiting_for_market_no_owner_attention_needed",
            },
            "latest_summary": {"runtime_signal_summaries": []},
        },
        now=NOW_MS,
    )

    assert event.source_id == "runtime_signal_watcher_artifact"
    assert event.context_artifact.artifact_id == "llm-watcher-watching_no_signal"
    assert "legacy-watcher-packet-id" not in event.context_artifact.artifact_id


def test_trade_closed_and_review_due_events_are_push_only_review_inputs():
    trade_event = build_trade_closed_advisory_event(
        {
            "trade_id": "trade-1",
            "symbol": "BTC/USDT:USDT",
            "status": "closed",
            "review_status": "review_due",
            "outcome_summary": {
                "realized_pnl": "12.3",
                "side": "long",
                "entryPrice": "100",
                "stop-loss": "98",
                "takeProfit": "120",
            },
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
    trade_payload = json.dumps(trade_event.context_artifact.model_dump(mode="json"))
    assert "side" not in trade_payload
    assert "entryPrice" not in trade_payload
    assert "stop-loss" not in trade_payload
    assert "takeProfit" not in trade_payload
    assert review_event.event_type == LlmConsumableEventType.REVIEW_DUE
    assert review_event.delivery_policy == [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
    assert review_event.strategy_family_ids == ["MPG-001"]
