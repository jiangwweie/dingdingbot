# YAML 去味清单

**审查日期**: 2026-04-25
**硬约束**: YAML 已彻底废弃，不再作为启动配置来源

---

## 执行摘要

**结论**: ✅ **YAML 已不参与启动流程**，但存在残留代码、注释和文档需要清理。

**残留分类**:
- 启动链路残留: **0 个**（已完全移除）
- 接口残留: **3 个**（导入/导出工具，不影响启动）
- 文档残留: **40+ 个**（误导维护者）
- 注释残留: **4 个**（误导维护者）

---

## 1. 启动链路残留

**结论**: ✅ **无启动依赖**

### 证据

```python
# src/application/config_manager.py:908
"""Build default core configuration (hardcoded defaults).
Used when DB is not yet initialized or unavailable.
No YAML file fallback — DB or defaults only.
"""
```

```python
# src/main.py:201-202
config_manager = load_all_configs()
await config_manager.initialize_from_db()  # ✅ 从 DB 初始化
```

### 残留代码（不影响启动）

| 文件路径 | 行号 | 残留内容 | 残留类型 | 是否影响 Sim-1 | 建议动作 |
|---------|------|----------|----------|----------------|----------|
| `src/application/config_manager.py` | 1760 | `import_from_yaml()` 方法 | 启动链路 | ❌ 不影响 | 保留（备份工具） |
| `src/application/config_manager.py` | 1876 | `export_to_yaml()` 方法 | 启动链路 | ❌ 不影响 | 保留（备份工具） |
| `src/application/config_manager.py` | 2027 | `load_all_configs()` 注释 | 启动链路 | ❌ 不影响 | **修改文案** |

**说明**: `import_from_yaml()` 和 `export_to_yaml()` 是手动备份工具，不影响启动。

---

## 2. 接口残留

**结论**: ⚠️ **存在 YAML 导入/导出接口（非启动必需）**

| 文件路径 | 行号 | 残留内容 | 残留类型 | 是否影响 Sim-1 | 建议动作 |
|---------|------|----------|----------|----------------|----------|
| `src/interfaces/api.py` | 1419 | YAML 导入接口 | 接口 | ❌ 不影响 | 保留（备份工具） |
| `src/interfaces/api.py` | 1476 | YAML 导出接口 | 接口 | ❌ 不影响 | 保留（备份工具） |
| `src/interfaces/api_v1_config.py` | 1682 | YAML 导入接口 | 接口 | ❌ 不影响 | 保留（备份工具） |
| `src/interfaces/api_profile_endpoints.py` | 349 | YAML 导入接口 | 接口 | ❌ 不影响 | 保留（备份工具） |

**说明**: 这些接口用于手动导入/导出配置备份，不影响 Sim-1 启动。

---

## 3. 文档残留

**结论**: ❌ **大量过时文档引用 YAML**

### 高优先级文档（误导性强）

| 文件路径 | 行号 | 残留内容 | 是否影响 Sim-1 | 建议动作 |
|---------|------|----------|----------------|----------|
| `docs/tasks/archive/S2-5-ATR 过滤器实现.md` | 193 | 引用 `config/core.yaml` | ❌ 不影响 | **添加废弃说明** |
| `docs/tasks/archive/S4-2-异步 IO 队列优化.md` | 45 | 引用 `config/core.yaml` | ❌ 不影响 | **添加废弃说明** |
| `docs/tasks/archive/S6-1-冷却缓存优化.md` | 38 | 引用 `config/core.yaml` | ❌ 不影响 | **添加废弃说明** |
| `docs/tasks/archive/2026-03-25-子任务B-*.md` | 6 | 引用 `user.yaml` | ❌ 不影响 | **添加废弃说明** |
| `docs/diagnostic-reports/archive/2026-03-29-*.md` | 129 | 引用 `config/user.yaml` | ❌ 不影响 | **添加废弃说明** |

### 中优先级文档（误导性中等）

| 文件路径 | 行号 | 残留内容 | 是否影响 Sim-1 | 建议动作 |
|---------|------|----------|----------------|----------|
| `docs/designs/archive/handoff-skills/*.md` | 151 | 引用 `config/user.yaml` | ❌ 不影响 | **添加废弃说明** |
| `docs/archive/2026-04-14/v1.0.0-*.md` | 197 | 引用 `config/core.yaml` | ❌ 不影响 | **添加废弃说明** |
| `docs/archive/2026-04-14/v1.0.0-*.md` | 387 | 文件树包含 `core.yaml` | ❌ 不影响 | **添加废弃说明** |

### 低优先级文档（误导性弱）

| 文件路径 | 行号 | 残留内容 | 是否影响 Sim-1 | 建议动作 |
|---------|------|----------|----------------|----------|
| `docs/adr/2026-04-14-*.md` | 656 | 正确描述 "没有 YAML 配置文件" | ❌ 不影响 | 保留 |

**建议动作**:
- **添加废弃说明**: 在文档顶部添加 `> **注意**: YAML 配置文件已废弃，当前系统使用数据库驱动配置。`
- **保留**: 内容正确或历史价值高，无需修改

---

## 4. 注释残留

**结论**: ⚠️ **存在误导性注释**

| 文件路径 | 行号 | 残留内容 | 是否影响 Sim-1 | 建议动作 |
|---------|------|----------|----------------|----------|
| `src/application/config_manager.py` | 217 | "Backward compatibility with YAML files" | ❌ 不影响 | **修改为 "YAML import/export utilities"** |
| `src/application/config_manager.py` | 254 | "config_dir: ... for backward compatibility" | ❌ 不影响 | **修改为 "legacy parameter (unused)"** |
| `src/application/config_manager.py` | 265 | "# Config directory (for YAML backward compatibility)" | ❌ 不影响 | **删除注释** |
| `src/application/config_manager.py` | 2015 | "config_dir: ... for backward compatibility" | ❌ 不影响 | **修改为 "legacy parameter (unused)"** |
| `src/application/signal_pipeline.py` | 88 | "# Queue configuration from core.yaml (S4-2)" | ❌ 不影响 | **删除注释** |
| `src/infrastructure/notifier.py` | 618 | "channels_config: List of channel configs from user.yaml" | ❌ 不影响 | **修改为 "from DB config"** |

---

## 5. 建议修复优先级

### P3 - 文档和注释清理（不影响功能）

**优先级**: 低（可后续清理）

**修复清单**:

1. **修改误导性注释**（预计 10 分钟）
   - `src/application/config_manager.py:217` → "YAML import/export utilities"
   - `src/application/config_manager.py:254` → "legacy parameter (unused)"
   - `src/application/config_manager.py:265` → 删除注释
   - `src/application/config_manager.py:2015` → "legacy parameter (unused)"
   - `src/application/signal_pipeline.py:88` → 删除注释
   - `src/infrastructure/notifier.py:618` → "from DB config"

2. **添加文档废弃说明**（预计 30 分钟）
   - 在 `docs/tasks/archive/*.md` 顶部添加废弃说明
   - 在 `docs/diagnostic-reports/archive/*.md` 顶部添加废弃说明
   - 在 `docs/designs/archive/*.md` 顶部添加废弃说明

3. **更新 CLAUDE.md**（预计 5 分钟）
   - 添加 "YAML 配置文件已废弃" 说明
   - 明确 "数据库驱动配置" 架构

---

## 6. 验证 YAML 已废弃

### 启动流程验证

```python
# src/main.py:201-202
config_manager = load_all_configs()
await config_manager.initialize_from_db()  # ✅ 从 DB 初始化
```

### 配置加载验证

```python
# src/application/config_manager.py:908
"""Build default core configuration (hardcoded defaults).
Used when DB is not yet initialized or unavailable.
No YAML file fallback — DB or defaults only.
"""
```

### Docker 构建验证

```dockerfile
# docker/Dockerfile.backend:27
COPY config/ ./config/  # ✅ 复制参考文件，不影响启动
```

**说明**: `config/` 目录包含 `.reference`/`.example`/`.bak` 文件，Docker 构建时复制这些文件不会导致失败，但也不参与启动流程。

---

## 7. 总结

### 关键结论

1. ✅ **YAML 已不参与启动流程**（硬约束已满足）
2. ✅ **Sim-1 部署不需要 YAML 文件**
3. ⚠️ **存在残留代码和注释**（不影响功能，但误导维护者）
4. ❌ **文档大量引用 YAML**（需要添加废弃说明）

### 修复建议

**立即修复**（阻塞 Sim-1）:
- 无（YAML 不阻塞部署）

**后续清理**（P3 优先级）:
- 修改误导性注释（6 处）
- 添加文档废弃说明（40+ 处）
- 更新 CLAUDE.md

---

**审查人**: Claude Code (Sonnet 4.6)
**文档版本**: v1.0
