# 架构决策记录：前端三错误修复方案

**ADR 编号**: ADR-20260404-001
**决策日期**: 2026-04-04
**决策状态**: Accepted
**决策者**: Architect
**参考文档**: DA-20260404-001

---

## 背景

前端出现三个错误：
1. react-window TypeError（API 不兼容）
2. `/api/strategy/params` 500 错误（Repository 未初始化）
3. `/api/strategy/params/templates` 404 错误（路由不匹配）

诊断报告已确认根因，需要选择修复方案。

---

## 决策

**采用方案 A（综合修复）**

### 具体决策

| 问题 | 决策内容 | 理由 |
|------|----------|------|
| react-window | 升级代码适配 2.x API | 保留性能改进，避免技术债 |
| Repository fallback | 抛出 503 而非返回未初始化实例 | 与其他 Repository 处理方式一致 |
| API 路径 | 前端统一使用后端已定义的路径 | 避免路由冗余 |

---

## 技术契约

### 契约 1: react-window 2.x API 适配

**文件**: `gemimi-web-front/src/components/v3/OrderChainTreeTable.tsx`

**修改内容**:

```tsx
// Row 组件定义（第 169-177 行）
// 修改前
const Row: FC<{ index: number; style: React.CSSProperties; data: FlatOrderTreeNode[] }> = ({
  index,
  style,
  data,
}) => { ... }

// 修改后（适配 2.x RowComponentProps）
// 注意：2.x 的 rowProps 会被展开传递给 Row 组件
// Row 接收 (index, style) + rowProps 中的所有属性
// 由于 rowProps={flatData} 是数组，需要特殊处理

// 方案：使用 rowProps 传递单个数据项
// 在 List 外层遍历，或改变数据传递方式
```

**重要发现**: react-window 2.x 的 `rowProps` 机制与 1.x 的 `itemData` 不同：
- 1.x: `itemData` 整体传递给 Row，Row 通过 `data[index]` 获取项
- 2.x: `rowProps` 直接展开传递给 Row，Row 不自动接收数组

**正确适配方案**:
```tsx
// 方案：将 flatData 作为 rowProps 传递，Row 内部通过 index 访问
const Row: FC<{ index: number; style: React.CSSProperties; items?: FlatOrderTreeNode[] }> = ({
  index,
  style,
  items,
}) => {
  if (!items || !items[index]) return null;
  const item = items[index];
  // ... 渲染逻辑
};

// List 使用
<List
  height={Math.min(flatData.length * 52, 600)}
  rowCount={flatData.length}
  rowHeight={52}
  rowProps={{ items: flatData }}  // 包装为对象
  rowComponent={Row}
/>
```

---

### 契约 2: Repository fallback 统一处理

**文件**: `src/interfaces/api.py`

**修改位置**: 第 263-269 行

**修改内容**:
```python
def _get_config_entry_repo() -> Any:
    """Get config entry repository or raise error if not initialized."""
    if _config_entry_repo is None:
        raise HTTPException(
            status_code=503,
            detail="Config entry repository not initialized. Please restart the server."
        )
    return _config_entry_repo
```

**一致性检查**: 与 `_get_config_manager()` (第 237-241 行) 保持一致模式。

---

### 奉约 3: API 路径统一

**决策**: 前端修改为使用后端已定义的路径

**修改文件**: `gemimi-web-front/src/lib/api.ts`

**路径映射**:
| 前端当前路径 | 修改为后端路径 | 说明 |
|--------------|----------------|------|
| `/api/strategy/params/templates` | `/api/strategies/templates` | 策略模板列表 |
| `/api/strategy/params/templates/{id}/load` | `/api/strategies/{id}` | 加载策略详情 |

**注意**: 需检查前端是否有其他使用这些路径的地方。

---

## 影响评估

### 影响范围

| 影响项 | 评估 |
|--------|------|
| Orders 页面 | 修复后正常渲染 |
| 策略参数页面 | API 正常响应 |
| 其他 react-window 使用 | 需检查是否有类似问题 |
| Repository 模式 | 统一 fallback 行为 |

### 检查清单

- [ ] 是否有其他组件使用 react-window？
- [ ] 是否有其他 API 路径不匹配？
- [ ] Repository 单元测试是否覆盖 fallback 场景？

---

## 实施计划

### 并行簇识别

```
任务依赖图:
┌─────────────────────────────────────────────────────────┐
│ 前端修复 (F1) ──────────────────────────────────────────┤
│   - react-window API 适配                               │
│   - API 路径修改                                         │
│                                                         │
│ 后端修复 (B1) ──────────────────────────────────────────┤
│   - Repository fallback 修改                            │
│                                                         │
│ 测试验证 (T1) ──────────────────────────────────────────┤
│   - 依赖: F1 + B1                                        │
└─────────────────────────────────────────────────────────┘

可并行执行: F1 + B1
需串行执行: T1 依赖 F1+B1 完成
```

### 任务分配

| 任务 ID | 任务内容 | 角色 | 预计工时 | 依赖 |
|---------|----------|------|----------|------|
| F1-1 | react-window API 适配 | frontend | 0.5h | - |
| F1-2 | API 路径修改 | frontend | 0.25h | - |
| B1-1 | Repository fallback 修改 | backend | 0.25h | - |
| T1-1 | 单元测试验证 | qa | 0.5h | F1+B1 |
| T1-2 | E2E 测试验证 | qa | 0.5h | F1+B1 |

---

## 验收标准

### 功能验收

- [ ] Orders 页面正常渲染（无 TypeError）
- [ ] `/api/strategy/params` 返回 200 或正确的错误码
- [ ] `/api/strategies/templates` 返回 200

### 测试验收

- [ ] 前端 E2E 测试通过
- [ ] 后端单元测试通过

---

## 后续行动

### 技术债

1. **API 契约文档化**: 建议使用 OpenAPI 规范记录所有 API 路径
2. **依赖升级流程**: 建立 CHANGELOG 检查机制
3. **版本锁定策略**: 考虑使用 `npm shrinkwrap` 或 `pnpm`

---

*决策时间: 2026-04-04*