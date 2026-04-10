# 诊断报告：前端三个错误根因分析

**报告编号**: DA-20260404-001
**优先级**: P0
**状态**: 已完成
**诊断时间**: 2026-04-04

---

## 问题描述

| 字段 | 内容 |
|------|------|
| 用户报告 | 前端出现三个错误：react-window TypeError + API 500 + API 404 |
| 影响范围 | Orders 页面无法渲染，策略参数页面无法使用 |
| 出现频率 | 必现 |
| 相关组件 | OrderChainTreeTable.tsx, api.ts, api.py |

### 错误详情

| 错误 | 信息 |
|------|------|
| 错误 1 | `react-window TypeError: Cannot convert undefined or null to object at de (react-window.js:471:52)` |
| 错误 2 | `GET /api/strategy/params 500 (Internal Server Error)` |
| 错误 3 | `GET /api/strategy/params/templates 404 (Not Found)` |

---

## 五维分析表

| 维度 | 排查发现 | 状态 |
|------|----------|------|
| 请求参数 | API 路径不匹配，前端请求的后端未定义 | ❌异常 |
| 响应参数 | 500 错误来自未初始化的 Repository | ❌异常 |
| 日志 | react-window 内部 Object.values 调用失败 | ❌异常 |
| 数据库 | ConfigEntryRepository 未初始化导致数据库连接失败 | ❌异常 |
| 代码 | react-window 2.x API 完全不兼容，props 名称错误 | ❌异常 |

---

## 排查过程

### Step 1: 初步假设

| 假设 | 可能性 | 验证方法 | 验证结果 |
|------|--------|----------|----------|
| react-window props 名称错误 | 高 | 检查 package.json 版本 + API 文档 | ✅ 确认 |
| Repository 未初始化 | 高 | 检查 fallback 创建逻辑 | ✅ 确认 |
| API 路径不匹配 | 高 | 对比前后端 API 定义 | ✅ 确认 |
| react-window 版本不兼容 | 高 | 检查 2.x API 变化 | ✅ 确认 |

### Step 2: 深入排查

**排查的文件**:
- `web-front/package.json:32` - react-window 版本 `^2.2.7`
- `web-front/src/components/v3/OrderChainTreeTable.tsx:369-377` - List 组件使用
- `src/interfaces/api.py:263-269` - `_get_config_entry_repo()` fallback
- `src/interfaces/api.py:2191` - `/api/strategies/templates` 端点定义
- `web-front/src/lib/api.ts:1643` - 前端调用 `/api/strategy/params/templates`

**发现的异常模式**:

#### 1. react-window 2.x API 不兼容

**当前代码** (OrderChainTreeTable.tsx:369-377):
```tsx
<List
  height={Math.min(flatData.length * 52, 600)}
  itemCount={flatData.length}      // ❌ 1.x API
  itemSize={52}                     // ❌ 1.x API
  data={flatData}                   // ❌ 1.x API
  ref={listRef}
>
  {Row}                             // ❌ 1.x API
</List>
```

**react-window 2.x API**:
| 1.x Prop | 2.x Prop | 说明 |
|----------|----------|------|
| `children={Row}` | `rowComponent={Row}` | 行渲染组件 |
| `itemCount` | `rowCount` | 行数量 |
| `itemSize` | `rowHeight` | 行高度 |
| `itemData`/`data` | `rowProps` | 传递给行组件的额外 props |
| - | `rowProps` 是 required prop | 2.x 强制要求 |

**根因**: react-window 2.x 完全重命名了 props，导致旧代码传递的 props 不被识别，内部 `Object.values(undefined)` 抛出 TypeError。

#### 2. ConfigEntryRepository fallback 未初始化

**当前代码** (api.py:263-269):
```python
def _get_config_entry_repo() -> Any:
    """Get config entry repository or create a new instance if not initialized."""
    if _config_entry_repo is None:
        # Fallback: create a new instance
        from src.infrastructure.config_entry_repository import ConfigEntryRepository
        return ConfigEntryRepository()  # ❌ 未初始化！
    return _config_entry_repo
```

**问题**: 
- `ConfigEntryRepository()` 创建实例后需要调用 `await initialize()` 才能正常工作
- fallback 直接返回未初始化的实例，`_db` 为 None
- 后续 `get_entries_by_prefix()` 调用会失败

#### 3. API 路径不匹配

**前端请求** (api.ts:1643):
```typescript
const res = await fetch('/api/strategy/params/templates', {  // ❌ 路径错误
```

**后端定义** (api.py:2191):
```python
@app.get("/api/strategies/templates")  # ✅ 正确路径
```

**路径对比**:
| 前端请求 | 后端定义 | 状态 |
|----------|----------|------|
| `/api/strategy/params/templates` | - | 404 |
| `/api/strategy/params` | `/api/strategy/params` | 500 (内部错误) |
| - | `/api/strategies/templates` | 未被调用 |

### Step 3: 根因定位（5 Why 分析）

#### 错误 1: react-window TypeError

```
Why 1: 为什么 TypeError: Cannot convert undefined or null to object？
  → react-window 内部调用 Object.values 处理一个 undefined 对象

Why 2: 为什么 react-window 收到 undefined 对象？
  → 当前代码传递的 props 名称不被 react-window 2.x 识别

Why 3: 为什么 props 名称不被识别？
  → react-window 2.x 完全重命名了 API props（itemCount→rowCount 等）

Why 4: 为什么使用了旧的 props 名称？
  → package.json 升级到 react-window ^2.2.7，但代码未同步更新

Why 5: 为什么升级版本后没有更新代码？
  → **根本原因**: 依赖升级后未检查 API 兼容性变更，缺少版本锁定策略
```

#### 错误 2: /api/strategy/params 500

```
Why 1: 为什么 API 返回 500 Internal Server Error？
  → ConfigEntryRepository 数据库操作失败

Why 2: 为什么数据库操作失败？
  → Repository 实例的 `_db` 属性为 None

Why 3: 为什么 _db 为 None？
  → Repository 实例未调用 `initialize()` 方法

Why 4: 为什么未调用 initialize()？
  → `_get_config_entry_repo()` 的 fallback 直接返回 `ConfigEntryRepository()` 实例

Why 5: 为什么 fallback 不初始化实例？
  → **根本原因**: fallback 函数是同步函数，无法调用异步的 `initialize()` 方法
```

#### 错误 3: /api/strategy/params/templates 404

```
Why 1: 为什么 API 返回 404 Not Found？
  → FastAPI 没有匹配的路由定义

Why 2: 为什么没有匹配的路由？
  → 后端定义的是 `/api/strategies/templates`，前端请求的是 `/api/strategy/params/templates`

Why 3: 为什么路径不一致？
  → 前后端开发时路径约定不统一

Why 4: 为什么约定不统一？
  → 前端假设存在 templates 子路由，但后端使用不同的路径结构

Why 5: 为什么前端假设错误？
  → **根本原因**: 前后端 API 契约缺少文档化，开发时没有统一的 API 规范文档
```

---

## 修复方案

### 方案 A [推荐] - 综合修复

#### A1: 修复 react-window 2.x 兼容性

**文件**: `web-front/src/components/v3/OrderChainTreeTable.tsx`
**位置**: 第 169-177 行（Row 组件定义）+ 第 369-377 行（List 使用）

**修改 Row 组件定义**（适配 react-window 2.x RowComponentProps）:
```tsx
// 修改前（第 169-174 行）
const Row: FC<{ index: number; style: React.CSSProperties; data: FlatOrderTreeNode[] }> = ({
  index,
  style,
  data,
}) => {

// 修改后
const Row: FC<{ index: number; style: React.CSSProperties; data?: FlatOrderTreeNode[] }> = ({
  index,
  style,
  data,
}) => {
  if (!data) return null;
```

**修改 List 使用**（第 369-377 行）:
```tsx
// 修改前
<List
  height={Math.min(flatData.length * 52, 600)}
  itemCount={flatData.length}
  itemSize={52}
  data={flatData}
  ref={listRef}
>
  {Row}
</List>

// 修改后（react-window 2.x API）
<List
  height={Math.min(flatData.length * 52, 600)}
  rowCount={flatData.length}
  rowHeight={52}
  rowProps={flatData}
  rowComponent={Row}
/>
```

**预估工作量**: 0.5h

#### A2: 修复 ConfigEntryRepository fallback 初始化

**文件**: `src/interfaces/api.py`
**位置**: 第 263-269 行

**修改方案**（抛出 503 而不是返回未初始化实例）:
```python
# 修改前
def _get_config_entry_repo() -> Any:
    if _config_entry_repo is None:
        from src.infrastructure.config_entry_repository import ConfigEntryRepository
        return ConfigEntryRepository()  # ❌ 未初始化
    return _config_entry_repo

# 修改后
def _get_config_entry_repo() -> Any:
    """Get config entry repository or raise error if not initialized."""
    if _config_entry_repo is None:
        raise HTTPException(status_code=503, detail="Config entry repository not initialized")
    return _config_entry_repo
```

**预估工作量**: 0.25h

#### A3: 修复 API 路径不匹配

**文件**: `web-front/src/lib/api.ts`
**位置**: 第 1643 行

**修改方案**（统一使用后端定义的路径）:
```typescript
// 修改前
const res = await fetch('/api/strategy/params/templates', {

// 修改后
const res = await fetch('/api/strategies/templates', {
```

**或添加后端端点**（如果需要独立的 strategy params templates）:
```python
# 文件: src/interfaces/api.py
# 新增端点
@app.get("/api/strategy/params/templates")
async def get_strategy_param_templates():
    """Get strategy parameter templates."""
    # 实现逻辑...
```

**预估工作量**: 0.25h

---

### 方案 B - 版本锁定

**锁定 react-window 版本**:
```json
// package.json
"react-window": "1.8.10"  // 移除 ^ 前缀，锁定到 1.x
```

**优点**: 无需修改代码，快速恢复
**缺点**: 错过 2.x 性能改进，未来可能需要升级

**预估工作量**: 0.1h

---

### 方案 C - 添加缺失的 API 端点

**为 `/api/strategy/params/templates` 添加后端端点**:

**文件**: `src/interfaces/api.py`
**位置**: 在 `/api/strategy/params` 附近添加

```python
@app.get("/api/strategy/params/templates")
async def get_strategy_params_templates():
    """Get strategy parameter templates."""
    # 可以复用现有的策略模板逻辑
    repo = _get_repository()
    strategies = await repo.get_all_custom_strategies()
    templates = [
        {"id": s["id"], "name": s["name"], "description": s["description"]}
        for s in strategies
    ]
    return {"templates": templates}
```

**优点**: 保持前端 API 路径一致性
**缺点**: 可能造成路由混乱（两套 templates API）

**预估工作量**: 0.5h

---

## 建议

### 立即修复

- **推荐方案**: 方案 A（综合修复）
- **理由**: 解决所有根本问题，确保系统稳定性

### 修复优先级

| 优先级 | 任务 | 工时 |
|--------|------|------|
| P0 | A1: react-window 2.x 兼容性 | 0.5h |
| P0 | A2: ConfigEntryRepository fallback | 0.25h |
| P0 | A3: API 路径不匹配 | 0.25h |
| **总计** | | **1h** |

### 后续优化（技术债）

- 添加 API 契约文档（OpenAPI/Swagger）
- 添加依赖升级兼容性检查流程
- 考虑使用 `npm shrinkwrap` 锁定依赖版本

### 预防措施

- 依赖升级时检查 CHANGELOG 和 API 变化
- 前后端 API 定义使用统一的文档化流程
- 添加单元测试覆盖 Repository fallback 场景

---

## 附录

### 相关文件

- `web-front/package.json` - react-window 版本定义
- `web-front/src/components/v3/OrderChainTreeTable.tsx` - react-window 使用
- `web-front/src/lib/api.ts` - API 调用路径
- `src/interfaces/api.py` - API 端点定义
- `src/infrastructure/config_entry_repository.py` - Repository 实现

### 验证方法

```bash
# 修复后验证 react-window
cd web-front && npm run dev

# 验证 API 端点
curl http://localhost:3000/api/strategy/params
curl http://localhost:3000/api/strategies/templates

# 运行单元测试
pytest tests/unit/test_config_entry_repository.py -v
```

---

*诊断完成时间: 2026-04-04*