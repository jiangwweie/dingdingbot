# 任务计划 - T004 P2-4 止损逻辑歧义修复

> **任务 ID**: T004
> **优先级**: P2
> **工时估算**: 3h
> **创建时间**: 2026-04-07
> **状态**: 已完成 ✅

---

## 任务目标

修复 `_calculate_stop_loss_price()` 方法的语义歧义问题，并添加完整的单元测试覆盖。

---

## 阶段划分

### 阶段 1: 代码验证 (已完成 ✅)
- [x] 阅读设计文档 `docs/arch/order-management-fix-design.md`
- [x] 确认 `_calculate_stop_loss_price()` 方法已按修复代码实现
- [x] 确认修复代码与设计文档一致

**验证结果**:
- 代码已修复 (第 430-483 行)
- 语义说明清晰：`rr_multiple < 0` 表示 RR 倍数，`rr_multiple > 0` 表示百分比
- `rr_multiple=-1.0` 正确计算为 1% 止损

### 阶段 2: 单元测试编写 (已完成 ✅)
- [x] 新增 `test_rr_mode_long_position` - LONG 1R 止损
- [x] 新增 `test_rr_mode_short_position` - SHORT 1R 止损
- [x] 新增 `test_percent_mode_long_position` - LONG 2% 止损
- [x] 新增 `test_percent_mode_short_position` - SHORT 2% 止损
- [x] 新增 `test_rr_mode_2r_stop_loss` - 2R 止损

**测试结果**:
```
LONG 1R (rr=-1.0): 50000 → 49500 (50000 × 0.99) ✅
SHORT 1R (rr=-1.0): 50000 → 50500 (50000 × 1.01) ✅
LONG 2% (rr=0.02): 50000 → 49000 (50000 × 0.98) ✅
SHORT 2% (rr=0.02): 50000 → 51000 (50000 × 1.02) ✅
LONG 2R (rr=-2.0): 50000 → 49000 (50000 × 0.98) ✅
```

### 阶段 3: 测试验证 (已完成 ✅)
- [x] 运行 `pytest tests/unit/test_order_manager.py -v`
- [x] 确认新增 5 个测试全部通过
- [x] 确认现有测试无回归 (53 passed)

### 阶段 4: 文档更新 (已完成 ✅)
- [x] 更新 `docs/planning/task_plan.md`
- [x] 更新 `docs/planning/progress.md`
- [x] Git 提交

---

## 验收标准

- ✅ `_calculate_stop_loss_price()` 明确区分 RR 倍数和百分比语义
- ✅ `rr_multiple=-1.0` 正确计算为 1% 止损（而非 2%）
- ✅ 新增 5 个单元测试全部通过
- ✅ 现有测试无回归 (53 passed)

---

## 相关文件

| 文件 | 路径 | 状态 |
|------|------|------|
| 设计文档 | `docs/arch/order-management-fix-design.md` | 已阅读 |
| 源代码 | `src/domain/order_manager.py` | 已验证 |
| 测试文件 | `tests/unit/test_order_manager.py` | 已新增测试 |
| 任务计划 | `docs/planning/task_plan.md` | 已更新 |
| 进度日志 | `docs/planning/progress.md` | 已更新 |
