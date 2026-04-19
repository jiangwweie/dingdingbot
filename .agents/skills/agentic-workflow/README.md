# Agentic Workflow - 高阶技能设计

> **创建日期**: 2026-04-01
> **适用场景**: v3.0 量化交易系统开发
> **核心理念**: 多 Agent 协作 + 自动质量保障

---

## 背景与动机

在多 Agent 协作开发复杂量化系统时，普通"写代码"Agent 常因以下问题埋下隐患：

1. **上下文丢失** - 设计文档与代码不同步
2. **测试滞后** - 先写代码后补测试，遗漏边界条件
3. **类型漂移** - float 污染 Decimal 金融计算
4. **并发漏洞** - 死锁风险、事件循环阻塞
5. **未来函数** - 回测偷看未来数据

---

## 5 个核心技能设计

### 1. 契约双向同步 (Contract-to-Code Sync) 📋

**问题**: 代码改了，设计文档没更新，导致后续 Agent 产生幻觉

**工作流**:

```
┌─────────────────────────────────────────────────────────────┐
│                    正向约束 (开发时)                         │
├─────────────────────────────────────────────────────────────┤
│ 1. 读取契约文档 (e.g., phase4-order-orchestration-contract.md) │
│ 2. 提取接口签名、状态转移图、OCO 逻辑限制                      │
│ 3. 生成 Pydantic 模型骨架                                     │
│ 4. 强制遵循契约实现业务逻辑                                   │
│ 5. 验证：实现是否覆盖契约所有要求                              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    逆向同步 (修复时) ⭐核心亮点                │
├─────────────────────────────────────────────────────────────┤
│ 1. 检测代码变更 (e.g., DynamicRiskManager 入参修改)           │
│ 2. AST 扫描定位相关函数签名、类属性                           │
│ 3. 自动更新契约文档中的表格和状态转移图                        │
│ 4. 提交时附带文档变更 diff                                    │
│ 5. 确保 Markdown 与代码 SSOT 绝对一致                          │
└─────────────────────────────────────────────────────────────┘
```

**实现路径**:
```python
# 逆向同步伪代码
def sync_contract_from_code(code_change: CodeDiff) -> ContractUpdate:
    # 1. AST 解析变更代码
    tree = ast.parse(code_change.new_code)
    
    # 2. 定位函数/类签名变更
    changed_signatures = extract_signatures(tree)
    
    # 3. 读取契约文档
    contract = parse_markdown_table("phase3-risk-state-machine-contract.md")
    
    # 4. 比对并生成更新建议
    updates = []
    for sig in changed_signatures:
        if sig.name in contract.functions:
            old = contract.functions[sig.name]
            if old.params != sig.params:
                updates.append(ContractUpdate(
                    section="接口签名",
                    old=old.params,
                    new=sig.params
                ))
    
    # 5. 自动生成 PR 描述
    return generate_pr_description(updates)
```

**触发条件**:
- 修改 `domain/` 或 `application/` 层核心类
- 变更 Pydantic 模型字段
- 调整状态机流转逻辑

---

### 2. TDD 闭环自愈 (Test-Driven Self-Correction) 🧪

**问题**: 状态机边界条件复杂，人工测试易遗漏

**工作流**:

```
┌─────────────────────────────────────────────────────────────┐
│                    TDD 自愈合循环                              │
│                                                             │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐              │
│   │ 契约表  │ ──→ │ 生成测试│ ──→ │ 运行 pytest│              │
│   │ UT-XXX  │     │ 用例    │     │         │              │
│   └─────────┘     └─────────┘     └────┬────┘              │
│      ↑                                 │                    │
│      │         ┌─────────────────┐    │                    │
│      │         │   测试失败？     │ ←──┘                    │
│      │         └────────┬────────┘                         │
│      │                  │                                  │
│      │           Yes    │    No                           │
│      │                  ↓                                  │
│      │         ┌─────────────────┐                         │
│      │         │ 截获 Traceback   │                         │
│      │         │ 分析失败原因     │                         │
│      │         │ 自我修复代码     │                         │
│      │         └────────┬────────┘                         │
│      │                  │                                  │
│      └──────────────────┴──────────→ ✅ 绿灯提交            │
└─────────────────────────────────────────────────────────────┘
```

**实现配置** (`~/.claude/skills/tdd-self-heal/SKILL.md`):

```markdown
# TDD 闭环自愈技能

## 权限要求
- 执行 `pytest tests/ -v`
- 读取 `tests/**/*.py` 和 `src/**/*.py`
- 修改 `src/` 业务代码

## 工作流程

### 阶段 1: 契约解析
1. 读取任务契约表 (e.g., `docs/v3/phase3-risk-state-machine-contract.md`)
2. 提取测试用例清单 (UT-001 ~ UT-012)
3. 为每个用例生成 pytest 测试函数骨架

### 阶段 2: 测试先行
1. 编写失败测试 (Red)
2. 运行测试确认失败
3. 截取失败输出

### 阶段 3: 实现与自愈
1. 编写最小实现使测试通过 (Green)
2. 运行完整测试套件
3. 如果失败:
   - 解析 Traceback 定位问题
   - 分析是测试错误还是实现错误
   - 自动修复并重试
4. 最多重试 3 次，仍失败则向用户汇报

### 阶段 4: 重构
1. 运行 mypy 类型检查
2. 运行 black 格式化
3. 提交代码
```

**测试用例模板**:
```python
# tests/unit/test_risk_state_machine.py

class TestRiskStateMachine:
    """风控状态机测试 - 基于契约 UT-001 ~ UT-012"""
    
    @pytest.mark.asyncio
    async def test_ut_001_initial_stop_loss_triggers_exit(
        self, mock_position, price_feed
    ):
        """UT-001: 初始止损触发平仓"""
        # Given: 持有多头仓位，入场价 50000
        position = await create_position(
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49500")
        )
        
        # When: 价格跌至 49499
        await price_feed.push("BTC/USDT:USDT", Decimal("49499"))
        await risk_manager.check_stop_loss(position)
        
        # Then: 仓位关闭，exit_reason='INITIAL_STOP_LOSS'
        assert position.status == "CLOSED"
        assert position.exit_reason == "INITIAL_STOP_LOSS"
        assert position.exit_price == Decimal("49499")
```

**预期收益**: 阻挡 90% 低级逻辑漏洞

---

### 3. 类型与精度宪兵 (Type & Precision Enforcer) 🛡️

**问题**: float 污染 Decimal 计算，导致金融精度丢失

**工作流**:

```
┌─────────────────────────────────────────────────────────────┐
│                   代码审查红线检查                            │
│                                                             │
│  代码提交 ──→ mypy --strict ──→ float 检测 ──→ TickSize 验证  │
│                                              │                │
│                                    ┌────────┴────────┐      │
│                                    │  任一失败？      │      │
│                                    └────────┬────────┘      │
│                                             │                │
│                          ┌──────────────────┴──────────┐    │
│                          │         Yes                 │    │
│                          │  1. 阻塞合并                 │    │
│                          │  2. 输出具体错误位置          │    │
│                          │  3. 建议修复方案              │    │
│                          └─────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**审查清单**:

| 检查项 | 工具 | 红线 |
|--------|------|------|
| 类型注解 | `mypy --strict` | 禁止 `Any` 类型 |
| 金融精度 | 自定义 AST 检查 | 禁止 `float` 用于金额/价格 |
| 边界格式化 | 自定义正则 | CCXT 调用前必须 `quantize()` |
| Pydantic 判别器 | 正则检查 | 多态模型必须有 `discriminator` |

**实现** (`.github/workflows/type-check.yml`):

```yaml
name: Type & Precision Check

on: [pull_request]

jobs:
  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install mypy
        run: pip install mypy pytest
        
      - name: Run mypy --strict
        run: mypy --strict src/
        
      - name: Check for float in financial code
        run: |
          # 禁止在 domain/ 使用 float
          if grep -r "float" src/domain/ --include="*.py"; then
            echo "❌ float detected in domain layer"
            exit 1
          fi
          
      - name: Verify Decimal quantize before exchange call
        run: |
          # 检查 CCXT 调用前是否有 quantize
          python scripts/check_quantize.py
```

**自定义检查脚本** (`scripts/check_quantize.py`):

```python
#!/usr/bin/env python3
"""检查 CCXT 调用前的 TickSize/LotSize 格式化"""

import ast
import sys
from pathlib import Path

CCXT_CALLS = {'create_order', 'cancel_order', 'fetch_balance'}

def check_quantize_in_file(filepath: Path) -> list[str]:
    errors = []
    tree = ast.parse(filepath.read_text())
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in CCXT_CALLS:
                    # 检查参数是否有 quantize 调用
                    for arg in node.args:
                        if not has_quantize(arg):
                            errors.append(
                                f"{filepath}:{node.lineno}: "
                                f"{node.func.attr}() argument missing quantize()"
                            )
    return errors

def has_quantize(node: ast.AST) -> bool:
    """检查节点是否包含 quantize() 调用"""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Attribute):
                if child.func.attr == 'quantize':
                    return True
    return False

if __name__ == "__main__":
    all_errors = []
    for py_file in Path("src").rglob("*.py"):
        all_errors.extend(check_quantize_in_file(py_file))
    
    if all_errors:
        print("❌ TickSize/LotSize 格式化检查失败:")
        for err in all_errors:
            print(f"  {err}")
        sys.exit(1)
    else:
        print("✅ TickSize/LotSize 格式化检查通过")
```

---

### 4. 并发幽灵猎手 (Concurrency Audit) 🔍

**问题**: AI 写并发代码易漏掉死锁风险、事件循环阻塞

**工作流**:

```
┌─────────────────────────────────────────────────────────────┐
│                  并发代码审查流程                              │
│                                                             │
│  检测修改文件 ──→ 是否在 critical path? ──→ No ──→ 跳过      │
│                          │                                  │
│                        Yes                                  │
│                          ↓                                  │
│              ┌───────────────────────┐                      │
│              │  强制链式思考输出       │                      │
│              │  (Sequential Thinking) │                      │
│              └───────────┬───────────┘                      │
│                          ↓                                  │
│              ┌───────────────────────┐                      │
│              │   扫描 AST 检测反模式     │                      │
│              │  1. 持锁时网络 I/O      │                      │
│              │  2. session.commit()   │                      │
│              │     未正确释放          │                      │
│              │  3. asyncio.Lock 嵌套   │                      │
│              └───────────┬───────────┘                      │
│                          ↓                                  │
│              ┌───────────────────────┐                      │
│              │   生成审查报告          │                      │
│              │  - 死锁风险分析         │                      │
│              │  - 阻塞点定位           │                      │
│              │  - 修复建议             │                      │
│              └───────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

**关键文件路径** (修改这些文件触发审查):
- `src/infrastructure/exchange_gateway.py`
- `src/domain/position_manager.py`
- `src/infrastructure/signal_repository.py`

**AST 反模式检测** (`scripts/audit_concurrency.py`):

```python
#!/usr/bin/env python3
"""并发代码审计 - 检测死锁风险和事件循环阻塞"""

import ast
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ConcurrencyIssue:
    file: str
    line: int
    issue_type: str
    description: str
    severity: str  # HIGH/MEDIUM/LOW

# 危险模式定义
DANGEROUS_PATTERNS = {
    "network_io_while_holding_lock": {
        "description": "持有 asyncio.Lock 时执行网络 I/O",
        "blocking_calls": ["aiohttp.request", "ccxt.fetch", "websocket.send"],
        "lock_types": ["asyncio.Lock", "asyncio.Condition"],
    },
    "commit_without_flush": {
        "description": "session.commit() 前未 flush 或处理异常",
        "target_calls": ["session.commit", "db.execute"],
    }
}

def audit_file(filepath: Path) -> list[ConcurrencyIssue]:
    issues = []
    source = filepath.read_text()
    tree = ast.parse(source)
    
    # 检测锁持有期间的阻塞调用
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncWith):
            # 检查 with await lock 内部
            lock_vars = extract_lock_vars(node)
            body_issues = check_body_for_blocking(node.body, lock_vars)
            issues.extend(body_issues)
    
    return issues

def check_body_for_blocking(
    body: list[ast.stmt], 
    lock_vars: set[str]
) -> list[ConcurrencyIssue]:
    """检查代码块中是否有持锁时的阻塞调用"""
    issues = []
    for stmt in body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            if is_blocking_call(call):
                issues.append(ConcurrencyIssue(
                    file=filepath.name,
                    line=stmt.lineno,
                    issue_type="network_io_while_holding_lock",
                    description=f"持锁时调用 {ast.unparse(call)}",
                    severity="HIGH"
                ))
    return issues

if __name__ == "__main__":
    critical_files = [
        Path("src/infrastructure/exchange_gateway.py"),
        Path("src/domain/position_manager.py"),
        Path("src/infrastructure/signal_repository.py"),
    ]
    
    all_issues = []
    for f in critical_files:
        all_issues.extend(audit_file(f))
    
    if all_issues:
        print("⚠️ 并发风险检测:")
        for issue in all_issues:
            print(f"  [{issue.severity}] {issue.file}:{issue.line}")
            print(f"    {issue.issue_type}: {issue.description}")
        # 不阻塞构建，仅警告
```

**链式思考模板** (AI 输出格式):

```markdown
## 并发审查 - 链式思考

### T0: 初始状态
- 文件：`exchange_gateway.py`
- 修改：添加 WebSocket 断线重连逻辑
- 涉及锁：`self._reconnect_lock`

### T1: 锁获取
```python
async with self._reconnect_lock:
    # 临界区开始
```

### T2: 临界区操作分析
| 操作 | 类型 | 风险 |
|------|------|------|
| `await self._websocket.reconnect()` | 网络 I/O | ⚠️ 持锁阻塞 |
| `await self._subscribe_all()` | 网络 I/O | ⚠️ 持锁阻塞 |

### T3: 风险识别
- **死锁风险**: 如果重连超时，其他需要重连锁的协程将永久等待
- **建议**: 使用 `asyncio.wait_for()` 包裹重连逻辑，设置超时

### T4: 修复方案
```python
async with self._reconnect_lock:
    try:
        await asyncio.wait_for(
            self._websocket.reconnect(),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        logger.error("重连超时")
        raise
```
```

---

### 5. 沙箱时间旅行 (Time-Travel Sandbox) ⏳

**问题**: 回测系统出现"未来函数"，偷看未闭合 K 线数据

**工作流**:

```
┌─────────────────────────────────────────────────────────────┐
│                   时间旅行沙箱                                │
│                                                             │
│  用户指令：验证 SignalPipeline 在特定时间点的行为              │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────┐        │
│  │  伪造系统时间                                    │        │
│  │  - 锁定在 15m K 线中间状态 (High 触及 TP1)       │        │
│  │  - 4h K 线尚未闭合                               │        │
│  └─────────────────────────────────────────────────┘        │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────┐        │
│  │  快照内存数据库                                  │        │
│  │  - 保存当前所有仓位状态                          │        │
│  │  - 保存信号队列                                  │        │
│  └─────────────────────────────────────────────────┘        │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────┐        │
│  │  验证行为                                        │        │
│  │  - 是否过早释放信号？                            │        │
│  │  - 是否偷看了 4h 收盘价？                         │        │
│  │  - MTF 对齐是否正确？                            │        │
│  └─────────────────────────────────────────────────┘        │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────┐        │
│  │  恢复快照，继续迭代                              │        │
│  └─────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

**实现** (`tests/sandbox/time_travel.py`):

```python
#!/usr/bin/env python3
"""时间旅行沙箱 - 伪造系统时间验证回测逻辑"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import patch
from dataclasses import dataclass, field

@dataclass
class TimeSnapshot:
    """系统时间快照"""
    frozen_time: datetime
    kline_state: dict  # {symbol_timeframe: KlineData}
    positions: dict    # {position_id: Position}
    signals: list      # List[Signal]

class TimeTravelSandbox:
    """时间旅行沙箱"""
    
    def __init__(self):
        self._snapshots: list[TimeSnapshot] = []
        self._current_time: datetime | None = None
    
    async def freeze_time(
        self,
        target_time: datetime,
        kline_state: dict,
    ) -> TimeSnapshot:
        """冻结系统时间到指定点"""
        self._current_time = target_time
        
        # 快照当前状态
        snapshot = TimeSnapshot(
            frozen_time=target_time,
            kline_state=kline_state.copy(),
            positions={},  # 从 DB 快照
            signals=[],    # 从 DB 快照
        )
        self._snapshots.append(snapshot)
        
        return snapshot
    
    @asynccontextmanager
    async def time_locked(self, target_time: datetime):
        """上下文管理器：时间锁定"""
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = target_time
            mock_datetime.utcnow.return_value = target_time.replace(tzinfo=timezone.utc)
            yield
        # 退出时恢复
    
    async def restore_snapshot(self, index: int = -1):
        """恢复到指定快照"""
        snapshot = self._snapshots[index]
        self._current_time = snapshot.frozen_time
        # 恢复 DB 状态...

# 使用示例
async def test_no_future_function():
    """验证信号处理不会偷看未来数据"""
    sandbox = TimeTravelSandbox()
    
    # 场景：15m K 线在 10:30，但 4h K 线尚未闭合 (闭合时间是 12:00)
    kline_state = {
        "BTC/USDT:USDT:15m": KlineData(
            timestamp=datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc),
            open=Decimal("50000"),
            high=Decimal("50100"),  # TP1 触及
            low=Decimal("49900"),
            close=Decimal("50050"),  # 尚未最终闭合
            is_closed=False,  # 关键：K 线未闭合
        ),
        "BTC/USDT:USDT:4h": KlineData(
            timestamp=datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc),
            open=Decimal("49800"),
            high=Decimal("50200"),
            low=Decimal("49700"),
            close=Decimal("50100"),  # 这是"未来"数据！
            is_closed=False,  # 4h K 线也未闭合
        ),
    }
    
    await sandbox.freeze_time(
        target_time=datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc),
        kline_state=kline_state,
    )
    
    async with sandbox.time_locked(
        datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc)
    ):
        # 运行信号管道
        pipeline = SignalPipeline(...)
        result = await pipeline.process_kline(kline_state["BTC/USDT:USDT:15m"])
        
        # 验证：MTF 过滤器不应使用 4h 的未闭合收盘价
        assert not result.used_unconfirmed_4h_close
```

---

## 实施路线图

### Phase 1: 基础建设 (本周)
- [ ] TDD 闭环自愈技能 - 集成 pytest 执行权限
- [ ] 类型与精度宪兵 - CI 工作流 + 检查脚本

### Phase 2: 进阶能力 (下周)
- [ ] 并发幽灵猎手 - AST 反模式检测
- [ ] 契约双向同步 - 文档解析 + AST 比对

### Phase 3: 沙箱环境 (实盘前)
- [ ] 时间旅行沙箱 - 可伪造时间的测试框架

---

## 与其他 MCP 的集成

| 技能 | 依赖 MCP | 集成方式 |
|------|----------|----------|
| TDD 自愈 | 无 | 直接 Bash 执行 pytest |
| 类型宪兵 | filesystem | 读取代码 + 执行检查脚本 |
| 并发猎手 | filesystem | AST 分析 |
| 契约同步 | filesystem + Git | 读写文档 + 提交变更 |
| 时间沙箱 | 无 | Python 单元测试 |

---

*设计日期：2026-04-01*
*盯盘狗 v3.0 - Agentic Workflow*
