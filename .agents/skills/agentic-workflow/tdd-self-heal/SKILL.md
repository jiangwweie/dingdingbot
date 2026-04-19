# TDD 闭环自愈技能 (Test-Driven Self-Correction)

> **技能类型**: 自动开发 + 自我修复
> **适用场景**: 状态机逻辑、边界条件复杂的量化功能
> **预期收益**: 阻挡 90% 低级逻辑漏洞

---

## 技能描述

本技能赋予 AI 完整的 TDD 闭环能力：
1. 解析契约文档中的测试用例清单
2. 生成 pytest 测试代码
3. 执行测试并分析失败
4. 自我修复业务代码
5. 直到所有测试通过才提交

---

## 权限要求

```json
{
  "permissions": {
    "allow": [
      "Bash(pytest:*)",
      "Bash(python3 -c:*)",
      "Read(//Users/jiangwei/Documents/final/tests/**)",
      "Read(//Users/jiangwei/Documents/final/src/**)",
      "Write(//Users/jiangwei/Documents/final/tests/**)",
      "Write(//Users/jiangwei/Documents/final/src/**)"
    ]
  }
}
```

---

## 工作流详解

### 阶段 0: 接收任务

**用户输入示例**:
```
实现 DynamicRiskManager 的移动止损功能
契约文档：docs/v3/phase3-risk-state-machine-contract.md
测试用例：UT-005 ~ UT-008
```

### 阶段 1: 契约解析

**AI 执行**:
1. 读取契约文档
2. 提取测试用例清单
3. 理解每个用例的 Given/When/Then

**契约表示例**:
| 用例 ID | 测试场景 | 前置条件 | 触发条件 | 预期结果 | 优先级 |
|---------|----------|----------|----------|----------|--------|
| UT-005 | 移动止损触发 | 持仓盈利>1% | 价格回撤 0.5% | 平仓，exit_reason=TRAILING_STOP | 高 |
| UT-006 | 移动止损未触发 | 持仓盈利<1% | 价格小幅波动 | 持仓保持 | 中 |

### 阶段 2: 生成测试代码

**AI 输出**:
```python
# tests/unit/test_risk_manager_trailing_stop.py

import pytest
from decimal import Decimal
from src.domain.risk_manager import DynamicRiskManager
from src.domain.models import Position, PositionStatus

class TestTrailingStopLogic:
    """移动止损测试 - 基于契约 UT-005 ~ UT-008"""
    
    @pytest.mark.asyncio
    async def test_ut_005_trailing_stop_triggers_after_1pct_profit(self):
        """UT-005: 盈利超 1% 后价格回撤触发移动止损"""
        # Given: 持有多头仓位，入场价 50000，当前价 50600 (>1% 盈利)
        position = Position(
            symbol="BTC/USDT:USDT",
            side="LONG",
            entry_price=Decimal("50000"),
            quantity=Decimal("0.1"),
            status=PositionStatus.OPEN,
            highest_price=Decimal("50600"),  # 最高价记录
            trailing_stop_price=Decimal("50300"),  # 移动止损价
        )
        
        # When: 价格回撤至 50299 (低于移动止损价)
        risk_manager = DynamicRiskManager()
        await risk_manager.check_trailing_stop(position, Decimal("50299"))
        
        # Then: 仓位关闭，exit_reason=TRAILING_STOP
        assert position.status == PositionStatus.CLOSED
        assert position.exit_reason == "TRAILING_STOP"
        assert position.exit_price == Decimal("50299")
    
    @pytest.mark.asyncio
    async def test_ut_006_trailing_stop_not_triggered_below_1pct(self):
        """UT-006: 盈利不足 1% 时不触发移动止损"""
        # Given: 持仓盈利<1%
        position = Position(
            symbol="BTC/USDT:USDT",
            side="LONG",
            entry_price=Decimal("50000"),
            quantity=Decimal("0.1"),
            status=PositionStatus.OPEN,
            highest_price=Decimal("50400"),  # 盈利<1%
            trailing_stop_price=None,  # 未激活
        )
        
        # When: 价格小幅下跌
        risk_manager = DynamicRiskManager()
        await risk_manager.check_trailing_stop(position, Decimal("50350"))
        
        # Then: 持仓保持开放
        assert position.status == PositionStatus.OPEN
        assert position.exit_reason is None
```

### 阶段 3: 运行测试 (Red)

**AI 执行**:
```bash
cd /Users/jiangwei/Documents/final
source venv/bin/activate
pytest tests/unit/test_risk_manager_trailing_stop.py -v
```

**预期输出** (失败):
```
FAILED test_risk_manager_trailing_stop.py::TestTrailingStopLogic::test_ut_005_trailing_stop_triggers_after_1pct_profit
AssertionError: assert PositionStatus.OPEN == PositionStatus.CLOSED
```

### 阶段 4: 实现业务代码 (Green)

**AI 分析失败原因并实现**:
```python
# src/domain/risk_manager.py

from decimal import Decimal
from src.domain.models import Position, PositionStatus

class DynamicRiskManager:
    """动态风控管理器"""
    
    TRAILING_STOP_THRESHOLD = Decimal("0.01")  # 1% 盈利阈值
    TRAILING_STOP_DISTANCE = Decimal("0.005")  # 0.5% 回撤距离
    
    async def check_trailing_stop(
        self, 
        position: Position, 
        current_price: Decimal
    ) -> bool:
        """检查是否触发移动止损"""
        
        # 1. 检查是否满足移动止损激活条件
        if not self._is_trailing_stop_active(position):
            return False
        
        # 2. 检查是否触发止损
        if position.side == "LONG":
            if current_price <= position.trailing_stop_price:
                await self._close_position(
                    position, 
                    current_price, 
                    "TRAILING_STOP"
                )
                return True
        else:  # SHORT
            if current_price >= position.trailing_stop_price:
                await self._close_position(
                    position,
                    current_price,
                    "TRAILING_STOP"
                )
                return True
        
        return False
    
    def _is_trailing_stop_active(self, position: Position) -> bool:
        """检查移动止损是否已激活"""
        if position.highest_price is None:
            return False
        
        # 计算未实现盈亏比率
        if position.side == "LONG":
            profit_ratio = (
                position.highest_price - position.entry_price
            ) / position.entry_price
        else:
            profit_ratio = (
                position.entry_price - position.highest_price
            ) / position.entry_price
        
        return profit_ratio >= self.TRAILING_STOP_THRESHOLD
    
    async def _close_position(
        self,
        position: Position,
        exit_price: Decimal,
        reason: str
    ):
        """平仓辅助方法"""
        position.status = PositionStatus.CLOSED
        position.exit_price = exit_price
        position.exit_reason = reason
        position.closed_at = datetime.now(timezone.utc)
```

### 阶段 5: 自愈合循环

**AI 执行**:
```bash
pytest tests/unit/test_risk_manager_trailing_stop.py -v
```

**如果通过** ✅ → 进入重构阶段
**如果失败** ❌ → 分析 Traceback，返回阶段 4

**失败分析示例**:
```
分析：测试失败是因为 trailing_stop_price 未在盈利时更新

根本原因：缺少更新移动止损价的逻辑

修复方案：
1. 添加 update_trailing_stop_price() 方法
2. 在每次价格更新时调用
3. 重新运行测试
```

### 阶段 6: 重构与提交

**AI 执行**:
```bash
# 类型检查
mypy src/domain/risk_manager.py

# 格式化
black src/domain/risk_manager.py

# 提交
git add src/domain/risk_manager.py tests/unit/test_risk_manager_trailing_stop.py
git commit -m "feat(domain): 实现移动止损逻辑 (UT-005 ~ UT-008)

- 添加 DynamicRiskManager.check_trailing_stop() 方法
- 盈利超 1% 后激活移动止损
- 回撤 0.5% 触发平仓
- 100% 测试覆盖

Co-Authored-By: Codex Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 技能触发条件

当用户指令包含以下关键词时激活此技能：

| 关键词 | 触发行为 |
|--------|----------|
| "实现 X 功能，契约是..." | 解析契约 → 生成测试 → 实现代码 |
| "为 X 编写测试，遵循..." | 生成测试 → 运行 → 修复 |
| "修复这个 Bug，测试用例是..." | 生成回归测试 → 修复 → 验证 |
| "/tdd [功能描述]" | 完整 TDD 流程 |

---

## 输出格式

**技能执行中的状态更新**:
```
🔴 Red: 测试已生成，等待运行
  └─ 已创建 4 个测试用例
  └─ 运行 pytest...

🟢 Green: 测试通过
  └─ 4 passed in 0.52s
  └─ 正在格式化代码...

🔵 Refactor: 重构完成
  └─ mypy 检查通过
  └─ 已提交 git: abc123
```

**最终汇报**:
```markdown
## TDD 闭环完成

### 实现功能
DynamicRiskManager 移动止损逻辑

### 测试覆盖
- ✅ UT-005: 盈利超 1% 后触发移动止损
- ✅ UT-006: 盈利不足 1% 时不触发
- ✅ UT-007: 空头仓位移动止损
- ✅ UT-008: 移动止损价格更新

### 代码变更
- `src/domain/risk_manager.py` (+45 行)
- `tests/unit/test_risk_manager_trailing_stop.py` (+89 行)

### 提交
- abc1234 feat(domain): 实现移动止损逻辑
```

---

## 与规划文件的集成

执行此技能时，自动更新规划文档：

```bash
# 更新 task_plan.md
- 标记当前阶段为 completed
- 更新下一阶段的 blockedBy 状态

# 更新 progress.md  
- 记录本次 TDD 循环的迭代次数
- 记录遇到的典型错误模式
```

---

*技能版本：v1.0*
*创建日期：2026-04-01*
