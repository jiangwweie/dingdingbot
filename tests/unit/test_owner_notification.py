from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.application.owner_notification import (
    OwnerNotificationIntent,
    OwnerNotificationKind,
    OwnerNotificationSeverity,
    owner_notification_dedupe_key,
    render_owner_notification_card,
)


def _intent(**overrides) -> OwnerNotificationIntent:
    values = {
        "notification_kind": OwnerNotificationKind.OPPORTUNITY_DETECTED,
        "severity": OwnerNotificationSeverity.INFO,
        "correlation_id": "signal:signal-001",
        "strategy_group_id": "SOR-001",
        "symbol": "SOLUSDT",
        "side": "long",
        "occurred_at_ms": 1_800_000_000_000,
        "headline": "发现交易机会",
        "current_state": "系统正在进行下单前检查",
        "result_summary": "尚未下单",
        "plain_reason": "策略条件刚刚满足",
        "next_system_action": "系统会继续完成账户和风险检查",
        "owner_action_required": False,
        "owner_action": None,
        "technical_refs": ("blocker_class:fresh_signal", "ticket:null"),
        "template_version": "owner-notification-v1",
    }
    values.update(overrides)
    return OwnerNotificationIntent(**values)


def test_intent_requires_stable_correlation_and_owner_action_when_required() -> None:
    with pytest.raises(ValidationError, match="correlation_id"):
        _intent(correlation_id="")
    with pytest.raises(ValidationError, match="owner_action"):
        _intent(
            owner_action_required=True,
            owner_action=None,
            severity=OwnerNotificationSeverity.CRITICAL,
        )


def test_static_card_renders_owner_language_without_callback_or_technical_terms() -> None:
    payload = render_owner_notification_card(_intent())
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["template"] == "blue"
    assert "发现交易机会" in serialized
    assert "SOR-001" in serialized
    assert "SOLUSDT" in serialized
    assert "做多" in serialized
    assert "无需操作" in serialized
    assert "action" not in {element.get("tag") for element in payload["card"]["elements"]}
    for forbidden in (
        "blocker_class",
        "checkpoint",
        "FinalGate",
        "Operation Layer",
        "RequiredFacts",
        "evidence_ref",
        "ticket:null",
    ):
        assert forbidden not in serialized


def test_critical_card_is_red_and_requires_plain_owner_action() -> None:
    payload = render_owner_notification_card(
        _intent(
            notification_kind=OwnerNotificationKind.INTERVENTION_REQUIRED,
            severity=OwnerNotificationSeverity.CRITICAL,
            correlation_id="incident:unprotected:ticket-001",
            headline="持仓保护状态异常",
            current_state="已经开仓，但保护单状态无法确认",
            result_summary="系统已暂停该方向的新开仓",
            plain_reason="交易所保护单与内部记录不一致",
            next_system_action="系统继续核对订单和持仓",
            owner_action_required=True,
            owner_action="检查交易所持仓和保护单",
        )
    )

    assert payload["card"]["header"]["template"] == "red"
    assert "检查交易所持仓和保护单" in json.dumps(
        payload,
        ensure_ascii=False,
    )


def test_dedupe_key_is_stable_and_template_version_does_not_resend_history() -> None:
    first = _intent(template_version="owner-notification-v1")
    wording_update = _intent(template_version="owner-notification-v2")
    terminal = _intent(
        notification_kind=OwnerNotificationKind.OPPORTUNITY_NOT_EXECUTED,
    )

    assert owner_notification_dedupe_key("tokyo-runtime-server-monitor", first) == (
        owner_notification_dedupe_key(
            "tokyo-runtime-server-monitor",
            wording_update,
        )
    )
    assert owner_notification_dedupe_key(
        "tokyo-runtime-server-monitor",
        first,
    ) != owner_notification_dedupe_key(
        "tokyo-runtime-server-monitor",
        terminal,
    )
