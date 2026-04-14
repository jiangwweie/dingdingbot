# SystemSettings 页面新增风控配置表单 — 实施方案

> 日期: 2026-04-13
> 状态: 待评审
> 优先级: P1

---

## 一、前端类型确认

### 1.1 `RiskConfig` 类型对齐情况

`web-front/src/api/config.ts:96-107` 中已定义的 `RiskConfig` 与后端 `RiskConfigResponse`（`src/interfaces/api_v1_config.py:123-134`）**字段完全对齐**，无需补充：

| 字段 | 后端 `RiskConfigResponse` | 前端 `RiskConfig` | 状态 |
|------|--------------------------|-------------------|------|
| id | str | string | OK |
| max_loss_percent | Decimal | number | OK |
| max_leverage | int | number | OK |
| max_total_exposure | Optional[Decimal] | number \| null | OK |
| daily_max_trades | Optional[int] | number \| null | OK |
| daily_max_loss | Optional[Decimal] | number \| null | OK |
| max_position_hold_time | Optional[int] | number \| null | OK |
| cooldown_minutes | int | number | OK |
| updated_at | str | string | OK |
| version | int | number | OK |

### 1.2 需要新增的类型

需新增 `RiskConfigFormValues` 接口，用于前端表单值类型。与 `RiskConfig` 的区别在于：表单不携带 `id`、`updated_at`、`version` 等只读字段。

```typescript
interface RiskConfigFormValues {
  max_loss_percent: number;           // 0.001 ~ 1 (0.1% ~ 100%)
  max_leverage: number;               // 1 ~ 125
  max_total_exposure: number | null;  // 0 ~ 1 (0% ~ 100%)，可选
  daily_max_trades: number | null;    // 1+，可选
  daily_max_loss: number | null;      // 0+，可选
  max_position_hold_time: number | null; // 1+ (分钟)，可选
  cooldown_minutes: number;           // 0+ (分钟)
}
```

**需要同时新增 `RiskConfigUpdateRequest` 接口**（提交用，所有字段可选），用于 PUT 请求体，与后端 `RiskConfigUpdateRequest`（`api_v1_config.py:137-145`）对齐：

```typescript
export interface RiskConfigUpdateRequest {
  max_loss_percent?: number;
  max_leverage?: number;
  max_total_exposure?: number | null;
  daily_max_trades?: number | null;
  daily_max_loss?: number | null;
  max_position_hold_time?: number | null;
  cooldown_minutes?: number;
}
```

---

## 二、表单字段设计

### 2.1 字段分组

风控配置 Card 按业务语义分为 3 个 Divider 区块：

| 区块 | 字段 | 验证规则 | 单位/格式 |
|------|------|---------|-----------|
| **仓位风控** | max_loss_percent | required, min: 0.001, max: 1 | 百分比 (输入 0.01 = 1%) |
| | max_leverage | required, min: 1, max: 125 | 倍数 |
| | max_total_exposure | optional, min: 0, max: 1 | 百分比 (null = 不限制) |
| **日频风控** | daily_max_trades | optional, min: 1 | 笔数 (null = 不限制) |
| | daily_max_loss | optional, min: 0 | 金额/百分比 (null = 不限制) |
| **时间与冷却** | max_position_hold_time | optional, min: 1 | 分钟 (null = 不限制) |
| | cooldown_minutes | required, min: 0 | 分钟 |

### 2.2 默认值

参考后端默认值（`api_v1_config.py:723-730`）：

```typescript
const DEFAULT_RISK_CONFIG: RiskConfigFormValues = {
  max_loss_percent: 0.01,         // 1%
  max_leverage: 10,               // 10x
  max_total_exposure: null,       // 不限制
  daily_max_trades: null,         // 不限制
  daily_max_loss: null,           // 不限制
  max_position_hold_time: null,   // 不限制
  cooldown_minutes: 5,            // 5 分钟
};
```

### 2.3 `max_loss_percent` 的用户体验优化

后端存储的是 Decimal 小数（0.01 = 1%），但用户更习惯看百分比数字。采用与现有 `signal_cooldown_seconds` 字段相同的 `formatter/parser` 模式：

- 输入显示: `1%`（实际值为 0.01）
- formatter: `(value) => `${(value * 100).toFixed(1)}%``
- parser: `(value) => Number(value?.replace('%', '')) / 100`

---

## 三、加载与保存策略

### 3.1 加载逻辑

页面打开时，在现有的 `loadConfig()` 中**追加** `configApi.getRiskConfig()` 调用。两个加载请求**并行执行**（`Promise.all`），避免串行延迟。

```typescript
// 在现有 loadConfig 中追加 riskConfig 加载
const [systemResponse, riskResponse] = await Promise.all([
  configApi.getSystemConfig(),
  configApi.getRiskConfig(),
]);
```

加载失败互不影响：risk 加载失败不影响 system 配置显示，反之亦然。各自独立 catch。

### 3.2 保存逻辑

**方案：独立保存按钮**

风控配置使用**独立的保存按钮**，与系统配置的保存按钮分离。原因：

1. **语义不同**：系统配置标注"修改后需重启服务"，风控配置"立即生效（hot-reload）"，放在同一个按钮下语义混乱
2. **失败隔离**：两个保存独立，一个失败不影响另一个
3. **用户体验**：用户可能只改风控参数，不需要同时提交系统配置
4. **后端 API 不同**：分别是 `PUT /system` 和 `PUT /risk`

### 3.3 State 策略

**独立的 loading/saving 状态**：

| State | 用途 |
|-------|------|
| `riskLoading` | 风控配置加载中 |
| `riskSaving` | 风控配置保存中 |
| `riskError` | 风控配置加载错误 |

复用现有 `loading` / `saving` 仅用于系统配置，互不干扰。

页面级整体 loading 判定：`loading || riskLoading`（任一加载中显示 Spin）。

---

## 四、代码变更清单

### 4.1 `web-front/src/api/config.ts` — 新增类型导出

**新增 import**: 无（不涉及新 import）

**新增类型**:

```typescript
// 风控配置表单值类型（用于 Ant Design Form）
export interface RiskConfigFormValues {
  max_loss_percent: number;
  max_leverage: number;
  max_total_exposure: number | null;
  daily_max_trades: number | null;
  daily_max_loss: number | null;
  max_position_hold_time: number | null;
  cooldown_minutes: number;
}

// 风控配置更新请求（与后端 RiskConfigUpdateRequest 对齐）
export interface RiskConfigUpdateRequest {
  max_loss_percent?: number;
  max_leverage?: number;
  max_total_exposure?: number | null;
  daily_max_trades?: number | null;
  daily_max_loss?: number | null;
  max_position_hold_time?: number | null;
  cooldown_minutes?: number;
}
```

**预计新增行数**: ~20 行

---

### 4.2 `web-front/src/pages/config/SystemSettings.tsx` — 主要改动

#### 4.2.1 新增 import

```typescript
import {
  // 现有 import 保持不变
  Form, InputNumber, Card, Button, Switch, message, Spin, Alert, Collapse, Space, Divider,
} from 'antd';
// 新增：Slider 用于 max_leverage 可视化，Select 用于快速选择预设
// 新增：ShieldOutlined (风控图标)
import {
  ReloadOutlined, SaveOutlined, WarningOutlined, FileTextOutlined,
  ShieldOutlined,  // 新增
} from '@ant-design/icons';
// 新增类型导入
import { configApi, type SystemConfigResponse, type SystemConfigUpdateRequest,
         type RiskConfigFormValues, type RiskConfigUpdateRequest } from '../../api/config';
```

#### 4.2.2 新增常量

```typescript
const DEFAULT_RISK_CONFIG: RiskConfigFormValues = {
  max_loss_percent: 0.01,
  max_leverage: 10,
  max_total_exposure: null,
  daily_max_trades: null,
  daily_max_loss: null,
  max_position_hold_time: null,
  cooldown_minutes: 5,
};
```

#### 4.2.3 新增 state

```typescript
// 风控配置独立状态
const [riskForm] = Form.useForm();                    // 独立表单实例
const [riskLoading, setRiskLoading] = useState(false);
const [riskSaving, setRiskSaving] = useState(false);
const [riskError, setRiskError] = useState<string | null>(null);
const [riskConfig, setRiskConfig] = useState<RiskConfigFormValues | null>(null);
```

#### 4.2.4 新增 useEffect（加载风控配置）

在现有 `loadConfig` 内部，**并行加载**：

```typescript
const loadConfig = useCallback(async () => {
  setLoading(true);
  setRiskLoading(true);
  setError(null);
  setRiskError(null);
  try {
    // 并行加载系统配置和风控配置
    const [systemResponse, riskResponse] = await Promise.allSettled([
      configApi.getSystemConfig(),
      configApi.getRiskConfig(),
    ]);

    // 系统配置处理（现有逻辑不变）
    if (systemResponse.status === 'fulfilled') {
      // ... 现有 system config 解析逻辑
    } else {
      const errorMsg = systemResponse.reason?.response?.data?.detail
        || systemResponse.reason?.message || '加载失败';
      setError(errorMsg);
      message.error('加载系统配置失败：' + errorMsg);
    }

    // 风控配置处理（新增）
    if (riskResponse.status === 'fulfilled') {
      const data = riskResponse.value.data;
      const riskFormValues: RiskConfigFormValues = {
        max_loss_percent: data.max_loss_percent ?? DEFAULT_RISK_CONFIG.max_loss_percent,
        max_leverage: data.max_leverage ?? DEFAULT_RISK_CONFIG.max_leverage,
        max_total_exposure: data.max_total_exposure,
        daily_max_trades: data.daily_max_trades,
        daily_max_loss: data.daily_max_loss,
        max_position_hold_time: data.max_position_hold_time,
        cooldown_minutes: data.cooldown_minutes ?? DEFAULT_RISK_CONFIG.cooldown_minutes,
      };
      setRiskConfig(riskFormValues);
      riskForm.setFieldsValue(riskFormValues);
    } else {
      const errorMsg = riskResponse.reason?.response?.data?.detail
        || riskResponse.reason?.message || '加载失败';
      setRiskError(errorMsg);
      message.error('加载风控配置失败：' + errorMsg);
    }
  } finally {
    setLoading(false);
    setRiskLoading(false);
  }
}, [form, riskForm]);
```

#### 4.2.5 新增 handleSubmit（保存风控配置）

```typescript
const handleRiskSubmit = async (values: RiskConfigFormValues) => {
  setRiskSaving(true);
  try {
    // 构建更新请求（只传非 null 的字段，null 字段也传 null 表示清除限制）
    const updatePayload: RiskConfigUpdateRequest = {
      max_loss_percent: values.max_loss_percent,
      max_leverage: values.max_leverage,
      max_total_exposure: values.max_total_exposure,
      daily_max_trades: values.daily_max_trades,
      daily_max_loss: values.daily_max_loss,
      max_position_hold_time: values.max_position_hold_time,
      cooldown_minutes: values.cooldown_minutes,
    };

    await configApi.updateRiskConfig(updatePayload);
    message.success('风控配置已保存（立即生效）');
    setRiskConfig(values);
  } catch (err: any) {
    console.error('保存风控配置失败:', err);
    const errorMsg = err.response?.data?.detail || err.message || '保存失败';
    message.error('保存失败：' + errorMsg);
  } finally {
    setRiskSaving(false);
  }
};
```

#### 4.2.6 新增 handleRiskReset

```typescript
const handleRiskReset = () => {
  riskForm.resetFields();
  if (riskConfig) {
    riskForm.setFieldsValue(riskConfig);
  }
};
```

#### 4.2.7 新增 JSX — 风控配置 Card

插入位置：在现有"全局系统配置" Card 之后（`</Card>` 闭合标签之后），操作按钮之前。

```tsx
{/* 风控配置 (Level 1, 立即生效) */}
<Card
  title={
    <div className="flex items-center gap-2">
      <ShieldOutlined className="text-blue-500" />
      <span>风控配置</span>
      <span className="text-xs text-gray-400 font-normal ml-2">
        (修改后立即生效，无需重启)
      </span>
    </div>
  }
  className="mb-4 border-blue-200 bg-blue-50/30"
>
  <Form
    form={riskForm}
    layout="vertical"
    onFinish={handleRiskSubmit}
    initialValues={DEFAULT_RISK_CONFIG}
    size={isTab ? 'middle' : 'large'}
  >
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Divider orientation="left" className="my-2">
        仓位风控
      </Divider>

      <Form.Item
        name="max_loss_percent"
        label="最大损失百分比"
        rules={[{ required: true, type: 'number', min: 0.001, max: 1 }]}
        tooltip="单笔交易允许的最大损失占总资产的百分比，默认值：0.01 (1%)"
        extra="超过此阈值将强制平仓"
      >
        <InputNumber
          min={0.001}
          max={1}
          step={0.001}
          className="w-full"
          disabled={riskSaving}
          formatter={(value) => `${((value as number) * 100).toFixed(1)}%`}
          parser={(value) => Number(value?.replace('%', '')) / 100}
        />
      </Form.Item>

      <Form.Item
        name="max_leverage"
        label="最大杠杆倍数"
        rules={[{ required: true, type: 'number', min: 1, max: 125 }]}
        tooltip="允许使用的最大杠杆倍数，默认值：10"
        extra="高杠杆会放大盈亏，建议保守设置"
      >
        <InputNumber
          min={1}
          max={125}
          step={1}
          className="w-full"
          disabled={riskSaving}
          formatter={(value) => `${value}x`}
          parser={(value) => Number(value?.replace('x', ''))}
        />
      </Form.Item>

      <Form.Item
        name="max_total_exposure"
        label="最大总暴露比例"
        rules={[{ type: 'number', min: 0, max: 1 }]}
        tooltip="所有持仓的总暴露上限占总资产的比例，不填表示不限制"
        extra="1 = 100% 总资产，null = 不限制"
      >
        <InputNumber
          min={0}
          max={1}
          step={0.05}
          className="w-full"
          disabled={riskSaving}
          placeholder="不限制"
          formatter={(value) => value ? `${((value as number) * 100).toFixed(0)}%` : ''}
          parser={(value) => value ? Number(value?.replace('%', '')) / 100 : null}
        />
      </Form.Item>

      <Divider orientation="left" className="my-2">
        日频风控
      </Divider>

      <Form.Item
        name="daily_max_trades"
        label="每日最大交易次数"
        rules={[{ type: 'number', min: 1 }]}
        tooltip="单日允许的最大交易笔数，不填表示不限制"
        extra="防止过度交易，null = 不限制"
      >
        <InputNumber
          min={1}
          step={1}
          className="w-full"
          disabled={riskSaving}
          placeholder="不限制"
        />
      </Form.Item>

      <Form.Item
        name="daily_max_loss"
        label="每日最大损失"
        rules={[{ type: 'number', min: 0 }]}
        tooltip="单日累计最大允许损失金额，不填表示不限制"
        extra="null = 不限制"
      >
        <InputNumber
          min={0}
          step={100}
          className="w-full"
          disabled={riskSaving}
          placeholder="不限制"
          formatter={(value) => value ? `$${value}` : ''}
          parser={(value) => value ? Number(value?.replace('$', '')) : null}
        />
      </Form.Item>

      <Divider orientation="left" className="my-2">
        时间与冷却
      </Divider>

      <Form.Item
        name="max_position_hold_time"
        label="最大持仓时间"
        rules={[{ type: 'number', min: 1 }]}
        tooltip="单笔持仓允许的最大持有时间（分钟），不填表示不限制"
        extra="超时将强制平仓，null = 不限制"
      >
        <InputNumber
          min={1}
          step={30}
          className="w-full"
          disabled={riskSaving}
          placeholder="不限制"
          formatter={(value) => value ? `${value} 分钟` : ''}
          parser={(value) => value ? Number(value?.replace(' 分钟', '')) : null}
        />
      </Form.Item>

      <Form.Item
        name="cooldown_minutes"
        label="平仓冷却时间"
        rules={[{ required: true, type: 'number', min: 0 }]}
        tooltip="强制平仓后到下一次开仓之间的冷却时间（分钟），默认值：5"
        extra="防止连续亏损后的报复性交易"
      >
        <InputNumber
          min={0}
          max={1440}
          step={1}
          className="w-full"
          disabled={riskSaving}
          formatter={(value) => `${value} 分钟`}
          parser={(value) => Number(value?.replace(' 分钟', ''))}
        />
      </Form.Item>
    </Space>

    {/* 风控配置操作按钮 */}
    <Form.Item className="mt-6">
      <Space>
        <Button
          type="primary"
          htmlType="submit"
          loading={riskSaving}
          icon={<SaveOutlined />}
          size="large"
        >
          保存风控配置
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={handleRiskReset}
          size="large"
        >
          重置
        </Button>
      </Space>
    </Form.Item>
  </Form>
</Card>
```

#### 4.2.8 修改 loading 判断

页面级 loading 判定改为：

```tsx
if (loading || riskLoading) {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <Spin size="large" tip="加载系统配置..." />
    </div>
  );
}
```

#### 4.2.9 新增风险配置错误提示

在现有 system error Alert 之后，追加 risk error Alert：

```tsx
{riskError && (
  <Alert
    type="error"
    showIcon
    message="风控配置加载失败"
    description={riskError}
    action={
      <Button type="primary" size="small" onClick={loadConfig}>
        重新加载
      </Button>
    }
    className="mb-4"
  />
)}
```

---

## 五、预计代码行数

| 文件 | 改动类型 | 预计行数 |
|------|---------|---------|
| `web-front/src/api/config.ts` | 新增 2 个接口 | +20 |
| `web-front/src/pages/config/SystemSettings.tsx` | import 修改 | +2 |
| `web-front/src/pages/config/SystemSettings.tsx` | 新增常量 | +10 |
| `web-front/src/pages/config/SystemSettings.tsx` | 新增 state | +6 |
| `web-front/src/pages/config/SystemSettings.tsx` | 修改 loadConfig | +25 |
| `web-front/src/pages/config/SystemSettings.tsx` | 新增 handleRiskSubmit | +20 |
| `web-front/src/pages/config/SystemSettings.tsx` | 新增 handleRiskReset | +6 |
| `web-front/src/pages/config/SystemSettings.tsx` | 新增风控 Card JSX | +130 |
| `web-front/src/pages/config/SystemSettings.tsx` | 修改 loading/error 判断 | +15 |
| **总计** | | **~234 行** |

---

## 六、风险评估与缓解

### 风险 1: `max_loss_percent` 的 Decimal 精度问题

**描述**: 后端使用 `Decimal` 类型存储 `max_loss_percent`，前端使用 `number`。JavaScript 浮点数精度可能导致 `0.01` 变成 `0.010000000000000002`。

**影响**: 后端校验失败或存储不精确的值。

**缓解措施**:
1. `InputNumber` 设置 `step={0.001}` 控制精度
2. 提交前使用 `parseFloat(value.toFixed(4))` 截断多余小数位
3. 后端 `Decimal` 字段本身有精度控制，可容忍小数误差

### 风险 2: 两个表单共用页面，误操作风险

**描述**: 用户修改了风控配置但忘记点击保存，转而点击系统配置的保存按钮，导致风控修改丢失。

**影响**: 用户混淆两个独立的保存按钮。

**缓解措施**:
1. 风控 Card 使用不同的视觉风格（蓝色主题 vs 橙色主题），明确区分
2. 风控 Card 按钮文案明确为"保存风控配置"
3. 后续可选增强：表单未保存时显示 dirty 标记提示

### 风险 3: `daily_max_loss` 的单位歧义

**描述**: 后端 `daily_max_loss` 类型为 `Decimal`，但没有明确的单位文档。可能是金额（USDT）也可能是百分比。

**影响**: 前端展示单位与后端预期不一致。

**缓解措施**:
1. 当前方案中 `daily_max_loss` 使用 `$` 前缀（金额单位），与 `max_loss_percent`（百分比）区分
2. 需与后端确认实际单位语义，如为百分比则改用 `%` 格式
3. tooltip 和 extra 中注明单位

### 风险 4: 加载性能

**描述**: 页面打开时多一个 API 请求（`getRiskConfig`），增加加载时间。

**影响**: 页面初始加载稍慢。

**缓解措施**:
1. 使用 `Promise.allSettled` 并行请求，不串行增加延迟
2. 两个请求互不影响，一个失败不影响另一个显示
3. 风控配置数据量极小（单条记录），网络开销可忽略

### 风险 5: 权限不足

**描述**: `PUT /api/v1/config/risk` 需要 admin 权限。如果当前用户非 admin，保存将返回 403。

**影响**: 非 admin 用户看到风控配置但无法保存。

**缓解措施**:
1. 保存失败时捕获 403 错误，显示友好提示"需要管理员权限"
2. 后续可选：非 admin 用户显示只读模式（禁用表单控件）

---

## 七、验证清单

### 7.1 功能验证

1. 打开 `/config/system` 页面，确认"风控配置"Card 显示在"全局系统配置"Card 下方
2. 确认 7 个字段正确加载并填充
3. 修改 `max_loss_percent`，点击"保存风控配置"，确认成功提示"风控配置已保存（立即生效）"
4. 刷新页面，确认修改后的值已持久化
5. 点击"重置"，确认字段恢复到上次保存的值
6. 将可选字段（`max_total_exposure`、`daily_max_trades` 等）清空，确认提交 null 值
7. 测试边界值：`max_loss_percent=0.001`、`max_leverage=125`

### 7.2 错误场景

8. 模拟 API 加载失败（断网），确认显示错误 Alert + 重新加载按钮
9. 模拟 403 权限不足，确认显示友好的权限错误提示
10. 输入非法值（如 `max_leverage=0`），确认前端校验拦截

### 7.3 样式验证

11. Page 模式下，确认风控 Card 在左侧两列布局中正确显示
12. Tab 模式下，确认风控 Card 正确显示且无布局溢出
13. 确认风控 Card 的蓝色主题与系统配置的橙色主题视觉区分清晰

---

## 八、执行顺序

1. **Step 1**: `web-front/src/api/config.ts` 新增 `RiskConfigFormValues` 和 `RiskConfigUpdateRequest` 类型 (~20 行)
2. **Step 2**: `web-front/src/pages/config/SystemSettings.tsx` 新增 import、常量、state (~18 行)
3. **Step 3**: 修改 `loadConfig` 函数，加入并行加载风控配置 (~25 行修改)
4. **Step 4**: 新增 `handleRiskSubmit` 和 `handleRiskReset` 函数 (~26 行)
5. **Step 5**: 新增风控配置 Card JSX (~130 行)
6. **Step 6**: 修改 loading/error 渲染逻辑 (~15 行)
7. **Step 7**: 手动验证验证清单中的 13 个步骤

---

## 九、关键文件绝对路径

- 主要修改文件: `/Users/jiangwei/Documents/final/web-front/src/pages/config/SystemSettings.tsx`
- 类型定义文件: `/Users/jiangwei/Documents/final/web-front/src/api/config.ts`
- 后端端点参考: `/Users/jiangwei/Documents/final/src/interfaces/api_v1_config.py`
