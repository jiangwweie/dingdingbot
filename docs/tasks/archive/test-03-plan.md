# Test-03: EMA 缓存 + WebSocket 降级集成测试

**优先级**: P2 | **预估工时**: 2-3h | **负责窗口**: 窗口 1（Claude）

**目标**: 验证 WebSocket 降级时，EMA 缓存正确失效/重建，避免使用过期数据。

---

## 阶段概览

| 阶段 | 任务 | 状态 | 提交 |
|------|------|------|------|
| 1 | 创建测试文件框架 | ✅ 完成 | - |
| 2 | 实现 Test Fixtures | ✅ 完成 | - |
| 3 | 实现测试用例 1: EMA 缓存重建 | ✅ 完成 | - |
| 4 | 实现测试用例 2: WebSocket 降级验证 | ✅ 完成 | - |
| 5 | 实现测试用例 3: EMA 缓存更新 | ✅ 完成 | - |
| 6 | 运行测试验证 | ✅ 完成 (3 passed) | - |
| 7 | 提交代码 | ✅ 完成 | 399bed1 |

---

**窗口 1 状态**: Test-04 ✅ 完成，Test-03 ✅ 完成

---

## 执行步骤

### 阶段 1: 创建测试文件框架

**文件**: `tests/integration/test_ema_cache_ws_fallback.py`

---

### 阶段 2: 实现 Test Fixtures

**Fixtures**:
- `ema_cache` - EMACache 实例
- `config_manager` - ConfigManager 实例
- `exchange_gateway` - ExchangeGateway 实例
- `signal_pipeline` - SignalPipeline 实例

---

### 阶段 3: 实现测试用例 1

**测试**: `test_ema_cache_rebuild_on_ws_fallback`

验证 WebSocket 降级时 EMA 缓存正确重建。

---

### 阶段 4: 实现测试用例 2

**测试**: `test_websocket_fallback_triggers_cache_invalidation`

验证 WebSocket 降级触发缓存失效。

---

### 阶段 5: 实现测试用例 3

**测试**: `test_multi_timeframe_ema_consistency_after_fallback`

验证多周期 EMA 一致性。

---

### 阶段 6: 运行测试验证

```bash
pytest tests/integration/test_ema_cache_ws_fallback.py -v
```

---

### 阶段 7: 提交代码

```
test(integration): 添加 EMA 缓存+WebSocket 降级集成测试 (#Test-03)
```

---

## 相关文档

- `docs/tasks/S-integration-Test03.md` - 完整任务文档
- `docs/planning/integration-test-plan.md` - 集成测试总计划
