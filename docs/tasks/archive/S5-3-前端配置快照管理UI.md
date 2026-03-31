# S5-3: 前端配置快照管理 UI

**任务负责人**: Claude
**执行日期**: 2026-03-27
**实际工时**: ~2 小时
**优先级**: 低
**依赖**: S4-1 配置快照版本化（后端 API 已就绪）

---

## 目标

实现配置快照管理前端界面，让用户可以通过 UI：
1. 查看历史快照列表
2. 创建新的配置快照
3. 回滚到任意历史版本
4. 删除不需要的快照

---

## 交付物

### 新增文件
| 文件 | 说明 |
|------|------|
| `web-front/src/pages/Snapshots.tsx` | 快照管理主页面 |

### 修改文件
| 文件 | 修改内容 |
|------|----------|
| `web-front/src/lib/api.ts` | 新增快照类型定义和 4 个 API 函数 |
| `web-front/src/App.tsx` | 新增 `/snapshots` 路由 |
| `web-front/src/components/Layout.tsx` | 新增导航入口（配置快照） |

---

## 实现步骤

### 步骤 1: 定义类型和 API 函数

**文件**: `web-front/src/lib/api.ts`

```typescript
// 类型定义
export interface ConfigSnapshot {
  id: number;
  version: string;
  config_json: string;
  description: string;
  created_at: string;
  created_by: string;
  is_active: boolean;
}

export interface CreateSnapshotRequest {
  version: string;
  description: string;
  config_json?: string;
}

// API 函数
export async function fetchSnapshots()
export async function createSnapshot(payload: CreateSnapshotRequest)
export async function deleteSnapshot(id: number)
export async function applySnapshot(id: number)
```

### 步骤 2: 创建页面组件

**文件**: `web-front/src/pages/Snapshots.tsx`

**功能**:
- 使用 SWR 自动刷新数据
- 创建快照对话框（含表单验证）
- 表格展示快照列表
- 回滚/删除操作（带二次确认）
- 活跃状态视觉标识
- 空状态提示

### 步骤 3: 添加路由

**文件**: `web-front/src/App.tsx`

```tsx
<Route path="snapshots" element={<Snapshots />} />
```

### 步骤 4: 添加导航

**文件**: `web-front/src/components/Layout.tsx`

```tsx
{ to: '/snapshots', icon: Save, label: '配置快照' }
```

### 步骤 5: 修复 Bug

**问题**: 创建快照时后端要求 `config_json` 字段，但前端未传递

**修复**: 在 `handleCreate` 函数中先获取当前配置：
```typescript
const res = await fetch('/api/config');
const currentConfig = await res.json();
await createSnapshot({
  version: newVersion,
  description: newDescription,
  config_json: JSON.stringify(currentConfig),
});
```

---

## 测试验证

### API 测试
```bash
# 创建快照
curl -X POST http://localhost:8000/api/config/snapshots \
  -H "Content-Type: application/json" \
  -d '{"version":"v1.0.0","description":"测试","config_json":"{}"}'

# 查询列表
curl http://localhost:8000/api/config/snapshots

# 激活快照
curl -X POST http://localhost:8000/api/config/snapshots/1/activate

# 删除快照
curl -X DELETE http://localhost:8000/api/config/snapshots/1
```

### 前端测试
- ✅ 页面加载：http://localhost:3000/snapshots
- ✅ 创建快照对话框
- ✅ 回滚确认对话框
- ✅ 删除确认对话框
- ✅ 空状态展示
- ✅ 列表数据展示

---

## Git 提交

```bash
git add web-front/src/lib/api.ts
git add web-front/src/pages/Snapshots.tsx
git add web-front/src/App.tsx
git add web-front/src/components/Layout.tsx
git commit -m "feat(S5-3): 前端配置快照管理 UI"
git push origin main
```

**提交哈希**: `2fad026`
**提交时间**: 2026-03-27 16:30+

---

## 遇到的问题

| 问题 | 解决方案 |
|------|----------|
| 后端 API 要求 `config_json` 字段 | 在创建快照前先调用 `/api/config` 获取当前配置 |

---

## 验收状态

- [x] 可查看历史快照列表
- [x] 可创建新快照
- [x] 可回滚到任意历史版本
- [x] 可删除历史快照
- [x] 活跃快照有视觉标识
- [x] 回滚前有二次确认
- [x] 删除前有二次确认
- [x] 错误处理完善
- [x] 代码已提交推送

---

*文档创建：2026-03-27 - S5-3 任务完成归档*
