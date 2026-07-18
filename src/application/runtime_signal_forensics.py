"""Pure reduction of PG runtime lineage into an Owner-readable explanation."""

from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.owner_notification import owner_correlation_id


class RuntimeSignalForensicsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    strategy_group_id: str | None = None
    symbol: str | None = None
    side: Literal["long", "short"] | None = None
    limit: int = Field(default=200, ge=1, le=1000)

    @model_validator(mode="after")
    def _valid_window(self) -> "RuntimeSignalForensicsQuery":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be later than start_ms")
        return self


class RuntimeSignalFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_event_id: str
    strategy_group_id: str
    symbol: str
    side: str | None
    observed_at_ms: int
    chain_stage: str
    classification: str
    first_blocker: str | None
    explanation: str
    action_time_invocation_id: str | None = None
    promotion_candidate_id: str | None = None
    action_time_lane_input_id: str | None = None
    ticket_id: str | None = None
    process_name: str | None = None
    process_state: str | None = None
    notification_state: str = "not_recorded"
    net_pnl: str | None = None
    r_multiple: str | None = None


class RuntimeSignalForensicsResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_name: str = Field(
        default="brc.runtime_signal_forensics.v2", alias="schema"
    )
    start_ms: int
    end_ms: int
    conclusion_code: str
    conclusion: str
    market_absence_proven: bool
    findings: tuple[RuntimeSignalFinding, ...]
    row_counts: dict[str, int]
    forbidden_effects: dict[str, bool]


def reduce_runtime_signal_forensics(
    query: RuntimeSignalForensicsQuery,
    rows: Mapping[str, Any],
) -> RuntimeSignalForensicsResult:
    signals = [
        row
        for row in _rows(rows.get("live_signal_events"))
        if query.start_ms <= int(row.get("observed_at_ms") or 0) <= query.end_ms
        and _matches_scope(row, query)
    ][: query.limit]
    counts = {
        key: len(_rows(value))
        for key, value in rows.items()
        if isinstance(value, list)
    }
    if not signals:
        covered = _window_covered(
            _rows(rows.get("watcher_runtime_coverage")),
            _rows(rows.get("server_monitor_runs")),
            _rows(rows.get("strategy_group_candidate_scope")),
            query,
        )
        return _result(
            query,
            conclusion_code=(
                "no_detected_signal_with_coverage" if covered else "runtime_data_gap"
            ),
            conclusion=(
                "该时间段观察链路完整，系统没有记录到符合策略条件的新信号。"
                if covered
                else "该时间段没有信号记录，但观察覆盖不足，不能断言市场没有机会。"
            ),
            market_absence_proven=covered,
            findings=(),
            row_counts=counts,
        )

    findings = tuple(_reduce_signal(signal, rows) for signal in signals)
    completed = sum(item.classification == "trade_completed" for item in findings)
    progressed = sum(item.ticket_id is not None for item in findings)
    conclusion_code = (
        "trade_completed"
        if completed
        else "trade_chain_progressed"
        if progressed
        else "signal_detected_not_traded"
    )
    conclusion = (
        f"共发现 {len(findings)} 个信号，其中 {completed} 个已完成交易。"
        if completed
        else f"共发现 {len(findings)} 个信号，最远推进到交易链路，但尚未形成已完成交易。"
        if progressed
        else f"共发现 {len(findings)} 个信号，但都在真实 Ticket 之前停止。"
    )
    return _result(
        query,
        conclusion_code=conclusion_code,
        conclusion=conclusion,
        market_absence_proven=False,
        findings=findings,
        row_counts=counts,
    )


def _reduce_signal(
    signal: Mapping[str, Any],
    rows: Mapping[str, Any],
) -> RuntimeSignalFinding:
    signal_id = str(signal.get("signal_event_id") or "")
    invocation = _first(
        rows.get("action_time_invocations"), "signal_event_id", signal_id
    )
    invocation_id = str(invocation.get("action_time_invocation_id") or "")
    promotion = _first(
        rows.get("promotion_candidates"), "signal_event_id", signal_id
    )
    promotion_id = str(promotion.get("promotion_candidate_id") or "")
    lane = _first_any(
        rows.get("action_time_lane_inputs"),
        (("signal_event_id", signal_id), ("promotion_candidate_id", promotion_id)),
    )
    lane_id = str(
        lane.get("lane_input_id")
        or lane.get("action_time_lane_input_id")
        or ""
    )
    ticket = _first_any(
        rows.get("action_time_tickets"),
        (("signal_event_id", signal_id), ("action_time_lane_input_id", lane_id)),
    )
    ticket_id = str(ticket.get("ticket_id") or "")
    command = _first(
        rows.get("ticket_bound_exchange_commands"), "ticket_id", ticket_id
    )
    attempt = _latest(
        rows.get("ticket_bound_protected_submit_attempts"), "ticket_id", ticket_id
    )
    lifecycle = _latest(
        rows.get("ticket_bound_order_lifecycle_runs"), "ticket_id", ticket_id
    )
    outcome = _first(rows.get("live_outcome_ledger"), "ticket_id", ticket_id)
    lineage = {
        "action_time_invocation_id": invocation_id or None,
        "promotion_candidate_id": promotion_id or None,
        "action_time_lane_input_id": lane_id or None,
        "ticket_id": ticket_id or None,
    }
    signal = {**signal, "__forensics_lineage__": lineage}
    notification_state = _notification_state(
        _rows(rows.get("server_monitor_notifications")), signal_id, ticket_id
    )

    if not promotion:
        if not invocation:
            return _finding(
                signal,
                "action_time_invocation",
                "engineering_handoff_gap",
                "action_time_invocation_missing",
                "信号已经记录，但没有建立对应的下单前调用上下文。",
                notification_state=notification_state,
            )
        invocation_outcomes = _invocation_process_outcomes(
            rows.get("runtime_process_outcomes"),
            invocation=invocation,
            signal=signal,
        )
        blocking_outcome = _earliest_blocking_process_outcome(invocation_outcomes)
        if blocking_outcome:
            lineage["process_name"] = _text_or_none(
                blocking_outcome.get("process_name")
            )
            lineage["process_state"] = _text_or_none(
                blocking_outcome.get("process_state")
            )
            process_state = str(blocking_outcome.get("process_state") or "")
            return _finding(
                signal,
                "runtime_process",
                _process_outcome_classification(process_state),
                _text_or_none(blocking_outcome.get("first_blocker"))
                or f"runtime_process_{process_state}",
                _process_outcome_explanation(process_state),
                notification_state=notification_state,
            )
        if not invocation_outcomes:
            return _finding(
                signal,
                "runtime_process",
                "engineering_handoff_gap",
                "runtime_process_outcome_missing",
                "下单前调用已经建立，但没有记录到对应的运行过程结果。",
                notification_state=notification_state,
            )
        return _finding(
            signal,
            "signal",
            "engineering_handoff_gap",
            "promotion_candidate_missing_after_successful_invocation",
            "下单前调用已经完成，但没有生成候选晋级记录。",
            notification_state=notification_state,
        )
    if not lane:
        promotion_status = str(promotion.get("status") or "")
        promotion_blockers = _string_list(promotion.get("blockers"))
        if promotion_status == "arbitration_lost":
            return _finding(
                signal,
                "promotion_candidate",
                "not_selected_by_arbitration",
                "arbitration_lost",
                "信号符合候选条件，但同一时刻有更高优先级机会被选中。",
                notification_state=notification_state,
            )
        if promotion_status == "blocked":
            blocker = promotion_blockers[0] if promotion_blockers else "promotion_blocked"
            return _finding(
                signal,
                "promotion_candidate",
                "runtime_safety_or_exchange_constraint",
                blocker,
                "信号已经进入候选判断，但资金、交易所约束或安全条件未通过。",
                notification_state=notification_state,
            )
        if promotion_status == "expired":
            return _finding(
                signal,
                "promotion_candidate",
                "opportunity_expired_before_action_time",
                "promotion_expired",
                "候选机会在进入下单前处理通道之前已经过期。",
                notification_state=notification_state,
            )
        return _finding(
            signal,
            "promotion_candidate",
            "engineering_handoff_gap",
            "action_time_lane_missing",
            "信号已经晋级，但没有进入唯一的下单前处理通道。",
            notification_state=notification_state,
        )
    if not ticket:
        return _finding(
            signal,
            "action_time_lane",
            "engineering_handoff_gap",
            "action_time_ticket_missing",
            "机会已进入下单前处理，但没有形成正式交易意图。",
            notification_state=notification_state,
        )
    if not command:
        ticket_status = str(ticket.get("status") or "")
        if ticket_status == "expired":
            return _finding(
                signal,
                "ticket",
                "opportunity_expired_before_submit",
                "ticket_expired_before_submit",
                "正式交易意图已经建立，但在提交真实订单前已经过期。",
                ticket_id=ticket_id,
                notification_state=notification_state,
            )
        if ticket_status == "finalgate_rejected":
            return _finding(
                signal,
                "ticket",
                "runtime_safety_or_reconciliation_gap",
                "finalgate_rejected",
                "正式交易意图没有通过最终交易安全检查。",
                ticket_id=ticket_id,
                notification_state=notification_state,
            )
        if ticket_status in {"invalidated", "superseded"}:
            return _finding(
                signal,
                "ticket",
                "opportunity_invalidated_before_submit",
                f"ticket_{ticket_status}",
                "正式交易意图在提交前被更新的市场或范围事实终止。",
                ticket_id=ticket_id,
                notification_state=notification_state,
            )
        if ticket_status in {"created", "preflight_pending", "finalgate_ready"}:
            return _finding(
                signal,
                "ticket",
                "trade_processing",
                "final_trade_check_pending",
                "正式交易意图已经建立，系统仍在完成下单前安全检查。",
                ticket_id=ticket_id,
                notification_state=notification_state,
            )
        return _finding(
            signal,
            "ticket",
            "engineering_handoff_gap",
            "exchange_command_missing",
            "正式交易意图已经建立，但没有记录到交易所命令。",
            ticket_id=ticket_id,
            notification_state=notification_state,
        )
    attempt_status = str(attempt.get("status") or "")
    if (
        attempt_status in {"submit_failed", "hard_stopped", "blocked"}
        and attempt.get("exchange_write_called") is not True
    ):
        attempt_blockers = _string_list(attempt.get("blockers"))
        blocker = (
            attempt_blockers[0]
            if attempt_blockers
            else f"protected_submit_{attempt_status}"
        )
        return _finding(
            signal,
            "operation_layer",
            "operation_blocked",
            blocker,
            "系统已经形成正式交易意图，但提交前被工程或安全条件阻断，没有调用交易所，也没有创建订单。",
            ticket_id=ticket_id,
            notification_state=notification_state,
        )
    command_state = str(command.get("command_state") or "")
    if command_state in {"outcome_unknown", "hard_stopped"}:
        return _finding(
            signal,
            "exchange_command",
            "runtime_safety_or_reconciliation_gap",
            command_state,
            "交易所命令已经发出，但结果需要安全核对。",
            ticket_id=ticket_id,
            notification_state=notification_state,
        )
    lifecycle_status = str(lifecycle.get("status") or "")
    if lifecycle_status == "lifecycle_closed":
        return _finding(
            signal,
            "closed",
            "trade_completed",
            None,
            "交易已经结束，结果和通知状态均可追溯。",
            ticket_id=ticket_id,
            notification_state=notification_state,
            net_pnl=_text_or_none(outcome.get("net_pnl")),
            r_multiple=_text_or_none(outcome.get("r_multiple")),
        )
    if lifecycle_status in {"position_protected", "runner_protected"}:
        return _finding(
            signal,
            lifecycle_status,
            "trade_active",
            None,
            "真实仓位已经建立并处于受保护状态。",
            ticket_id=ticket_id,
            notification_state=notification_state,
        )
    return _finding(
        signal,
        "exchange_command",
        "trade_processing",
        "lifecycle_confirmation_pending",
        "订单已进入交易所链路，正在等待成交和保护确认。",
        ticket_id=ticket_id,
        notification_state=notification_state,
    )


def _result(
    query: RuntimeSignalForensicsQuery,
    *,
    conclusion_code: str,
    conclusion: str,
    market_absence_proven: bool,
    findings: tuple[RuntimeSignalFinding, ...],
    row_counts: dict[str, int],
) -> RuntimeSignalForensicsResult:
    return RuntimeSignalForensicsResult(
        start_ms=query.start_ms,
        end_ms=query.end_ms,
        conclusion_code=conclusion_code,
        conclusion=conclusion,
        market_absence_proven=market_absence_proven,
        findings=findings,
        row_counts=row_counts,
        forbidden_effects={
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "mutates_policy": False,
            "writes_files": False,
        },
    )


def _finding(
    signal: Mapping[str, Any],
    chain_stage: str,
    classification: str,
    first_blocker: str | None,
    explanation: str,
    *,
    ticket_id: str | None = None,
    notification_state: str = "not_recorded",
    net_pnl: str | None = None,
    r_multiple: str | None = None,
) -> RuntimeSignalFinding:
    lineage = signal.get("__forensics_lineage__")
    lineage = lineage if isinstance(lineage, Mapping) else {}
    return RuntimeSignalFinding(
        signal_event_id=str(signal.get("signal_event_id") or ""),
        strategy_group_id=str(signal.get("strategy_group_id") or "unknown"),
        symbol=str(signal.get("symbol") or "unknown"),
        side=_text_or_none(signal.get("side")),
        observed_at_ms=int(signal.get("observed_at_ms") or 0),
        chain_stage=chain_stage,
        classification=classification,
        first_blocker=first_blocker,
        explanation=explanation,
        action_time_invocation_id=_text_or_none(
            lineage.get("action_time_invocation_id")
        ),
        promotion_candidate_id=_text_or_none(lineage.get("promotion_candidate_id")),
        action_time_lane_input_id=_text_or_none(
            lineage.get("action_time_lane_input_id")
        ),
        ticket_id=ticket_id or _text_or_none(lineage.get("ticket_id")),
        process_name=_text_or_none(lineage.get("process_name")),
        process_state=_text_or_none(lineage.get("process_state")),
        notification_state=notification_state,
        net_pnl=net_pnl,
        r_multiple=r_multiple,
    )


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _matches_scope(row: Mapping[str, Any], query: RuntimeSignalForensicsQuery) -> bool:
    return all(
        expected is None or str(row.get(field) or "") == expected
        for field, expected in (
            ("strategy_group_id", query.strategy_group_id),
            ("symbol", query.symbol),
            ("side", query.side),
        )
    )


def _window_covered(
    coverage_rows: list[dict[str, Any]],
    monitor_rows: list[dict[str, Any]],
    candidate_scope_rows: list[dict[str, Any]],
    query: RuntimeSignalForensicsQuery,
) -> bool:
    required_lanes = {
        _lane_key(row)
        for row in candidate_scope_rows
        if _scope_effective_in_window(row, query)
    }
    if not required_lanes:
        return False
    coverage_ok = all(
        _lane_window_is_healthy(
            [row for row in coverage_rows if _lane_key(row) == lane], query
        )
        for lane in required_lanes
    )
    monitor_times = sorted(
        int(row.get("finished_at_ms") or 0)
        for row in monitor_rows
        if str(row.get("status") or "") in {"quiet", "notify"}
    )
    if not coverage_ok or not monitor_times:
        return False
    max_gap_ms = 1_200_000
    boundary_ok = (
        monitor_times[0] <= query.start_ms + max_gap_ms
        and monitor_times[-1] >= query.end_ms - max_gap_ms
    )
    gaps_ok = all(
        later - earlier <= max_gap_ms
        for earlier, later in zip(monitor_times, monitor_times[1:])
    )
    return boundary_ok and gaps_ok


def _invocation_process_outcomes(
    value: Any,
    *,
    invocation: Mapping[str, Any],
    signal: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Bind process evidence to Invocation first, then exact lane identity."""

    rows = _rows(value)
    invocation_id = str(invocation.get("action_time_invocation_id") or "")
    direct = [
        row
        for row in rows
        if invocation_id
        and str(row.get("action_time_invocation_id") or "") == invocation_id
    ]
    if direct:
        return direct
    lane_identity_key = str(
        invocation.get("lane_identity_key") or signal.get("lane_identity_key") or ""
    )
    source_watermark = str(
        invocation.get("source_watermark") or signal.get("source_watermark") or ""
    )
    return [
        row
        for row in rows
        if lane_identity_key
        and str(row.get("lane_identity_key") or "") == lane_identity_key
        and (
            not source_watermark
            or str(row.get("source_watermark") or "") == source_watermark
        )
    ]


def _earliest_blocking_process_outcome(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    blocking = [
        row
        for row in rows
        if str(row.get("process_state") or "")
        in {"business_blocked", "retryable_failure", "hard_failure"}
    ]
    process_order = {
        "live_signal_materialization": 10,
        "action_time_fact_snapshots": 20,
        "promotion_action_time_lane": 30,
        "action_time_ticket_sequence": 40,
    }
    return min(
        blocking,
        key=lambda row: (
            process_order.get(str(row.get("process_name") or ""), 99),
            int(
                row.get("completed_at_ms")
                or row.get("updated_at_ms")
                or row.get("started_at_ms")
                or 0
            ),
        ),
        default={},
    )


def _process_outcome_classification(process_state: str) -> str:
    return {
        "business_blocked": "runtime_business_blocked",
        "retryable_failure": "engineering_runtime_failure",
        "hard_failure": "runtime_safety_or_identity_failure",
    }.get(process_state, "engineering_runtime_failure")


def _process_outcome_explanation(process_state: str) -> str:
    return {
        "business_blocked": "下单前运行过程被已记录的业务或安全条件阻断。",
        "retryable_failure": "下单前运行过程发生可重试的工程失败。",
        "hard_failure": "下单前运行过程触发了身份或安全硬失败。",
    }.get(process_state, "下单前运行过程未能完成，需要工程排查。")


def _lane_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("strategy_group_id") or ""),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def _scope_effective_in_window(
    row: Mapping[str, Any], query: RuntimeSignalForensicsQuery
) -> bool:
    if str(row.get("status") or "active") not in {"active", "enabled"}:
        return False
    starts_at_ms = int(
        row.get("effective_from_ms") or row.get("created_at_ms") or 0
    )
    ends_at_ms = int(
        row.get("closed_at_ms") or row.get("expires_at_ms") or 2**63 - 1
    )
    return starts_at_ms <= query.end_ms and ends_at_ms >= query.start_ms


def _lane_window_is_healthy(
    rows: list[dict[str, Any]], query: RuntimeSignalForensicsQuery
) -> bool:
    if not rows:
        return False
    intervals: list[tuple[int, int]] = []
    for row in rows:
        start = int(
            row.get("coverage_start_ms")
            or row.get("created_at_ms")
            or row.get("last_tick_at_ms")
            or 0
        )
        end = int(row.get("coverage_end_ms") or row.get("valid_until_ms") or 0)
        if end < query.start_ms or start > query.end_ms:
            continue
        if (
            str(row.get("coverage_state") or "") != "covered"
            or str(row.get("liveness_state") or "") not in {"healthy", "ok"}
        ):
            return False
        intervals.append((max(start, query.start_ms), min(end, query.end_ms)))
    if not intervals:
        return False
    cursor = query.start_ms
    for start, end in sorted(intervals):
        if start > cursor:
            return False
        cursor = max(cursor, end)
    return cursor >= query.end_ms


def _first(value: Any, key: str, expected: str) -> dict[str, Any]:
    if not expected:
        return {}
    return next((row for row in _rows(value) if str(row.get(key) or "") == expected), {})


def _first_any(value: Any, identities: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    return next(
        (
            row
            for row in _rows(value)
            if any(expected and str(row.get(key) or "") == expected for key, expected in identities)
        ),
        {},
    )


def _latest(value: Any, key: str, expected: str) -> dict[str, Any]:
    matches = [row for row in _rows(value) if expected and str(row.get(key) or "") == expected]
    return max(
        matches,
        key=lambda row: int(row.get("updated_at_ms") or row.get("created_at_ms") or 0),
        default={},
    )


def _notification_state(rows: list[dict[str, Any]], signal_id: str, ticket_id: str) -> str:
    correlations = {owner_correlation_id("signal", signal_id)}
    if ticket_id:
        correlations.add(owner_correlation_id("ticket", ticket_id))
    matches = [row for row in rows if str(row.get("correlation_id") or "") in correlations]
    if not matches:
        return "not_recorded"
    return str(max(matches, key=lambda row: int(row.get("updated_at_ms") or 0)).get("notification_state") or "unknown")


def _text_or_none(value: Any) -> str | None:
    return None if value is None or str(value) == "" else str(value)


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []
