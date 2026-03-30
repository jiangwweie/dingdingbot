---
name: 质量要求与审查标准
description: 领域层纯净性、Decimal 精度、类型安全是代码审查红线
type: feedback
---

## 质量要求与审查标准

**日期**: 2026-03-30

### 代码审查红线

#### 1. 领域层纯净性

`domain/` 目录**严禁**导入：
- `ccxt`
- `aiohttp`
- `requests`
- `fastapi`
- `yaml`
- 任何 I/O 框架

**检查方式**: `grep -r "import ccxt\|import aiohttp\|import requests\|import fastapi" src/domain/`

---

#### 2. Decimal 精度

所有金额、比率、计算**必须**使用 `decimal.Decimal`。

**使用 `float` 进行金融计算将被拒绝。**

**检查方式**: Code Review 检查金融字段类型

---

#### 3. 类型安全

- **禁用 `Dict[str, Any]`** - 核心参数必须定义具名 Pydantic 类
- **辨识联合** - 多态对象必须使用 `discriminator='type'`
- **自动 Schema** - 接口文档通过模型反射生成

---

#### 4. API 密钥安全

- API 密钥必须为**只读权限**
- 系统启动时校验权限，发现 `trade`/`withdraw` 权限立即退出
- 所有敏感信息必须通过 `mask_secret()` 脱敏后记录日志

---

### 测试覆盖要求

| 模块 | 覆盖率要求 |
|------|-----------|
| 撮合引擎 | 100% |
| 风控状态机 | 100% |
| 订单编排 | 95% |
| 实盘集成 | 90% |

---

### 错误码系统

| 错误码 | 级别 | 说明 |
|--------|------|------|
| `F-001` | FATAL | API Key 有交易权限 |
| `F-002` | FATAL | API Key 有提现权限 |
| `F-003` | FATAL | 必填配置缺失 |
| `F-004` | FATAL | 交易所初始化失败 |
| `C-001` | CRITICAL | WebSocket 重连超限 |
| `C-002` | CRITICAL | 资产轮询连续失败 |
| `W-001` | WARNING | K 线数据质量异常 |
| `W-002` | WARNING | 数据延迟超限 |

---

**如何应用**:
- Code Review 时对照红线检查
- 发现违规立即修复
- 测试覆盖率不达标不合并
