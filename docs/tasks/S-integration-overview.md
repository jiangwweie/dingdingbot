# Phase 4 + Phase 5 集成测试总览

**创建日期**: 2026-03-27
**执行方式**: 3 窗口并行

---

## 测试任务总览

| 编号 | 测试场景 | 涉及功能 | 优先级 | 预估工时 | 负责窗口 |
|------|----------|----------|--------|----------|----------|
| **Test-01** | 配置快照 + WebSocket 降级联动 | S4-1 + S5-1 | P1 | 2-3h | 窗口 3 |
| **Test-02** | 队列背压 + WebSocket 降级 | S4-2 + S5-1 | P2 | 2-3h | 窗口 2 |
| **Test-03** | EMA 缓存 + WebSocket 降级 | S4-3 + S5-1 | P2 | 2-3h | 窗口 1 |
| **Test-04** | 快照回滚 + 信号状态连续性 | S4-1 + S5-2 | P0 | 3-4h | 窗口 1 |
| **Test-05** | 队列拥堵 + 信号状态完整性 | S4-2 + S5-2 | P0 | 4-6h | 窗口 2 |
| **Test-06** | 多策略 +EMA 缓存 + 状态跟踪 | S4-3 + S5-2 | P1 | 3-4h | 窗口 3 |

**总计**: 6 个测试任务，预计 16-23 小时，3 窗口并行后约 6-9 小时完成

---

## 窗口分配

### 窗口 1（Claude - 主窗口）

| 顺序 | 任务 | 文档 | 状态 |
|------|------|------|------|
| 1 | Test-04: 快照回滚 + 信号状态连续性 | `S-integration-Test04.md` | ⏳ 待执行 |
| 2 | Test-03: EMA 缓存 + WebSocket 降级 | `S-integration-Test03.md` | ⏳ 待执行 |

**预计耗时**: 5-7h

---

### 窗口 2（用户）

| 顺序 | 任务 | 文档 | 状态 |
|------|------|------|------|
| 1 | Test-05: 队列拥堵 + 信号状态完整性 | `S-integration-Test05.md` | ⏳ 待执行 |
| 2 | Test-02: 队列背压 + WebSocket 降级 | `S-integration-Test02.md` | ⏳ 待执行 |

**预计耗时**: 6-9h

---

### 窗口 3（用户）

| 顺序 | 任务 | 文档 | 状态 |
|------|------|------|------|
| 1 | Test-01: 配置快照 + WebSocket 降级 | `S-integration-Test01.md` | ⏳ 待执行 |
| 2 | Test-06: 多策略 +EMA 缓存 + 状态跟踪 | `S-integration-Test06.md` | ⏳ 待执行 |

**预计耗时**: 5-7h

---

## 执行前准备（所有窗口）

### 1. 环境检查

```bash
# 所有窗口执行相同检查
cd /Users/jiangwei/Documents/dingdingbot

# 确认代码版本（Phase 4 + Phase 5 已完成）
git log --oneline -5

# 确认测试依赖
pip list | grep -E "pytest|ccxt|ccxtpro"
```

### 2. API Key 配置

所有窗口使用**同一套测试网 API Key**：

```yaml
# config/user.yaml (所有窗口相同)
exchange:
  testnet: true
  api_key: "YOUR_BINANCE_TESTNET_API_KEY"
  api_secret: "YOUR_BINANCE_TESTNET_SECRET"
```

### 3. 测试文件结构

```
tests/integration/
├── test_snapshot_rollback_signal_continuity.py    # Test-04
├── test_ema_cache_ws_fallback.py                   # Test-03
├── test_queue_congestion_signal_integrity.py      # Test-05
├── test_queue_backpressure_ws.py                   # Test-02
├── test_snapshot_ws_fallback.py                    # Test-01
└── test_multi_strategy_ema_signal_tracking.py     # Test-06
```

---

## 测试依赖关系

```
所有测试相互独立，无依赖关系

┌──────────┐
│ 窗口 1    │ → Test-04 → Test-03
├──────────┤
│ 窗口 2    │ → Test-05 → Test-02
├──────────┤
│ 窗口 3    │ → Test-01 → Test-06
└──────────┘
```

---

## 执行流程

### 各窗口独立执行

1. 读取对应的任务执行文档
2. 按文档步骤执行测试开发
3. 运行测试验证
4. 提交代码

### 进度同步

每个测试完成后，在本文档更新状态：

```markdown
| 任务 | 窗口 | 状态 | 完成时间 | 提交 |
|------|------|------|----------|------|
| Test-01 | 窗口 3 | ✅ 完成 | - | - |
| Test-02 | 窗口 2 | ✅ 完成 | - | - |
| Test-03 | 窗口 1 | ✅ 完成 | - | - |
| Test-04 | 窗口 1 | ✅ 完成 | - | - |
| Test-05 | 窗口 2 | ✅ 完成 | - | - |
| Test-06 | 窗口 3 | ✅ 完成 | - | - |
```

---

## 提交规范

每个测试独立提交：

```bash
git add tests/integration/test_xxx.py
git commit -m "test(integration): 添加 <测试场景> 集成测试 (#Test-XX)"
```

---

## 验收标准

所有测试通过：

```bash
# 单个测试运行
pytest tests/integration/test_xxx.py -v

# 全部集成测试运行
pytest tests/integration/ -v
```

预期结果：
- 6 个测试文件全部创建
- 所有测试 100% 通过
- 无类型错误
- 代码符合项目规范

---

## 风险与应对

| 风险 | 应对方案 |
|------|----------|
| 测试网 API 限流 | 各窗口错开执行时间，使用不同 API Key |
| 测试文件冲突 | 每个测试独立文件，提交前 git pull |
| 测试环境不一致 | 所有窗口使用相同 config/user.yaml |
| 并发问题难以复现 | 多次运行验证，使用确定性时间戳 |

---

## 下一步

1. **所有窗口**：读取对应的任务执行文档
2. **窗口 1**：开始执行 Test-04
3. **窗口 2**：开始执行 Test-05
4. **窗口 3**：开始执行 Test-01

---

*本文档为集成测试协调中心，所有窗口执行前必读*
