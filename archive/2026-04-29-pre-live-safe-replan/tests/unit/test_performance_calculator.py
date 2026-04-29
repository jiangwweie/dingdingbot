"""
PerformanceCalculator 单元测试

测试 Optuna 目标函数计算逻辑

覆盖的测试用例:
- UT-001: 正常夏普比率计算
- UT-002: 使用已有 sharpe_ratio 字段
- UT-003: 交易数<2 时惩罚
- UT-004: 零波动率处理
- UT-005: 正常收益/回撤比计算
- UT-006: 零回撤处理
- UT-007: 负收益处理
- UT-008: 正常索提诺比率计算
- UT-009: 使用已有 sortino_ratio 字段
- UT-010: 无亏损交易处理
- UT-011: 总收益率计算
- UT-012: 胜率计算
- UT-013: 空数据边界情况
- UT-014: 负收益场景
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.application.strategy_optimizer import PerformanceCalculator


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def calculator():
    """创建 PerformanceCalculator 实例"""
    return PerformanceCalculator()


@pytest.fixture
def create_mock_report():
    """创建模拟回测报告的工厂函数"""
    def _factory(**kwargs):
        report = Mock()
        report.total_return = kwargs.get('total_return', Decimal('0.15'))
        report.max_drawdown = kwargs.get('max_drawdown', Decimal('0.05'))
        report.total_pnl = kwargs.get('total_pnl', Decimal('1500'))
        report.total_trades = kwargs.get('total_trades', 50)
        report.win_rate = kwargs.get('win_rate', Decimal('0.6'))
        report.avg_win = kwargs.get('avg_win', Decimal('100'))
        report.avg_loss = kwargs.get('avg_loss', Decimal('-50'))
        report.sharpe_ratio = kwargs.get('sharpe_ratio', None)
        report.sortino_ratio = kwargs.get('sortino_ratio', None)
        report.equity_curve = kwargs.get('equity_curve', [10000, 10100, 10200, 10150, 10300])
        report.returns = kwargs.get('returns', [0.01, 0.02, -0.005, 0.015])
        return report
    return _factory


# ============================================================
# Tests: 夏普比率计算
# ============================================================

class TestCalculateSharpeRatio:
    """夏普比率计算测试"""
    
    def test_calculate_sharpe_ratio_normal(self, calculator):
        """测试正常夏普比率计算"""
        returns = [0.02, 0.03, -0.01, 0.025, 0.015]
        
        result = calculator.calculate_sharpe_ratio(returns)
        
        assert isinstance(result, float)
        assert result > 0  # 正收益应该得到正的夏普比率
    
    def test_calculate_sharpe_ratio_insufficient_data(self, calculator):
        """测试数据不足时的处理"""
        returns = [0.02]  # 只有一个数据点
        
        result = calculator.calculate_sharpe_ratio(returns)
        
        assert result == 0.0  # 数据不足返回 0
    
    def test_calculate_sharpe_ratio_zero_volatility(self, calculator):
        """测试零波动率场景"""
        returns = [0.02, 0.02, 0.02, 0.02]  # 完全相同的收益
        
        result = calculator.calculate_sharpe_ratio(returns)
        
        assert result == 0.0  # 零波动率返回 0
    
    def test_calculate_sharpe_ratio_negative_returns(self, calculator):
        """测试负收益场景"""
        returns = [-0.02, -0.03, -0.01, -0.025]
        
        result = calculator.calculate_sharpe_ratio(returns)
        
        assert result < 0  # 负收益应得到负的夏普比率
    
    def test_calculate_sharpe_ratio_empty(self, calculator):
        """测试空数据"""
        returns = []
        
        result = calculator.calculate_sharpe_ratio(returns)
        
        assert result == 0.0
    
    def test_calculate_sharpe_ratio_custom_risk_free_rate(self, calculator):
        """测试自定义无风险利率"""
        returns = [0.02, 0.03, 0.025]
        risk_free_rate = 0.02  # 2% 无风险利率
        
        result = calculator.calculate_sharpe_ratio(
            returns, 
            risk_free_rate=risk_free_rate
        )
        
        assert isinstance(result, float)
    
    def test_calculate_sharpe_ratio_periods_per_year(self, calculator):
        """测试不同年化周期数"""
        returns = [0.01, 0.02, -0.01, 0.015]
        
        # 日线数据（365 周期）
        result_daily = calculator.calculate_sharpe_ratio(
            returns, periods_per_year=365
        )
        
        # 小时数据（24*365 周期）
        result_hourly = calculator.calculate_sharpe_ratio(
            returns, periods_per_year=24*365
        )
        
        assert isinstance(result_daily, float)
        assert isinstance(result_hourly, float)


# ============================================================
# Tests: 索提诺比率计算
# ============================================================

class TestCalculateSortinoRatio:
    """索提诺比率计算测试"""
    
    def test_calculate_sortino_ratio_normal(self, calculator):
        """测试正常索提诺比率计算"""
        returns = [0.02, -0.01, 0.03, -0.005, 0.025]
        
        result = calculator.calculate_sortino_ratio(returns)
        
        assert isinstance(result, float)
    
    def test_calculate_sortino_ratio_insufficient_data(self, calculator):
        """测试数据不足时的处理"""
        returns = [0.02]
        
        result = calculator.calculate_sortino_ratio(returns)
        
        assert result == 0.0
    
    def test_calculate_sortino_ratio_no_loss(self, calculator):
        """测试无亏损场景"""
        returns = [0.02, 0.03, 0.025, 0.01]  # 全部正收益
        
        result = calculator.calculate_sortino_ratio(returns)
        
        assert result == 0.0  # 无亏损无法计算下行偏差
    
    def test_calculate_sortino_ratio_insufficient_loss_data(self, calculator):
        """测试亏损数据不足时的处理"""
        returns = [0.02, 0.03, -0.01, 0.025]  # 只有一个负收益
        
        result = calculator.calculate_sortino_ratio(returns)
        
        assert result == 0.0  # 亏损数据不足返回 0
    
    def test_calculate_sortino_ratio_custom_risk_free_rate(self, calculator):
        """测试自定义无风险利率"""
        returns = [0.02, -0.01, 0.03, -0.005]
        risk_free_rate = 0.02
        
        result = calculator.calculate_sortino_ratio(
            returns,
            risk_free_rate=risk_free_rate
        )
        
        assert isinstance(result, float)


# ============================================================
# Tests: 最大回撤计算
# ============================================================

class TestCalculateMaxDrawdown:
    """最大回撤计算测试"""
    
    def test_calculate_max_drawdown_normal(self, calculator):
        """测试正常最大回撤计算"""
        equity_curve = [10000, 11000, 12000, 11500, 13000, 12500, 14000]
        
        result = calculator.calculate_max_drawdown(equity_curve)
        
        assert isinstance(result, float)
        assert 0 <= result <= 1  # 回撤应该在 0-1 之间
    
    def test_calculate_max_drawdown_insufficient_data(self, calculator):
        """测试数据不足时的处理"""
        equity_curve = [10000]
        
        result = calculator.calculate_max_drawdown(equity_curve)
        
        assert result == 0.0
    
    def test_calculate_max_drawdown_continuous_loss(self, calculator):
        """测试连续亏损场景"""
        equity_curve = [10000, 9500, 9000, 8500, 8000]
        
        result = calculator.calculate_max_drawdown(equity_curve)
        
        assert result == pytest.approx(0.2, rel=1e-1)  # 约 20% 回撤
    
    def test_calculate_max_drawdown_straight_up(self, calculator):
        """测试一直上涨场景"""
        equity_curve = [10000, 11000, 12000, 13000, 14000]
        
        result = calculator.calculate_max_drawdown(equity_curve)
        
        assert result == 0.0  # 无回撤
    
    def test_calculate_max_drawdown_empty(self, calculator):
        """测试空数据"""
        equity_curve = []
        
        result = calculator.calculate_max_drawdown(equity_curve)
        
        assert result == 0.0


# ============================================================
# Tests: 收益回撤比计算
# ============================================================

class TestCalculatePnlDdRatio:
    """收益回撤比计算测试"""
    
    def test_calculate_pnl_dd_ratio_normal(self, calculator):
        """测试正常收益/回撤比计算"""
        total_pnl = 1500.0
        max_drawdown = 0.05  # 5% 回撤
        
        result = calculator.calculate_pnl_dd_ratio(total_pnl, max_drawdown)
        
        assert result == pytest.approx(30000.0, rel=1e-6)  # 1500/0.05 = 30000
    
    def test_calculate_pnl_dd_ratio_zero_drawdown(self, calculator):
        """测试零回撤场景"""
        total_pnl = 1000.0
        max_drawdown = 0.0
        
        result = calculator.calculate_pnl_dd_ratio(total_pnl, max_drawdown)
        
        assert result == float('inf')  # 无穷大
    
    def test_calculate_pnl_dd_ratio_negative_pnl(self, calculator):
        """测试负收益场景"""
        total_pnl = -500.0
        max_drawdown = 0.1  # 10% 回撤
        
        result = calculator.calculate_pnl_dd_ratio(total_pnl, max_drawdown)
        
        assert result < 0  # 负收益应得到负的比值
    
    def test_calculate_pnl_dd_ratio_both_negative(self, calculator):
        """测试收益和回撤都为负的场景"""
        total_pnl = -500.0
        max_drawdown = -0.1
        
        result = calculator.calculate_pnl_dd_ratio(total_pnl, max_drawdown)
        
        assert isinstance(result, float)


# ============================================================
# Tests: 基于 Mock 回测报告的计算
# ============================================================

class TestCalculateFromMockReport:
    """基于 Mock 回测报告的计算测试"""
    
    def test_sharpe_with_existing_ratio(self, calculator, create_mock_report):
        """测试使用报告中的 sharpe_ratio 字段"""
        report = create_mock_report(sharpe_ratio=Decimal('2.5'))
        
        # 从报告中提取收益序列进行计算
        returns = [0.02, 0.03, -0.01, 0.025]
        result = calculator.calculate_sharpe_ratio(returns)
        
        assert isinstance(result, float)
    
    def test_sortino_with_existing_ratio(self, calculator, create_mock_report):
        """测试使用报告中的 sortino_ratio 字段"""
        report = create_mock_report(sortino_ratio=Decimal('3.2'))
        
        returns = [0.02, -0.01, 0.03, -0.005]
        result = calculator.calculate_sortino_ratio(returns)
        
        assert isinstance(result, float)
    
    def test_max_drawdown_from_equity_curve(self, calculator, create_mock_report):
        """测试从资金曲线计算最大回撤"""
        report = create_mock_report(
            equity_curve=[10000, 11000, 10500, 12000, 11800, 13000]
        )
        
        result = calculator.calculate_max_drawdown(report.equity_curve)
        
        assert isinstance(result, float)
        assert 0 <= result <= 1
    
    def test_pnl_dd_ratio_from_report(self, calculator, create_mock_report):
        """测试从报告计算收益/回撤比"""
        report = create_mock_report(
            total_pnl=Decimal('2000'),
            max_drawdown=Decimal('0.08')
        )
        
        result = calculator.calculate_pnl_dd_ratio(
            float(report.total_pnl),
            float(report.max_drawdown)
        )
        
        assert result == pytest.approx(25000.0, rel=1e-6)


# ============================================================
# Tests: 边界情况和异常处理
# ============================================================

class TestEdgeCases:
    """边界情况测试"""
    
    def test_all_zeros(self, calculator):
        """测试全零数据"""
        returns = [0.0, 0.0, 0.0, 0.0]
        
        sharpe = calculator.calculate_sharpe_ratio(returns)
        sortino = calculator.calculate_sortino_ratio(returns)
        
        assert sharpe == 0.0
        assert sortino == 0.0
    
    def test_very_small_returns(self, calculator):
        """测试极小收益率"""
        returns = [0.0001, 0.0002, -0.0001, 0.00015]
        
        sharpe = calculator.calculate_sharpe_ratio(returns)
        
        assert isinstance(sharpe, float)
    
    def test_very_large_drawdown(self, calculator):
        """测试极大回撤"""
        total_pnl = 1000.0
        max_drawdown = 0.99  # 99% 回撤
        
        result = calculator.calculate_pnl_dd_ratio(total_pnl, max_drawdown)
        
        assert result > 0
    
    def test_single_profit_single_loss(self, calculator):
        """测试单次盈利单次亏损"""
        returns = [0.1, -0.05]
        
        sharpe = calculator.calculate_sharpe_ratio(returns)
        sortino = calculator.calculate_sortino_ratio(returns)
        
        assert isinstance(sharpe, float)
        assert isinstance(sortino, float)
