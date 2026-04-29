# Task Plan: 回测财务记账修复（方案 A + 方案 B + max_drawdown 修复）

> **创建时间**: 2026-04-14
> **执行人**: Backend Developer
> **关联架构文档**: `docs/planning/architecture/backtest-accounting-fix-arch.md`

---

## 任务分解

### 阶段 1: 方案 A - 修复 account_snapshot.positions
- [x] 阅读 models.py 确认 PositionInfo 字段定义
- [x] 阅读 backtester.py 确认 positions_map 可用位置
- [x] 实现 `_build_account_snapshot()` 辅助方法
- [x] 替换 `positions=[]` 为调用新方法
- [x] 从 PositionInfo import 确认

### 阶段 2: 方案 B - 添加调试日志
- [x] backtester.py 信号创建处添加 logger.debug
- [x] backtester.py PositionSummary 创建处添加 logger.debug
- [x] matching_engine.py PnL 计算处添加 logger.debug

### 阶段 3: 修复 max_drawdown 计算
- [x] 改为累计余额计算 max_drawdown

### 阶段 4: 验证
- [x] 运行现有测试确保不被破坏 (79 passed, 1 pre-existing failure, 2 pre-existing failures)
- [ ] 更新 progress.md 和 findings.md

---

## 任务: PMS 回测 Direction/PnL 一致性验证

> **创建时间**: 2026-04-14
> **执行人**: QA Tester
> **背景**: DA-20260414-001 声称发现"11 笔 LONG 仓位 PnL 匹配 SHORT 公式"的方向矛盾 bug，RCA 分析认为代码层面方向全程一致

### 阶段 1: 创建验证脚本
- [x] 阅读 debug_pms.py 了解回测运行方式
- [x] 创建 tests/integration/test_direction_pnl_consistency.py
- [x] 实现 direction/PnL 一致性验证逻辑

### 阶段 2: 运行验证
- [x] 查询 backtest_reports 表中现有回测数据
- [x] 检查每个 PositionSummary 的 direction 和 realized_pnl 是否数学一致
- [x] 生成验证报告（44 个仓位，16 个显示方向矛盾）

### 阶段 3: 根因分析
- [x] 分析 16 个方向矛盾仓位的共同特征（全部 exit_reason=SL）
- [x] 确认 realized_pnl 是累计值（matching_engine.py line 279/351: += net_pnl）
- [x] 确认方向矛盾由 partial TP1 close + SL close 组合导致
- [x] 结论：不存在方向矛盾 bug，DA-20260414-001 数据来源有误
- [ ] 输出总仓位数、方向一致数、方向矛盾数
- [ ] 如有矛盾，打印详细信息并报告给 PM

---

## 技术笔记

- PositionInfo 字段: symbol, side(str: "long"/"short"), size(Decimal), entry_price(Decimal), unrealized_pnl(Decimal), leverage(int)
- Direction enum: LONG="LONG", SHORT="SHORT" → side = direction.value.lower()
- positions_map 在 _run_v3_pms_backtest 方法内可用，是 Dict[str, Position]
- Position 实体字段: direction, current_qty, entry_price, realized_pnl, is_closed, symbol, signal_id, id
- 测试验证: 79 passed, 1 pre-existing failure (test_backtester_mtf.py mock signature), 2 pre-existing failures (test_backtest_user_story.py)
