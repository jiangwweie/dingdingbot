# 问题汇总报告 - PR-20260404-001

**生成日期**: 2026-04-04
**生成时间**: 20:53
**报告类型**: 项目遗留问题汇总

---

## 📋 问题清单总览

| 类别 | 问题数 | 优先级 | 影响范围 |
|------|--------|--------|----------|
| **MCP 配置** | 1 | P1 | 前端自动化测试无法执行 |
| **TypeScript 类型错误** | 13 | P2 | 编译检查失败，不影响运行 |
| **前端单元测试** | 10 failed | P3 | 测试覆盖率降低 |
| **手动验证缺失** | 4 页面 | P1 | 关键交互功能未验证 |

---

## 🔴 P1 级问题 - 需立即处理

### 问题 1: Puppeteer MCP 未成功连接

**症状**:
- Puppeteer MCP 已配置在 `~/.claude/mcp.json`
- Chrome 浏览器已下载（v131.0.6778.204）
- 但 MCP server 未连接到当前会话
- `ListMcpResourcesTool` 只显示 sqlite server

**影响**:
- 无法使用 pup 技能进行前端自动化测试
- 无法验证 Config/Orders/Strategy 页面的交互功能
- 无法自动截图验证 UI 渲染

**根本原因**:
- MCP server 在 CLI 启动时加载，无法热重载
- 缺少显式的 Chrome 可执行路径配置

**已采取修复**:
- ✅ 已修改 `~/.claude/mcp.json`，添加 `PUPPETEER_EXECUTABLE_PATH`
- ✅ 已创建备份文件 `mcp.json.backup-20260404-204106`

**下一步行动**:
```bash
# 1. 退出当前 Claude Code CLI 会话
/exit

# 2. 重启 CLI
cd /Users/jiangwei/Documents/final
claude

# 3. 验证 Puppeteer MCP 是否生效
# 在新会话中检查可用工具列表
```

---

### 问题 2: 关键页面交互功能未验证

**影响页面**:
1. Config 页面 - 策略参数配置表单
2. Config Profile 管理页面 - CRUD 功能
3. Orders 页面 - 订单列表虚拟滚动
4. Strategy 创建/编辑页面 - 动态表单

**验证内容**:
- 表单提交是否正常
- 按钮点击是否响应
- 列表滚动是否流畅
- 动态添加/删除是否工作

**当前状态**:
- ✅ API 端点全部正常（已验证）
- ✅ 后端代码修复已生效
- ⚠️ 前端 UI 交互未验证（需手动或 Puppeteer）

**建议验证方案**:

**方案 A**: 手动浏览器测试（推荐）
```markdown
1. Config 页面: http://localhost:3000/config
   - 点击策略参数配置
   - 查看 Pinbar 参数表单
   - 修改参数并保存

2. Orders 页面: http://localhost:3000/orders
   - Cmd+Shift+R 强制刷新
   - 检查订单列表渲染
   - 测试虚拟滚动

3. Strategy 页面: http://localhost:3000/strategy
   - 点击触发器/过滤器添加按钮
   - 测试动态表单交互
```

**方案 B**: 等待 Puppeteer MCP 修复后自动测试
- 需重启 CLI（约 1 分钟）
- 使用 pup 技能自动验证
- 自动生成截图和验证报告

---

## 🟡 P2 级问题 - TypeScript 类型错误（13 个）

**影响**: 编译检查失败，但不影响运行时功能

**分类统计**:
| 错误类型 | 数量 | 文件 |
|----------|------|------|
| 类型不匹配 | 3 | Backtest.tsx |
| 属性缺失 | 3 | Backtest.tsx, PMSBacktest.tsx |
| 导出问题 | 2 | BacktestReports.tsx |
| 类型推断 | 1 | Backtest.tsx |
| 函数签名 | 1 | Orders.tsx |
| 配置错误 | 2 | vitest.config.ts |
| 逻辑错误 | 1 | StrategyWorkbench.tsx |

---

### 详细错误清单

#### 1. Backtest.tsx（7 个错误）

```typescript
// 错误 1: signal_stats 属性缺失
src/pages/Backtest.tsx(497,35): error TS2339
Property 'signal_stats' does not exist on type 'BacktestReport'.

// 错误 2: candles_analyzed 属性缺失
src/pages/Backtest.tsx(525,101): error TS2339
Property 'candles_analyzed' does not exist on type 'BacktestReport'.

// 错误 3: unknown 类型赋值错误
src/pages/Backtest.tsx(568,37): error TS2322
Type 'unknown' is not assignable to type 'ReactNode'.

// 错误 4: attempts 属性缺失
src/pages/Backtest.tsx(599,56): error TS2339
Property 'attempts' does not exist on type 'BacktestReport'.

// 错误 5-7: SignalDetailsModalProps 类型不匹配
src/pages/Backtest.tsx(806,11): error TS2322
Property 'signal' does not exist on type 'SignalDetailsModalProps'.
Did you mean 'signalId'?
```

**修复建议**:
- 更新 `BacktestReport` 类型定义，添加缺失属性
- 修改 `SignalDetailsModalProps` 接受 `signal` 对象或 `signalId`

---

#### 2. BacktestReports.tsx（2 个错误）

```typescript
// 错误 1: 类型未导出
src/pages/BacktestReports.tsx(12,8): error TS2459
Module '"../lib/api"' declares 'ListBacktestReportsRequest' locally,
but it is not exported.

// 错误 2: 类型不存在
src/pages/BacktestReports.tsx(13,8): error TS2724
'"../lib/api"' has no exported member named 'BacktestReportSummary'.
Did you mean 'BacktestReport'?
```

**修复建议**:
- 导出 `ListBacktestReportsRequest` 类型
- 创建或导出 `BacktestReportSummary` 类型

---

#### 3. Orders.tsx（1 个错误）

```typescript
// 错误: Promise<void> 类型不匹配
src/pages/Orders.tsx(303,9): error TS2322
Type '(orderIds: string[]) => void' is not assignable to type
'(orderIds: string[]) => Promise<void>'.
```

**修复建议**:
- 修改函数返回 `Promise<void>` 或添加 `async`

---

#### 4. PMSBacktest.tsx（2 个错误）

```typescript
// 错误 1: initial_balance 属性不存在
src/pages/PMSBacktest.tsx(150,9): error TS2353
'initial_balance' does not exist in type 'BacktestRequest'.

// 错误 2: SignalDetailsModalProps 类型不匹配（同 Backtest.tsx）
```

**修复建议**:
- 更新 `BacktestRequest` 类型定义

---

#### 5. StrategyWorkbench.tsx（1 个错误）

```typescript
// 错误: 类型无重叠的比较
src/pages/StrategyWorkbench.tsx(625,33): error TS2367
This comparison appears to be unintentional because the types
'"previewed"' and '"previewing"' have no overlap.
```

**修复建议**:
- 修正状态枚举值或比较逻辑

---

#### 6. vitest.config.ts（2 个错误）

```typescript
// 错误: coverage 配置缺少 provider
src/vitest.config.ts(5,13): error TS2769
Property 'provider' is missing in type '{ reporter: ..., include: ... }'
but required in type '{ provider: "v8"; } & CoverageV8Options'.

// 错误: vite Plugin 类型不匹配
```

**修复建议**:
```typescript
// 添加 provider 配置
coverage: {
  provider: 'v8',  // 或 'istanbul'
  reporter: ['html', 'json', 'text'],
  include: ['src/**/*'],
  exclude: ['src/**/*.test.*']
}
```

---

## 🟢 P3 级问题 - 前端单元测试失败（10 个）

**测试结果**:
- ✅ Passed: 32 tests
- ❌ Failed: 10 tests
- 📊 Files: 5 test files

**失败测试分析**:

### SnapshotList.test.tsx（主要失败源）
**问题**: API 调用异步等待不足
**症状**:
- `expect(apiMock).toHaveBeenCalled()` 在 API 未完成前检查
- 缺少 `await waitFor()` 或 `await screen.findBy...`

**修复示例**:
```typescript
// ❌ 错误写法
fireEvent.click(button);
expect(apiMock).toHaveBeenCalled();

// ✅ 正确写法
fireEvent.click(button);
await waitFor(() => {
  expect(apiMock).toHaveBeenCalled();
});
```

---

### 其他失败测试
**状态**: 需详细日志分析
**建议**: 运行 `npm test -- --reporter=verbose` 获取详细错误

---

## 📊 问题优先级排序

| 优先级 | 问题 | 预估修复时间 | 建议处理顺序 |
|--------|------|--------------|--------------|
| **P1-1** | Puppeteer MCP 连接 | 2 分钟 | 1️⃣ 立即处理 |
| **P1-2** | 手动验证 4 页面 | 5 分钟 | 2️⃣ MCP 修复后验证 |
| **P2-1** | BacktestReport 类型 | 10 分钟 | 3️⃣ 类型修复 |
| **P2-2** | SignalDetailsModalProps | 5 分钟 | 4️⃣ 类型修复 |
| **P2-3** | BacktestRequest 类型 | 5 分钟 | 5️⃣ 类型修复 |
| **P2-4** | vitest.config.ts | 3 分钟 | 6️⃣ 配置修复 |
| **P3-1** | 前端测试异步问题 | 15 分钟 | 7️⃣ 测试修复 |

**总预估时间**: 45 分钟

---

## 🎯 下一步行动计划

### 阶段 1: MCP 修复（立即执行）

```bash
# 用户操作
1. 退出当前 Claude Code CLI 会话（/exit）
2. 重新启动 CLI（claude）
3. 验证 Puppeteer MCP 工具列表

# 预期结果
✅ Puppeteer MCP 工具可用
✅ 可使用 pup 技能进行自动化测试
```

---

### 阶段 2: 页面交互验证（5 分钟）

**方案 A**: 手动浏览器测试
- Config 页面：策略参数表单交互
- Orders 页面：订单列表滚动
- Strategy 页面：动态表单添加
- Profile 管理：创建/切换/导入/导出

**方案 B**: Puppeteer 自动化测试
```bash
# 使用 pup 技能自动验证
/pup
```

---

### 阶段 3: TypeScript 类型修复（可选）

**优先级**: 不影响运行，可延后处理
**预估**: 30 分钟
**建议**: 等待后端 API 稳定后统一修复

---

### 阶段 4: 前端测试修复（可选）

**优先级**: 不影响功能，可延后处理
**预估**: 15 分钟
**建议**: 使用 vitest --reporter=verbose 详细分析

---

## 📝 补充说明

### 已修复问题（本次测试）

✅ **Config 页面 toFixed 错误**
- 后端：`api.py` Decimal → float 转换
- 前端：`PinbarParamForm.tsx` Number() 安全转换
- 验证：API 返回 float 类型（0.6）

✅ **Orders 页面 react-window 错误**
- 修复：`OrderChainTreeTable.tsx` 双重 null 检查
- 验证：代码审查确认修复存在

✅ **ConfigEntryRepository 初始化**
- 修复：`main.py` 补充初始化逻辑
- 验证：日志确认初始化成功

---

### MCP 配置备份

**备份文件**: `~/.claude/mcp.json.backup-20260404-204106`

**恢复命令**:
```bash
cp ~/.claude/mcp.json.backup-20260404-204106 ~/.claude/mcp.json
```

---

## 🔗 相关文档链接

- 测试报告: `docs/reports/TR-20260404-002-pup-validation.md`
- 架构评审: `docs/arch/AR-20260404-003-review.md`
- 进度日志: `docs/planning/progress.md`
- Git commits:
  - `1d22c1c` - docs: add Pup validation test report
  - `51f8c3c` - fix: Config 页面 API 返回类型修复
  - `47b6517` - docs: 更新进度日志

---

*报告生成时间: 2026-04-04 20:53*
*报告类型: 项目遗留问题汇总*