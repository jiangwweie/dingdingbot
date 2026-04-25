# {{功能名称}} - 接口契约表

> **创建日期**: {{YYYY-MM-DD}}
> **任务 ID**: {{Task ID}}
> **Coordinator**: {{Name}}

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

| 字段 | 类型 | 必填 | 约束条件 | 默认值 | 说明 |
|------|------|------|----------|--------|------|
| | | | | | |

### 2.3 请求体（Request Body）

```python
# Pydantic Schema 定义
class {{RequestModelName}}(BaseModel):
    {{field_name}}: {{type}}  # {{description}}
    ...
```

| 字段 | 类型 | 必填等级 | 约束条件 | 默认值 | 说明 | 前端对应字段 |
|------|------|----------|----------|--------|------|--------------|
| {{field_name}} | {{string\|number\|boolean\|object}} | REQUIRED | `minLength: 1, maxLength: 50` | - | {{说明}} | {{propName}} |

**必填等级说明**:
| 等级 | 后端 | 前端 | 说明 |
|------|------|------|------|
| **REQUIRED** | ❌ 拒绝请求 | ❌ 禁用提交 | 业务 + 技术双重要求 |
| **CONDITIONAL** | ⚠️ 条件校验 | ⚠️ 动态显示/隐藏 | 依赖其他字段状态（见约束条件） |
| **OPTIONAL** | ✅ 可空 | ✅ 可选填 | 有合理默认值 |

**约束条件格式规范**:
```python
# String 类型
`minLength: N, maxLength: M, pattern: "regex"`
# Number 类型
`min: N, max: M, step: 0.01`
# Array 类型
`minItems: N, maxItems: M`
# Enum
`["VALUE1", "VALUE2", "VALUE3"]`
# Conditional 示例
`required_when: {field: "orderType", equals: "LIMIT"}`
```

---

## 3. 响应 Schema

### 3.1 成功响应（200 OK）

```python
# Pydantic Schema 定义
class {{ResponseModelName}}(BaseModel):
    {{field_name}}: {{type}}  # {{description}}
    ...
```

| 字段 | 类型 | 必填 | 约束条件 | 说明 | TypeScript 类型 |
|------|------|------|----------|------|-----------------|
| {{field_name}} | {{string\|number\|boolean\|object}} | 是/否 | `minLength: 1` | {{说明}} | {{type}} |

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
    # 约束验证器
    @field_validator('{{field_name}}')
    @classmethod
    def validate_{{field_name}}(cls, v):
        if len(v) < 1 or len(v) > 50:
            raise ValueError('{{field_name}} must be between 1 and 50 characters')
        return v
```

### 6.2 前端 TypeScript 类型

```typescript
// gemimi-web-front/src/types/{{file}}.ts
export interface {{InterfaceName}} {
  {{fieldName}}: {{type}};
}
```

### 6.3 对齐检查表

| 字段 | 后端类型 | 前端类型 | 约束一致 | 必填一致 |
|------|----------|----------|----------|----------|
| {{field}} | {{type}} | {{type}} | ✅ / ❌ | ✅ / ❌ |

### 6.4 前后端校验分工

| 校验规则 | 前端校验 | 后端校验 | 说明 |
|----------|----------|----------|------|
| 必填检查 | ✅ | ✅ | 前端禁用提交，后端返回 400 |
| 格式校验 | ✅ | ✅ | 前端即时反馈，后端最终验证 |
| 业务规则 | ❌ | ✅ | 如唯一性检查、权限验证 |
| 长度限制 | ✅ | ✅ | 前端 input maxLength，后端 validator |

---

## 7. 审查签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| Coordinator | | | |
| Backend Dev | | | |
| Frontend Dev | | | |
| QA Tester | | | |
| Code Reviewer | | | |

**审查检查清单**:
- [ ] 所有字段的必填等级已明确（REQUIRED/CONDITIONAL/OPTIONAL）
- [ ] 所有字段的约束条件已定义（长度/范围/格式）
- [ ] CONDITIONAL 字段的触发条件已说明
- [ ] 前后端校验分工已明确
- [ ] 错误响应格式已定义

---

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | YYYY-MM-DD | 初始版本 | |
| v1.1 | YYYY-MM-DD | 增加字段约束定义规范 | |

---

**使用说明**:
1. 复制此模板到 `docs/designs/<task-name>-contract.md`
2. 替换所有 `{{占位符}}` 为实际内容
3. **必填等级和约束条件必须填写**，不能留空
4. 在阶段 1（契约设计）完成时填写
5. 作为后续开发、审查、测试的 SSOT

**字段约束填写示例**:

| 字段 | 类型 | 必填等级 | 约束条件 | 说明 |
|------|------|----------|----------|------|
| symbol | string | REQUIRED | `pattern: "^[A-Z]+/[A-Z]+:[A-Z]+$"` | 交易对，如 BTC/USDT:USDT |
| quantity | number | REQUIRED | `min: 0.001, max: 1000000, step: 0.001` | 下单数量 |
| orderType | string | REQUIRED | `["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"]` | 订单类型 |
| limitPrice | number | CONDITIONAL | `min: 0, required_when: {field: "orderType", equals: "LIMIT"}` | 限价单价格 |
| remark | string | OPTIONAL | `maxLength: 200, default: ""` | 备注信息 |
