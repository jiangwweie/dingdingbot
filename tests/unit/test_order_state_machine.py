"""
Order State Machine 单元测试

测试覆盖:
1. 8 种状态定义
2. 合法流转矩阵
3. can_transition() 方法
4. get_valid_transitions() 方法
5. is_terminal_state() 方法
6. InvalidOrderStateTransition 异常
"""

import pytest
from src.domain.order_state_machine import OrderStateMachine
from src.domain.exceptions import InvalidOrderStateTransition


class TestOrderStateMachineStates:
    """测试状态定义"""

    def test_states_count(self):
        """测试状态数量为 9 种"""
        assert len(OrderStateMachine.STATES) == 9

    def test_all_states_defined(self):
        """测试所有状态已定义"""
        expected_states = {
            "CREATED",
            "SUBMITTED",
            "PENDING",
            "OPEN",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELED",
            "REJECTED",
            "EXPIRED",
        }
        assert OrderStateMachine.STATES == expected_states

    def test_terminal_states_defined(self):
        """测试终态定义"""
        expected_terminal = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
        assert OrderStateMachine.TERMINAL_STATES == expected_terminal


class TestOrderStateMachineTransitions:
    """测试状态流转"""

    def test_created_transitions(self):
        """测试 CREATED 状态的合法流转"""
        valid = OrderStateMachine.get_valid_transitions_from("CREATED")
        assert valid == {"SUBMITTED", "CANCELED"}

    def test_submitted_transitions(self):
        """测试 SUBMITTED 状态的合法流转"""
        valid = OrderStateMachine.get_valid_transitions_from("SUBMITTED")
        assert valid == {"OPEN", "REJECTED", "CANCELED", "EXPIRED"}

    def test_pending_transitions(self):
        """测试 PENDING 状态的合法流转"""
        valid = OrderStateMachine.get_valid_transitions_from("PENDING")
        assert valid == {"OPEN", "REJECTED", "CANCELED", "SUBMITTED"}

    def test_open_transitions(self):
        """测试 OPEN 状态的合法流转"""
        valid = OrderStateMachine.get_valid_transitions_from("OPEN")
        assert valid == {"PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"}

    def test_partially_filled_transitions(self):
        """测试 PARTIALLY_FILLED 状态的合法流转"""
        valid = OrderStateMachine.get_valid_transitions_from("PARTIALLY_FILLED")
        assert valid == {"FILLED", "CANCELED"}

    def test_filled_transitions(self):
        """测试 FILLED 状态的合法流转 (终态)"""
        valid = OrderStateMachine.get_valid_transitions_from("FILLED")
        assert valid == set()

    def test_canceled_transitions(self):
        """测试 CANCELED 状态的合法流转 (终态)"""
        valid = OrderStateMachine.get_valid_transitions_from("CANCELED")
        assert valid == set()

    def test_rejected_transitions(self):
        """测试 REJECTED 状态的合法流转 (终态)"""
        valid = OrderStateMachine.get_valid_transitions_from("REJECTED")
        assert valid == set()

    def test_expired_transitions(self):
        """测试 EXPIRED 状态的合法流转 (终态)"""
        valid = OrderStateMachine.get_valid_transitions_from("EXPIRED")
        assert valid == set()


class TestCanTransition:
    """测试 can_transition() 方法"""

    # CREATED 状态的流转测试
    def test_created_to_submitted(self):
        assert OrderStateMachine.can_transition("CREATED", "SUBMITTED") is True

    def test_created_to_canceled(self):
        assert OrderStateMachine.can_transition("CREATED", "CANCELED") is True

    def test_created_to_open(self):
        assert OrderStateMachine.can_transition("CREATED", "OPEN") is False

    # SUBMITTED 状态的流转测试
    def test_submitted_to_open(self):
        assert OrderStateMachine.can_transition("SUBMITTED", "OPEN") is True

    def test_submitted_to_rejected(self):
        assert OrderStateMachine.can_transition("SUBMITTED", "REJECTED") is True

    def test_submitted_to_canceled(self):
        assert OrderStateMachine.can_transition("SUBMITTED", "CANCELED") is True

    def test_submitted_to_expired(self):
        assert OrderStateMachine.can_transition("SUBMITTED", "EXPIRED") is True

    def test_submitted_to_filled(self):
        assert OrderStateMachine.can_transition("SUBMITTED", "FILLED") is False

    # PENDING 状态的流转测试
    def test_pending_to_open(self):
        assert OrderStateMachine.can_transition("PENDING", "OPEN") is True

    def test_pending_to_rejected(self):
        assert OrderStateMachine.can_transition("PENDING", "REJECTED") is True

    def test_pending_to_canceled(self):
        assert OrderStateMachine.can_transition("PENDING", "CANCELED") is True

    def test_pending_to_submitted(self):
        assert OrderStateMachine.can_transition("PENDING", "SUBMITTED") is True

    def test_pending_to_filled(self):
        assert OrderStateMachine.can_transition("PENDING", "FILLED") is False

    def test_pending_to_partially_filled(self):
        assert OrderStateMachine.can_transition("PENDING", "PARTIALLY_FILLED") is False

    # OPEN 状态的流转测试
    def test_open_to_partially_filled(self):
        assert OrderStateMachine.can_transition("OPEN", "PARTIALLY_FILLED") is True

    def test_open_to_filled(self):
        assert OrderStateMachine.can_transition("OPEN", "FILLED") is True

    def test_open_to_canceled(self):
        assert OrderStateMachine.can_transition("OPEN", "CANCELED") is True

    def test_open_to_rejected(self):
        assert OrderStateMachine.can_transition("OPEN", "REJECTED") is True

    def test_open_to_pending(self):
        assert OrderStateMachine.can_transition("OPEN", "PENDING") is False

    # PARTIALLY_FILLED 状态的流转测试
    def test_partially_filled_to_filled(self):
        assert OrderStateMachine.can_transition("PARTIALLY_FILLED", "FILLED") is True

    def test_partially_filled_to_canceled(self):
        assert OrderStateMachine.can_transition("PARTIALLY_FILLED", "CANCELED") is True

    def test_partially_filled_to_open(self):
        assert OrderStateMachine.can_transition("PARTIALLY_FILLED", "OPEN") is False

    # 终态流转测试
    def test_filled_to_any(self):
        """测试 FILLED 终态不可流转"""
        for status in OrderStateMachine.STATES:
            assert OrderStateMachine.can_transition("FILLED", status) is False

    def test_canceled_to_any(self):
        """测试 CANCELED 终态不可流转"""
        for status in OrderStateMachine.STATES:
            assert OrderStateMachine.can_transition("CANCELED", status) is False

    def test_rejected_to_any(self):
        """测试 REJECTED 终态不可流转"""
        for status in OrderStateMachine.STATES:
            assert OrderStateMachine.can_transition("REJECTED", status) is False

    def test_expired_to_any(self):
        """测试 EXPIRED 终态不可流转"""
        for status in OrderStateMachine.STATES:
            assert OrderStateMachine.can_transition("EXPIRED", status) is False

    # 非法状态测试
    def test_invalid_from_status(self):
        """测试非法的源状态"""
        assert OrderStateMachine.can_transition("INVALID", "OPEN") is False

    def test_invalid_to_status(self):
        """测试非法的目标状态"""
        assert OrderStateMachine.can_transition("PENDING", "INVALID") is False


class TestCanTransitionWithException:
    """测试 can_transition_with_exception() 方法"""

    def test_valid_transition_no_exception(self):
        """测试合法流转不抛异常"""
        result = OrderStateMachine.can_transition_with_exception(
            "ord_123", "PENDING", "OPEN"
        )
        assert result is True

    def test_invalid_transition_raises_exception(self):
        """测试非法流转抛出异常"""
        with pytest.raises(InvalidOrderStateTransition) as exc_info:
            OrderStateMachine.can_transition_with_exception(
                "ord_123", "FILLED", "OPEN"
            )

        assert "ord_123" in str(exc_info.value)
        assert "FILLED" in str(exc_info.value)
        assert "OPEN" in str(exc_info.value)

    def test_exception_contains_valid_transitions(self):
        """测试异常包含合法的流转选项"""
        with pytest.raises(InvalidOrderStateTransition) as exc_info:
            OrderStateMachine.can_transition_with_exception(
                "ord_456", "PENDING", "FILLED"
            )

        exc = exc_info.value
        assert exc.order_id == "ord_456"
        assert exc.from_status == "PENDING"
        assert exc.to_status == "FILLED"
        assert "OPEN" in exc.valid_transitions
        assert "REJECTED" in exc.valid_transitions
        assert "CANCELED" in exc.valid_transitions


class TestIsTerminalState:
    """测试 is_terminal_state() 方法"""

    def test_terminal_states(self):
        """测试终态判定"""
        assert OrderStateMachine.is_terminal_state("FILLED") is True
        assert OrderStateMachine.is_terminal_state("CANCELED") is True
        assert OrderStateMachine.is_terminal_state("REJECTED") is True
        assert OrderStateMachine.is_terminal_state("EXPIRED") is True

    def test_non_terminal_states(self):
        """测试非终态判定"""
        assert OrderStateMachine.is_terminal_state("PENDING") is False
        assert OrderStateMachine.is_terminal_state("OPEN") is False
        assert OrderStateMachine.is_terminal_state("PARTIALLY_FILLED") is False

    def test_invalid_state(self):
        """测试非法状态"""
        assert OrderStateMachine.is_terminal_state("INVALID") is False


class TestHelperMethods:
    """测试辅助方法"""

    def test_is_valid_state(self):
        """测试状态有效性检查"""
        for state in OrderStateMachine.STATES:
            assert OrderStateMachine.is_valid_state(state) is True

        assert OrderStateMachine.is_valid_state("INVALID") is False
        assert OrderStateMachine.is_valid_state("") is False
        assert OrderStateMachine.is_valid_state(None) is False

    def test_get_all_states(self):
        """测试获取所有状态"""
        all_states = OrderStateMachine.get_all_states()
        assert len(all_states) == 9
        assert all_states == OrderStateMachine.STATES

    def test_get_terminal_states(self):
        """测试获取所有终态"""
        terminal_states = OrderStateMachine.get_terminal_states()
        assert len(terminal_states) == 4
        assert terminal_states == {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}

    def test_get_non_terminal_states(self):
        """测试获取所有非终态"""
        non_terminal = OrderStateMachine.get_non_terminal_states()
        assert len(non_terminal) == 5
        assert non_terminal == {"CREATED", "SUBMITTED", "PENDING", "OPEN", "PARTIALLY_FILLED"}

    def test_describe_transition_valid(self):
        """测试流转描述 - 合法流转"""
        desc = OrderStateMachine.describe_transition("PENDING", "OPEN")
        assert "PENDING" in desc
        assert "OPEN" in desc
        assert "Order sent to exchange" in desc

    def test_describe_transition_invalid(self):
        """测试流转描述 - 非法流转"""
        desc = OrderStateMachine.describe_transition("FILLED", "OPEN")
        assert "Invalid transition" in desc


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_string_state(self):
        """测试空字符串状态"""
        assert OrderStateMachine.can_transition("", "OPEN") is False
        assert OrderStateMachine.can_transition("PENDING", "") is False
        assert OrderStateMachine.is_terminal_state("") is False

    def test_none_state(self):
        """测试 None 状态"""
        assert OrderStateMachine.can_transition(None, "OPEN") is False
        assert OrderStateMachine.can_transition("PENDING", None) is False
        assert OrderStateMachine.is_terminal_state(None) is False

    def test_case_sensitivity(self):
        """测试大小写敏感"""
        assert OrderStateMachine.can_transition("pending", "OPEN") is False
        assert OrderStateMachine.can_transition("PENDING", "open") is False
        assert OrderStateMachine.is_terminal_state("filled") is False

    def test_whitespace_state(self):
        """测试带空格的状态"""
        assert OrderStateMachine.can_transition(" PENDING", "OPEN") is False
        assert OrderStateMachine.can_transition("PENDING ", "OPEN") is False


class TestCompleteTransitionPaths:
    """测试完整的流转路径"""

    def test_successful_order_path(self):
        """测试成功订单的完整路径"""
        path = ["PENDING", "OPEN", "FILLED"]
        for i in range(len(path) - 1):
            assert OrderStateMachine.can_transition(path[i], path[i + 1]) is True

    def test_canceled_order_path(self):
        """测试被撤销订单的路径"""
        path = ["PENDING", "OPEN", "CANCELED"]
        for i in range(len(path) - 1):
            assert OrderStateMachine.can_transition(path[i], path[i + 1]) is True

    def test_rejected_order_path(self):
        """测试被拒绝订单的路径"""
        path = ["PENDING", "REJECTED"]
        assert OrderStateMachine.can_transition(path[0], path[1]) is True

    def test_partial_fill_then_filled_path(self):
        """测试部分成交后完全成交的路径"""
        path = ["PENDING", "OPEN", "PARTIALLY_FILLED", "FILLED"]
        for i in range(len(path) - 1):
            assert OrderStateMachine.can_transition(path[i], path[i + 1]) is True

    def test_partial_fill_then_canceled_path(self):
        """测试部分成交后撤销的路径"""
        path = ["PENDING", "OPEN", "PARTIALLY_FILLED", "CANCELED"]
        for i in range(len(path) - 1):
            assert OrderStateMachine.can_transition(path[i], path[i + 1]) is True

    def test_expired_order_path(self):
        """测试过期订单的路径"""
        # EXPIRED 通常由交易所返回，不是主动流转
        assert OrderStateMachine.is_terminal_state("EXPIRED") is True
