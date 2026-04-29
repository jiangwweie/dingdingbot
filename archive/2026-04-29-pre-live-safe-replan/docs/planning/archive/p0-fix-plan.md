# P0 缺陷修复任务计划

> **创建时间**: 2026-04-08  
> **关联 ADR**: `docs/arch/P0-websocket-kline-fix-design.md`  
> **实施清单**: `docs/arch/P0-implementation-checklist.md`  
> **测试清单**: `docs/arch/P0-test-checklist.md`

---

## 任务总览

| 任务 | 优先级 | 状态 | 预计工时 |
|------|--------|------|----------|
| 修复 1: WebSocket K 线选择逻辑 | P0 | ⏳ Pending | 2h |
| 修复 2: Pinbar 最小波幅检查 | P0 | ⏳ Pending | 1h |
| 修复 3: ATR 过滤器默认值确认 | P1 | ⏳ Pending | 0.5h |
| 单元测试编写 | P0 | ⏳ Pending | 2h |
| 测试运行与验证 | P0 | ⏳ Pending | 0.5h |

---

## 阶段 1: WebSocket K 线选择逻辑修复

### 待办事项
- [ ] 读取 `src/infrastructure/exchange_gateway.py`
- [ ] 修改 `_parse_ohlcv()` 方法签名（新增 `raw_info` 参数）
- [ ] 修改 `_subscribe_ohlcv_loop()` 方法（核心修复）
- [ ] 添加 DEBUG 日志
- [ ] 编写单元测试 `test_websocket_kline_selection.py`

### 验收标准
- [ ] 优先使用交易所 `x` 字段
- [ ] 后备时间戳推断机制
- [ ] 单元测试覆盖率 >85%

---

## 阶段 2: Pinbar 最小波幅检查

### 待办事项
- [ ] 读取 `src/domain/strategy_engine.py`
- [ ] 修改 `PinbarStrategy.detect()` 方法
- [ ] 添加最小波幅检查逻辑
- [ ] 编写单元测试 `test_pinbar_min_range.py`

### 验收标准
- [ ] ATR 可用时使用 10% 阈值
- [ ] 后备固定值 0.5 USDT
- [ ] DEBUG 级别日志

---

## 阶段 3: ATR 过滤器默认值确认

### 待办事项
- [ ] 读取 `src/domain/filter_factory.py`
- [ ] 确认 `AtrFilterDynamic.__init__()` 默认值

### 验收标准
- [ ] `enabled=False` 默认值
- [ ] `min_atr_ratio=0.001` 保持

---

## 阶段 4: 单元测试

### 待办事项
- [ ] 创建 `tests/unit/test_websocket_kline_selection.py`
- [ ] 创建 `tests/unit/test_pinbar_min_range.py`
- [ ] 更新 `tests/unit/test_filter_factory_atr.py`
- [ ] 运行测试验证

### 验收标准
- [ ] 所有测试通过
- [ ] 覆盖率 >85%

---

## 阶段 5: Git 提交

### 提交计划
1. `fix(P0): WebSocket K 线选择逻辑修复`
2. `fix(P0): Pinbar 最小波幅检查`
3. `test(P0): WebSocket + Pinbar 单元测试`

---

*最后更新：2026-04-08*
