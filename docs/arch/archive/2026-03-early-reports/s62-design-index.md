# S6-2 Pinbar 评分优化与信号覆盖 - 设计文档索引

**创建日期**: 2026-03-29
**状态**: 设计完成，待实施
**优先级**: 高

---

## 📍 设计文档位置

### 主设计文档
**文件**: `docs/tasks/2026-03-29-子任务 S6-2-Pinbar 评分优化与信号覆盖.md`

**内容包括**:
1. 问题背景与数据分析（21:00 vs 22:00 Pinbar 案例）
2. 核心规则（ATR 门槛、评分公式、覆盖规则）
3. 现状分析（架构摸底，已有组件清单）
4. 任务分解（6 个子任务的详细实现方案）
5. 设计决策记录（覆盖范围、评分公式、ATR 过滤）
6. 依赖关系与验收标准
7. 影响范围分析（SignalStatus 扩展的前后端引用清单）

---

## 📋 进度文档位置

**文件**: `docs/planning/progress.md`

**查找方式**: 打开文件，查看最新条目 `## 2026-03-29 - 会话：S6-2 Pinbar 评分优化与信号覆盖设计`

---

## 🎯 核心设计决策摘要

### 决策 1: 覆盖范围 - 同策略内覆盖
- **规则**: Pinbar 只和 Pinbar 比，Engulfing 只和 Engulfing 比
- **实现**: `dedup_key = f"{symbol}:{timeframe}:{direction}:{strategy_name}"`
- **理由**: 不同策略的评分标准不同，跨策略比较不公平

### 决策 2: 评分公式 - 统一基类提供
- **公式**: `score = pattern_ratio × 0.7 + min(atr_ratio, 2.0) × 0.3`
- **实现**: `PatternStrategy.calculate_score()` 基类方法
- **理由**: 保证同策略内分数可比性

### 决策 3: ATR 门槛过滤 - 策略共用
- **门槛**: `min_atr_ratio = 0.5`（K 线波幅 ≥ ATR × 0.5）
- **实现**: `AtrFilterDynamic` 作为通用 Filter
- **理由**: 十字星/一字线问题对所有形态策略都存在

---

## 📦 任务清单

| 编号 | 任务 | 文件 | 预计工时 |
|------|------|------|----------|
| S6-2-1 | ATR 过滤器配置与集成 | `filter_factory.py`, `core.yaml` | 2-3h |
| S6-2-2 | 评分公式优化 (ATR 调整) | `strategy_engine.py` | 1-2h |
| S6-2-3 | 数据库字段扩展 | `signal_repository.py` | 1h |
| S6-2-4 | 信号覆盖逻辑（整合冷却期） | `signal_pipeline.py` | 2-3h |
| S6-2-5 | 通知消息增强 | `notifier.py` | 1-2h |
| S6-2-6 | 前端信号列表增强 | `Signals.tsx`, `SignalStatusBadge.tsx` | 2-3h |

**总计**: 约 10-16 小时

---

## 🔗 依赖关系

```
S6-2-1 (ATR 过滤器配置)
    ↓
S6-2-2 (评分优化)
    ↓
S6-2-3 (数据库扩展)
    ↓
S6-2-4 (覆盖逻辑)
    ↓
S6-2-5 (通知增强)
    ↓
S6-2-6 (前端增强)
```

---

## 📂 相关文件清单

### 后端 Python (6 个)
- `src/domain/models.py` - SignalStatus 枚举扩展
- `src/domain/strategy_engine.py` - PinbarStrategy 评分优化
- `src/domain/filter_factory.py` - AtrFilterDynamic 配置
- `src/application/signal_pipeline.py` - 覆盖逻辑整合
- `src/infrastructure/signal_repository.py` - 数据库字段扩展
- `src/infrastructure/notifier.py` - 通知消息增强

### 前端 TypeScript (3 个)
- `web-front/src/lib/api.ts` - SignalStatus 枚举和接口扩展
- `web-front/src/components/SignalStatusBadge.tsx` - 状态徽章组件
- `web-front/src/pages/Signals.tsx` - 信号列表页

### 配置文件 (1 个)
- `config/core.yaml` - ATR 过滤器配置

### 测试文件 (2 个)
- `tests/unit/test_filter_factory.py` - ATR 过滤器测试
- `tests/unit/test_strategy_engine.py` - 评分优化测试

---

## 🏷️ 快速查找命令

```bash
# 查找设计文档
cat docs/tasks/2026-03-29-子任务\ S6-2-Pinbar\ 评分优化与信号覆盖.md

# 查找进度日志
grep -A 50 "S6-2 Pinbar 评分优化" docs/planning/progress.md

# 查找所有相关任务
grep "S6-2" docs/tasks/*.md
```

---

## 📝 Git 提交记录（实施后更新）

| 提交哈希 | 说明 | 日期 |
|----------|------|------|
| 待提交 | S6-2-1: ATR 过滤器配置 | - |
| 待提交 | S6-2-2: 评分公式优化 | - |
| 待提交 | S6-2-3: 数据库扩展 | - |
| 待提交 | S6-2-4: 信号覆盖逻辑 | - |
| 待提交 | S6-2-5: 通知消息增强 | - |
| 待提交 | S6-2-6: 前端增强 | - |

---

*文档结束 - 更新于 2026-03-29*
