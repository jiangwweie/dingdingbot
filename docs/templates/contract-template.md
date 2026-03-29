# {{功能名称}} - 接口契约表

> **创建日期**: {{YYYY-MM-DD}}
> **任务 ID**: {{Task ID}}
> ** Coordinator**: {{Name}}

---

## 1. API 端点定义

| 端点 | 方法 | 说明 | 负责人 |
|------|------|------|--------|
| `/api/{{endpoint}}` | {{GET\|POST\|PUT\|DELETE}} | {{功能说明}} | {{开发者}} |

---

## 2. 请求 Schema

### 2.1 请求头（Headers）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| Content-Type | string | 是 | application/json | - |
| Authorization | string | 否 | - | API Key（如需要） |

### 2.2 请求参数（Query Params）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| | | | | |

### 2.3 请求体（Request Body）

```python
# Pydantic Schema 定义
class {{RequestModelName}}(BaseModel):
    {{field_name}}: {{type}}  # {{description}}
    ...
```

| 字段 | 类型 | 必填 | 默认值 | 说明 | 前端对应字段 |
|------|------|------|--------|------|--------------|
| {{field_name}} | {{string\|number\|boolean\|object}} | 是/否 | - | {{说明}} | {{propName}} |

---

## 3. 响应 Schema

### 3.1 成功响应（200 OK）

```python
# Pydantic Schema 定义
class {{ResponseModelName}}(BaseModel):
    {{field_name}}: {{type}}  # {{description}}
    ...
```

| 字段 | 类型 | 必填 | 说明 | TypeScript 类型 |
|------|------|------|------|-----------------|
| {{field_name}} | {{string\|number\|boolean\|object}} | 是/否 | {{说明}} | {{type}} |

### 3.2 错误响应

| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| {{ERR_CODE}} | 400/401/403/404/500 | {{说明}} | {{toast\|redirect\|retry}} |

---

## 4. 前端组件 Props

### 4.1 组件树结构

```
{{ParentComponent}}
├── {{ChildComponent1}}
└── {{ChildComponent2}}
```

### 4.2 Props 定义

#### {{ComponentName}}

```typescript
interface {{ComponentName}}Props {
  {{propName}}: {{type}};  // {{description}}
  ...
}
```

| Prop | 类型 | 必填 | 默认值 | 说明 | 后端对应字段 |
|------|------|------|--------|------|--------------|
| {{propName}} | {{string\|number\|boolean}} | 是/否 | - | {{说明}} | {{api_field}} |

### 4.3 状态管理

| State | 类型 | 初始值 | 说明 |
|-------|------|--------|------|
| {{stateName}} | {{type}} | {{value}} | {{说明}} |

### 4.4 事件处理

| Event | 回调签名 | 触发时机 | 说明 |
|-------|----------|----------|------|
| on{{EventName}} | `() => void` | {{时机}} | {{说明}} |

---

## 5. 数据流图

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Frontend  │ ────▶│     API     │ ────▶│  Backend    │
│             │ ◀────│             │ ◀────│             │
└─────────────┘      └─────────────┘      └─────────────┘
```

---

## 6. 类型对齐检查

### 6.1 后端 Pydantic Schema

```python
# src/domain/models.py 或新建文件
class {{ModelName}}(BaseModel):
    {{field_name}}: {{type}}
```

### 6.2 前端 TypeScript 类型

```typescript
// web-front/src/types/{{file}}.ts
export interface {{InterfaceName}} {
  {{fieldName}}: {{type}};
}
```

### 6.3 对齐检查表

| 字段 | 后端类型 | 前端类型 | 是否一致 |
|------|----------|----------|----------|
| {{field}} | {{type}} | {{type}} | ✅ / ❌ |

---

## 7. 审查签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| Coordinator | | | |
| Backend Dev | | | |
| Frontend Dev | | | |
| QA Tester | | | |
| Code Reviewer | | | |

---

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | YYYY-MM-DD | 初始版本 | |

---

**使用说明**:
1. 复制此模板到 `docs/designs/<task-name>-contract.md`
2. 替换所有 `{{占位符}}` 为实际内容
3. 在阶段 1（契约设计）完成时填写
4. 作为后续开发、审查、测试的 SSOT
