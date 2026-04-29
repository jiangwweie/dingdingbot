# Phase 4 + Phase 5 集成测试任务计划

**当前日期**: 2026-03-27
**执行方式**: 3 窗口并行
**当前状态**: 用户重启电脑前，准备启动 3 个窗口

---

## 任务总览

| 编号 | 测试场景 | 涉及功能 | 优先级 | 预估工时 | 负责窗口 | 状态 |
|------|----------|----------|--------|----------|----------|------|
| **Test-01** | 配置快照 + WebSocket 降级联动 | S4-1 + S5-1 | P1 | 2-3h | 窗口 3 | ✅ 已完成 |
| **Test-02** | 队列背压 + WebSocket 降级 | S4-2 + S5-1 | P2 | 2-3h | 窗口 2 | ✅ 已完成 |
| **Test-03** | EMA 缓存 + WebSocket 降级 | S4-3 + S5-1 | P2 | 2-3h | 窗口 1 | ✅ 已完成 |
| **Test-04** | 快照回滚 + 信号状态连续性 | S4-1 + S5-2 | P0 | 3-4h | 窗口 1 | ✅ 已完成 |
| **Test-05** | 队列拥堵 + 信号状态完整性 | S4-2 + S5-2 | P0 | 4-6h | 窗口 2 | ✅ 已完成 |
| **Test-06** | 多策略 +EMA 缓存 + 状态跟踪 | S4-3 + S5-2 | P1 | 3-4h | 窗口 3 | ✅ 已完成 |

**总计**: 6 个测试任务，预计 16-23 小时，3 窗口并行后约 6-9 小时完成 ✅ **全部完成**

---

## 窗口分配与执行顺序

### 窗口 1（Claude - 主窗口）

| 顺序 | 任务 | 文档 | 状态 |
|------|------|------|------|
| 1 | Test-04: 快照回滚 + 信号状态连续性 | `docs/tasks/S-integration-Test04.md` | ⏳ 待执行 |
| 2 | Test-03: EMA 缓存 + WebSocket 降级 | `docs/tasks/S-integration-Test03.md` | ⏳ 待执行 |

**启动命令**:
```bash
cd /Users/jiangwei/Documents/dingdingbot
# 读取任务文档
cat docs/tasks/S-integration-Test04.md
# 开始执行 Test-04
```

---

### 窗口 2（用户）

| 顺序 | 任务 | 文档 | 状态 |
|------|------|------|------|
| 1 | Test-05: 队列拥堵 + 信号状态完整性 | `docs/tasks/S-integration-Test05.md` | ⏳ 待执行 |
| 2 | Test-02: 队列背压 + WebSocket 降级 | `docs/tasks/S-integration-Test02.md` | ⏳ 待执行 |

**启动命令**:
```bash
cd /Users/jiangwei/Documents/dingdingbot
# 读取任务文档
cat docs/tasks/S-integration-Test05.md
# 开始执行 Test-05
```

---

### 窗口 3（用户）

| 顺序 | 任务 | 文档 | 状态 |
|------|------|------|------|
| 1 | Test-01: 配置快照 + WebSocket 降级 | `docs/tasks/S-integration-Test01.md` | ⏳ 待执行 |
| 2 | Test-06: 多策略 +EMA 缓存 + 状态跟踪 | `docs/tasks/S-integration-Test06.md` | ⏳ 待执行 |

**启动命令**:
```bash
cd /Users/jiangwei/Documents/dingdingbot
# 读取任务文档
cat docs/tasks/S-integration-Test01.md
# 开始执行 Test-01
```

---

## 已完成的准备工作

### ✅ 文档创建

| 文档 | 路径 | 状态 |
|------|------|------|
| 总览文档 | `docs/tasks/S-integration-overview.md` | ✅ 已完成 |
| Test-01 文档 | `docs/tasks/S-integration-Test01.md` | ✅ 已完成 |
| Test-02 文档 | `docs/tasks/S-integration-Test02.md` | ✅ 已完成 |
| Test-03 文档 | `docs/tasks/S-integration-Test03.md` | ✅ 已完成 |
| Test-04 文档 | `docs/tasks/S-integration-Test04.md` | ✅ 已完成 |
| Test-05 文档 | `docs/tasks/S-integration-Test05.md` | ✅ 已完成 |
| Test-06 文档 | `docs/tasks/S-integration-Test06.md` | ✅ 已完成 |

### ✅ 代码状态

```bash
# 当前 git 状态
git log --oneline -5
```

预期看到最近的提交：
- `ddd0b38` docs: 创建 v0.5.0-phase5 发布说明
- `2cd3a28` feat(S5-2): 实现信号状态跟踪系统
- `5df31ee` feat(S5-1): 实现 WebSocket 资产推送功能

---

## 执行流程

### 每个窗口的执行步骤

1. **读取任务文档**
   ```bash
   cat docs/tasks/S-integration-TestXX.md
   ```

2. **创建测试文件**
   ```bash
   # 按照文档步骤 1 创建测试框架
   ```

3. **实现测试逻辑**
   ```bash
   # 按照文档步骤 2-3 实现
   ```

4. **运行测试验证**
   ```bash
   pytest tests/integration/test_xxx.py -v
   ```

5. **提交代码**
   ```bash
   git add tests/integration/test_xxx.py
   git commit -m "test(integration): 添加 <测试场景> 集成测试 (#Test-XX)"
   ```

6. **更新总览文档状态**
   ```bash
   # 编辑 docs/tasks/S-integration-overview.md
   # 将对应任务状态改为 ✅ 完成
   ```

---

## 进度追踪（执行中更新）

### 实时状态表

| 任务 | 窗口 | 状态 | 完成时间 | 提交 hash |
|------|------|------|----------|-----------|
| Test-01 | 窗口 3 | ⏳ 待执行 | - | - |
| Test-02 | 窗口 2 | ⏳ 待执行 | - | - |
| Test-03 | 窗口 1 | ⏳ 待执行 | - | - |
| Test-04 | 窗口 1 | ⏳ 待执行 | - | - |
| Test-05 | 窗口 2 | ⏳ 待执行 | - | - |
| Test-06 | 窗口 3 | ⏳ 待执行 | - | - |

---

## 重启后快速恢复

### 窗口 1（Claude）
```bash
cd /Users/jiangwei/Documents/dingdingbot
# 读取计划
cat docs/planning/task_plan.md
cat docs/tasks/S-integration-Test04.md
# 开始执行 Test-04
```

### 窗口 2
```bash
cd /Users/jiangwei/Documents/dingdingbot
# 读取计划
cat docs/tasks/S-integration-Test05.md
# 开始执行 Test-05
```

### 窗口 3
```bash
cd /Users/jiangwei/Documents/dingdingbot
# 读取计划
cat docs/tasks/S-integration-Test01.md
# 开始执行 Test-01
```

---

## 依赖检查

### 环境检查（所有窗口执行）

```bash
# 确认代码版本
git log --oneline -3

# 确认测试依赖
pip list | grep -E "pytest|ccxt"

# 确认测试目录
ls tests/integration/
```

### API Key 配置

```yaml
# config/user.yaml
exchange:
  testnet: true
  api_key: "YOUR_BINANCE_TESTNET_API_KEY"
  api_secret: "YOUR_BINANCE_TESTNET_SECRET"
```

---

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| 测试文件冲突 | 每个测试独立文件，提交前 git pull |
| 测试网 API 限流 | 各窗口错开执行时间 |
| 环境不一致 | 所有窗口使用相同 config/user.yaml |
| 并发问题 | 使用确定性时间戳，多次运行验证 |

---

## 完成后清理

所有测试完成后：

1. 运行完整测试套件验证：
   ```bash
   pytest tests/integration/ -v
   ```

2. 合并所有提交（如需要）：
   ```bash
   git push origin main
   ```

3. 更新发布文档：
   ```bash
   # 更新 docs/releases/v0.6.0-phase4-5-integration.md
   ```

---

*本文档由 planning-with-files 技能维护，重启后读取此文件恢复上下文*
