# 配置 Profile 管理 - 会话交接文档

**创建时间**: 2026-04-03  
**状态**: 📋 需求/架构完成，待开发执行  

---

## 一、已完成工作

### 1.1 产品需求文档 ✅
- **文件**: `docs/products/config-profile-management-prd.md`
- **内容**: 
  - 功能需求（列表/创建/切换/删除/导出/导入/对比）
  - 用户故事和验收标准
  - 原型图（列表页/创建对话框/切换预览/删除确认/导入对话框）
  - MVP 范围定义（第一阶段 6h）

### 1.2 技术架构设计 ✅
- **核心原则**: SQLite 为主，YAML 为辅
- **数据表设计**:
  ```sql
  -- 新增 config_profiles 表
  CREATE TABLE config_profiles (
      name TEXT PRIMARY KEY,
      description TEXT,
      is_active BOOLEAN DEFAULT FALSE,
      created_at TEXT,
      updated_at TEXT,
      created_from TEXT
  );
  
  -- 扩展 config_entries 表
  ALTER TABLE config_entries ADD COLUMN profile_name TEXT DEFAULT 'default';
  CREATE UNIQUE INDEX idx_config_profile_key ON config_entries(profile_name, category, key);
  ```

### 1.3 核心概念确认 ✅
- **Profile = 配置集合**: 一套完整的策略 + 风控 + 交易所配置组合
- **一键切换**: 数据库事务更新 `is_active` 字段，触发热重载
- **使用场景**: 保守/激进切换、时段配置、策略试验

---

## 二、待执行任务（MVP 范围）

### 第一阶段（6h）

| 任务 ID | 角色 | 任务 | 工时 | 状态 |
|---------|------|------|------|------|
| **B1** | 后端 | 数据库迁移脚本 | 1.5h | ☐ 待启动 |
| **B2** | 后端 | Repository 层实现 | 1.5h | ☐ |
| **B3** | 后端 | Service 层实现 | 1.5h | ☐ |
| **B4** | 后端 | API 端点实现 | 1.5h | ☐ |
| **F1** | 前端 | 类型定义 | 0.5h | ☐ |
| **F2** | 前端 | API 函数封装 | 0.5h | ☐ |
| **F3** | 前端 | Profile 管理页面 | 1.5h | ☐ |
| **F4** | 前端 | 对话框组件（3 个） | 1.5h | ☐ |
| **T1** | 测试 | Repository 单元测试 | 1h | ☐ |
| **T2** | 测试 | Service 单元测试 | 1h | ☐ |
| **T3** | 测试 | API 集成测试 | 1.5h | ☐ |

### 第二阶段（5h，可选延后）
- 复制 Profile
- 重命名 Profile
- 导出 YAML
- 导入 YAML

### 第三阶段（11h，可选延后）
- Profile 对比
- 定时切换
- 使用统计

---

## 三、其他待办 P1 任务

| 任务 ID | 任务名称 | 说明 | 工时 |
|---------|----------|------|------|
| **#3** | Orders 空状态处理 | 无订单时友好提示 | 0.5h |
| **#4** | 订单链 E2E 测试 | `tests/e2e/test_order_chain_e2e.py` | 4h |
| **#5** | 策略参数前端 E2E | 策略参数完整测试 | 2h |

---

## 四、技术实现要点

### 4.1 后端关键点

**Repository 层** (`src/infrastructure/config_profile_repository.py`):
```python
class ConfigProfileRepository:
    async def list_profiles() -> List[ProfileInfo]
    async def create_profile(name, description, copy_from)
    async def activate_profile(name) -> None  # 事务操作
    async def delete_profile(name) -> None
    async def copy_profile_configs(from_name, to_name)
```

**Service 层** (`src/application/config_profile_service.py`):
```python
class ConfigProfileService:
    async def list_profiles() -> List[ProfileInfo]
    async def create_profile(...) -> ProfileInfo
    async def switch_profile(name) -> ProfileDiff  # 返回差异预览
    async def delete_profile(name) -> bool
    async def export_yaml(name) -> str
    async def import_yaml(yaml_content, mode) -> ProfileInfo
```

**API 端点** (`src/interfaces/api.py`):
```python
GET  /api/config/profiles              # 列表
POST /api/config/profiles              # 创建
DELETE /api/config/profiles/{name}     # 删除
POST /api/config/profiles/{name}/activate  # 切换
GET  /api/config/profiles/{name}/export     # 导出
POST /api/config/profiles/import            # 导入
GET  /api/config/profiles/compare           # 对比
```

### 4.2 前端关键点

**类型定义** (`web-front/src/types/config-profile.ts`):
```typescript
interface ConfigProfile {
  name: string;
  description: string;
  is_active: boolean;
  config_count: number;
  created_at: string;
  updated_at: string;
}

interface ProfileDiff {
  from_profile: string;
  to_profile: string;
  diff: Record<string, Record<string, {old: string, new: string}>>;
  total_changes: number;
}
```

**核心组件**:
- `ConfigProfiles.tsx` - 主页面
- `CreateProfileModal.tsx` - 创建对话框
- `SwitchPreviewModal.tsx` - 切换预览
- `DeleteConfirmModal.tsx` - 删除确认

---

## 五、相关文件索引

### 设计文档
- `docs/products/config-profile-management-prd.md` - PRD（已完成）
- `docs/products/config-management-summary.md` - 配置管理总结
- `docs/designs/config-management-versioned-snapshots.md` - 快照设计

### 代码文件（现有）
- `src/application/config_manager.py` - ConfigManager
- `src/infrastructure/config_snapshot_repository.py` - 快照 Repository
- `src/infrastructure/config_entry_repository.py` - 配置项 Repository
- `src/interfaces/api.py` - API 端点

### 需要创建的文件
- `src/infrastructure/config_profile_repository.py` ⭐
- `src/application/config_profile_service.py` ⭐
- `scripts/migrate_to_profiles.py` ⭐
- `web-front/src/types/config-profile.ts` ⭐
- `web-front/src/pages/ConfigProfiles.tsx` ⭐
- `web-front/src/components/profiles/*.tsx` ⭐

---

## 六、执行建议

### 推荐顺序
1. **B1 数据库迁移** - 先决条件，1.5h
2. **B2/B3 Repository + Service** - 后端核心，3h
3. **F1/F2 前端类型+API** - 前端基础，1h（可与 B2/B3 并行）
4. **B4 API 端点** - 后端接口，1.5h
5. **F3/F4 前端 UI** - 前端实现，3h（可与 T1/T2 并行）
6. **T1/T2/T3 测试** - 验证，3.5h

### 并行策略
```
时间线:
│
├─ B1 迁移脚本 (1.5h)
│  ▼
├─ B2 Repository (1.5h) ──┬── F1/F2 前端基础 (1h)
├─ B3 Service (1.5h) ─────┤
│                         ├── B4 API 端点 (1.5h)
│                         │  ▼
│                         ├── F3/F4 前端 UI (3h)
│                         │  ▼
│                         └── T1/T2/T3 测试 (3.5h)
```

---

## 七、注意事项

### 数据迁移
- 迁移脚本需备份原数据库
- 迁移后验证现有配置归属到 default Profile
- 提供回滚脚本

### 向后兼容
- default Profile 必须存在且不可删除
- 现有 API（配置导出/导入）需兼容 Profile 功能
- ConfigManager 需支持按 Profile 读取配置

### 边界条件
- 禁止删除 default Profile
- 禁止删除当前激活的 Profile
- 名称唯一性验证（1-32 字符）
- 切换前必须预览差异

---

## 八、Git 提交建议

```bash
# 后端
git commit -m "feat(profile): 数据库迁移脚本和 Profile 表创建"
git commit -m "feat(profile): Repository 层实现"
git commit -m "feat(profile): Service 层实现"
git commit -m "feat(profile): API 端点实现"

# 前端
git commit -m "feat(profile): 类型定义和 API 函数封装"
git commit -m "feat(profile): Profile 管理页面"
git commit -m "feat(profile): 对话框组件（创建/切换/删除）"

# 测试
git commit -m "test(profile): Repository 和 Service 单元测试"
git commit -m "test(profile): API 集成测试"

# 文档
git commit -m "docs: 配置 Profile 管理 PRD"
```

---

**交接时间**: 2026-04-03  
**交接人**: AI Builder  
**备注**: 重启后继续执行 Profile 功能开发，按上述顺序推进
