# OpenAPI Spec 模板与示例

> **用途**：为架构师提供 OpenAPI 3.0 规范的标准模板，确保前后端契约一致性
> **最后更新**：2026-04-07

---

## 📋 最小化模板（必须包含）

```yaml
openapi: 3.0.0
info:
  title: 盯盘狗 API - [功能名称]
  version: 1.0.0
  description: [功能描述]

servers:
  - url: http://localhost:8000/api
    description: 本地开发服务器

paths:
  /endpoint-path:
    post:
      summary: [端点说明]
      operationId: createSomething
      tags:
        - [模块名称]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateRequest'
      responses:
        '200':
          description: 成功响应
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SuccessResponse'
        '400':
          description: 参数错误
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

components:
  schemas:
    CreateRequest:
      type: object
      required:
        - [必填字段列表]
      properties:
        field_name:
          type: string
          description: [字段说明]
          example: [示例值]

    SuccessResponse:
      type: object
      properties:
        result_field:
          type: string

    ErrorResponse:
      type: object
      properties:
        error_code:
          type: string
          example: "F-011"
        message:
          type: string
          example: "订单参数错误"
```

---

## 🎯 盯盘狗项目完整示例

```yaml
openapi: 3.0.0
info:
  title: 盯盘狗 API - 订单管理
  version: 3.0.0
  description: 订单创建、提交、查询、取消接口

servers:
  - url: http://localhost:8000/api
    description: 本地开发服务器

paths:
  /orders:
    post:
      summary: 创建新订单
      operationId: createOrder
      tags:
        - Orders
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '200':
          description: 订单创建成功
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '400':
          description: 参数错误
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '500':
          description: 系统错误
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

    get:
      summary: 查询订单列表
      operationId: listOrders
      tags:
        - Orders
      parameters:
        - name: status
          in: query
          schema:
            $ref: '#/components/schemas/OrderStatus'
        - name: symbol
          in: query
          schema:
            type: string
      responses:
        '200':
          description: 查询成功
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/OrderResponse'

  /orders/{orderId}:
    get:
      summary: 查询订单详情
      operationId: getOrder
      tags:
        - Orders
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: 查询成功
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: 订单不存在
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

    delete:
      summary: 取消订单
      operationId: cancelOrder
      tags:
        - Orders
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: 取消成功
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '400':
          description: 订单已成交，无法取消
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

components:
  schemas:
    # 请求模型
    CreateOrderRequest:
      type: object
      required:
        - symbol
        - direction
        - entry_price
        - quantity
      properties:
        symbol:
          type: string
          description: 交易对符号（CCXT 格式）
          example: "BTC/USDT:USDT"
        direction:
          $ref: '#/components/schemas/Direction'
        entry_price:
          type: string
          description: 入场价格（Decimal 字符串格式）
          example: "65000.00"
        quantity:
          type: string
          description: 订单数量（Decimal 字符串格式）
          example: "0.001"
        stop_loss:
          type: string
          description: 止损价格（可选）
        take_profit:
          type: string
          description: 止盈价格（可选）
        leverage:
          type: integer
          description: 杠杆倍数
          default: 1
          minimum: 1
          maximum: 100

    # 响应模型
    OrderResponse:
      type: object
      properties:
        order_id:
          type: string
          description: 订单 ID
          example: "ord_abc123"
        symbol:
          type: string
        direction:
          $ref: '#/components/schemas/Direction'
        status:
          $ref: '#/components/schemas/OrderStatus'
        entry_price:
          type: string
          description: Decimal 字符串格式
        quantity:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    # 错误响应
    ErrorResponse:
      type: object
      required:
        - error_code
        - message
      properties:
        error_code:
          type: string
          description: 错误码（F/C/W 系列）
          enum:
            - F-001
            - F-002
            - F-010
            - F-011
            - F-012
            - F-013
            - C-001
            - C-010
            - W-001
          example: "F-011"
        message:
          type: string
          description: 错误消息
          example: "订单参数错误"
        details:
          type: object
          description: 详细错误信息（可选）

    # 枚举类型
    Direction:
      type: string
      description: 订单方向
      enum:
        - LONG
        - SHORT
      example: "LONG"

    OrderStatus:
      type: string
      description: 订单状态
      enum:
        - PENDING
        - SUBMITTED
        - FILLED
        - CANCELLED
        - FAILED
      example: "PENDING"
```

---

## ✅ 验证清单（架构师必须检查）

| 验证项 | 检查内容 | 示例 |
|--------|---------|------|
| ✅ 所有端点已定义 | API 设计中的所有端点都在 paths 中定义 | `/orders`, `/orders/{id}` |
| ✅ 请求/响应模型完整 | 所有请求参数和响应字段已定义 | CreateOrderRequest, OrderResponse |
| ✅ 错误码完整 | F/C/W 系列错误码已枚举 | F-011, C-001, W-001 |
| ✅ 枚举值完整 | Direction, OrderStatus 等枚举已定义 | LONG/SHORT, PENDING/FILLED/... |
| ✅ 数据类型明确 | Decimal 字段使用 string 类型 | entry_price: type: string |
| ✅ 必填/可选标注 | required 字段已明确列出 | symbol, direction, entry_price |

---

## 🛠️ 使用方法

### 1. 架构师在设计时

```bash
# 在 ADR 文档中引用
docs/arch/[feature]-design.md
  └─ "接口契约"章节
     └─ OpenAPI Spec 文件：docs/contracts/[feature]-api-spec.yaml
```

### 2. 后端开发时

```bash
# 从 OpenAPI Spec 生成类型定义
pip install openapi-python-client
openapi-python-client generate --path docs/contracts/orders-api-spec.yaml

# 输出：src/interfaces/orders_types.py（自动生成）
```

### 3. 前端开发时

```bash
# 从 OpenAPI Spec 生成 TypeScript 类型
npm install -D openapi-typescript
openapi-typescript docs/contracts/orders-api-spec.yaml > web-front/src/types/orders.ts

# 输出：web-front/src/types/orders.ts（自动生成）
```

### 4. Mock 服务器

```bash
# 使用 Prism 创建 Mock API
npm install -g @stoplight/prism-cli
prism mock docs/contracts/orders-api-spec.yaml

# 输出：http://localhost:4010 (Mock API 服务器)
```

---

## 📚 参考资源

- [OpenAPI 3.0 规范](https://swagger.io/specification/)
- [FastAPI 自动生成 OpenAPI](https://fastapi.tiangolo.com/tutorial/security/handle-auth-errors/)
- [openapi-python-client](https://github.com/openapi-generators/openapi-python-client)
- [openapi-typescript](https://github.com/drwpow/openapi-typescript)

---

*本模板由 `/architect` skill 强制要求，确保前后端契约一致性*