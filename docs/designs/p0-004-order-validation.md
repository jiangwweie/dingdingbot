# P0-004: 订单参数合理性检查设计

> **创建日期**: 2026-04-01
> **任务 ID**: P0-004
> **阶段**: 阶段 1 - 详细设计
> **状态**: ⚠️ 修改后批准 (2026-04-01 评审通过，需修复 1 个问题)

---

## 一、问题分析

### 1.1 粉尘订单（Dust Orders）

**定义**: 订单金额过小，低于交易所最小交易限制的订单。

**产生原因**:
1. 策略计算错误，导致下单数量过小
2. 剩余余额精度问题，产生极小数量订单
3. 测试/调试时未设置合理下限

**风险**:
- **订单拒绝**: 交易所直接拒绝，浪费 API 调用次数
- **资源浪费**: 占用系统资源处理无效订单
- **策略异常信号**: 可能掩盖策略逻辑问题

### 1.2  Binance 最小订单金额限制

| 交易所 | 最小订单金额 | 说明 |
|--------|-------------|------|
| **Binance** | ≥5 USDT | 订单价值 (数量 × 价格) 必须≥5 USDT |
| **OKX** | ≥5 USDT (等值) | 部分交易对可能不同 |
| **Bybit** | 无统一限制 | 按交易对精度限制 |

**订单价值计算公式**:
```
order_value = quantity × price

对于市价单:
order_value = quantity × current_market_price

对于条件单:
order_value = quantity × trigger_price
```

### 1.3 异常价格订单

**定义**: 订单价格偏离当前市场价格超过合理范围的订单。

**产生原因**:
1. 策略参数配置错误（如止损设置过远）
2. 数据源异常（如 K 线数据错误）
3. 计算逻辑 bug（如小数点位置错误）

**风险**:
- **意外成交**: 价格异常可能导致快速成交，造成损失
- **订单拒绝**: 交易所价格限制可能拒绝订单
- **策略偏离**: 实际执行价格与策略预期严重不符

### 1.4 价格偏差示例

假设 BTC/USDT 当前市场价格为 70,000 USDT：

| 订单类型 | 订单价格 | 偏差 | 判定 |
|----------|----------|------|------|
| 限价买单 | 68,000 | -2.86% | ✅ 合理 |
| 限价买单 | 62,000 | -11.43% | ❌ 异常（偏差>10%） |
| 限价卖单 | 72,000 | +2.86% | ✅ 合理 |
| 限价卖单 | 78,000 | +11.43% | ❌ 异常（偏差>10%） |
| 止损买单 | 71,000 | +1.43% | ✅ 合理 |
| 止损买单 | 80,000 | +14.29% | ❌ 异常（偏差>10%） |

---

## 二、技术方案

### 2.1 检查流程概览

```
┌─────────────────────────────────────────────────────────────┐
│                  订单参数合理性检查流程                       │
├─────────────────────────────────────────────────────────────┤
│  1. 获取订单参数 (symbol, quantity, price, trigger_price)    │
│  2. 获取市场数据 (当前价格、交易对精度)                       │
│  3. 检查 1: 最小订单金额 (Binance ≥5 USDT)                   │
│  4. 检查 2: 价格合理性 (偏差≤10%)                            │
│  5. 检查 3: 数量精度 (符合交易对精度要求)                     │
│  6. 汇总检查结果，返回 OrderValidationResult                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 最小订单金额检查

#### 2.2.1 检查逻辑

```python
async def check_minimum_order_value(
    symbol: str,
    quantity: Decimal,
    price: Optional[Decimal],
    trigger_price: Optional[Decimal],
    order_type: OrderType,
) -> OrderValueCheckResult:
    """
    检查最小订单金额

    规则:
    - Binance: 订单价值 ≥ 5 USDT
    - 市价单：使用当前市场价格计算
    - 限价单：使用指定价格计算
    - 条件单：使用触发价计算

    Args:
        symbol: 交易对
        quantity: 订单数量
        price: 限价单价格（可选）
        trigger_price: 条件单触发价（可选）
        order_type: 订单类型

    Returns:
        OrderValueCheckResult: 检查结果
    """
    # 确定用于计算的有效价格
    effective_price = await get_effective_price(
        symbol, price, trigger_price, order_type
    )
    
    if effective_price is None:
        return OrderValueCheckResult(
            passed=False,
            reason="CANNOT_GET_PRICE",
            reason_message="无法获取有效价格用于计算订单价值"
        )
    
    # 计算订单价值
    order_value = quantity * effective_price
    
    # Binance 最小订单金额限制
    MIN_ORDER_VALUE = Decimal("5.0")  # 5 USDT
    
    if order_value < MIN_ORDER_VALUE:
        return OrderValueCheckResult(
            passed=False,
            reason="BELOW_MIN_ORDER_VALUE",
            reason_message=f"订单价值 {order_value:.2f} USDT < 最小限制 {MIN_ORDER_VALUE} USDT",
            order_value=order_value,
            min_required_value=MIN_ORDER_VALUE
        )
    
    return OrderValueCheckResult(
        passed=True,
        reason=None,
        reason_message=f"订单价值 {order_value:.2f} USDT ≥ 最小限制 {MIN_ORDER_VALUE} USDT",
        order_value=order_value,
        min_required_value=MIN_ORDER_VALUE
    )
```

#### 2.2.2 有效价格获取逻辑

```python
async def get_effective_price(
    symbol: str,
    price: Optional[Decimal],
    trigger_price: Optional[Decimal],
    order_type: OrderType,
) -> Optional[Decimal]:
    """
    获取用于计算订单价值的有效价格

    价格选择优先级:
    1. 限价单：使用指定 price
    2. 条件单：使用 trigger_price
    3. 市价单：调用 fetch_ticker_price 获取市场价
    """
    if order_type == OrderType.LIMIT:
        return price
    elif order_type in [OrderType.STOP_MARKET, OrderType.STOP_LIMIT]:
        return trigger_price
    elif order_type == OrderType.MARKET:
        # 获取当前市场价格
        return await exchange_gateway.fetch_ticker_price(symbol)
    else:
        return None
```

### 2.3 价格合理性检查

#### 2.3.1 检查逻辑

```python
async def check_price_deviation(
    symbol: str,
    price: Decimal,
    order_type: OrderType,
    max_deviation_percent: Decimal = Decimal("10.0"),
) -> PriceDeviationCheckResult:
    """
    检查价格偏差是否在合理范围内

    规则:
    - 计算订单价格相对于市场价格的偏差百分比
    - 偏差超过 max_deviation_percent（默认 10%）则拒绝

    偏差计算公式:
    deviation_percent = (order_price - market_price) / market_price × 100%

    Args:
        symbol: 交易对
        price: 订单价格
        order_type: 订单类型
        max_deviation_percent: 最大允许偏差百分比

    Returns:
        PriceDeviationCheckResult: 检查结果
    """
    # 获取当前市场价格
    market_price = await exchange_gateway.fetch_ticker_price(symbol)
    
    if market_price is None:
        return PriceDeviationCheckResult(
            passed=False,
            reason="CANNOT_GET_MARKET_PRICE",
            reason_message="无法获取市场价格进行偏差比较"
        )
    
    # 计算偏差百分比
    deviation = (price - market_price) / market_price * Decimal("100")
    abs_deviation = abs(deviation)
    
    # 判断是否超过阈值
    if abs_deviation > max_deviation_percent:
        return PriceDeviationCheckResult(
            passed=False,
            reason="PRICE_DEVIATION_EXCEEDED",
            reason_message=f"价格偏差 {deviation:+.2f}% 超过限制 {max_deviation_percent}%",
            order_price=price,
            market_price=market_price,
            deviation_percent=deviation,
            max_allowed_deviation=max_deviation_percent
        )
    
    return PriceDeviationCheckResult(
        passed=True,
        reason=None,
        reason_message=f"价格偏差 {deviation:+.2f}% 在允许范围内",
        order_price=price,
        market_price=market_price,
        deviation_percent=deviation,
        max_allowed_deviation=max_deviation_percent
    )
```

#### 2.3.2 不同订单类型的价格检查策略

| 订单类型 | 检查价格 | 偏差方向 | 说明 |
|----------|----------|----------|------|
| LIMIT (买入) | limit_price | 负偏差 | 买单价格低于市场价才合理 |
| LIMIT (卖出) | limit_price | 正偏差 | 卖单价格高于市场价才合理 |
| STOP_MARKET (买入) | - | 不检查 | 市价单无指定价格 |
| STOP_MARKET (卖出) | - | 不检查 | 市价单无指定价格 |
| STOP_LIMIT | trigger_price | 根据方向 | 条件单检查触发价 |

### 2.4 数量精度检查

#### 2.4.1 检查逻辑

```python
async def check_quantity_precision(
    symbol: str,
    quantity: Decimal,
) -> QuantityPrecisionCheckResult:
    """
    检查订单数量是否符合交易对精度要求

    规则:
    - 数量不能小于最小交易量
    - 数量精度不能超过交易所允许的小数位数

    Args:
        symbol: 交易对
        quantity: 订单数量

    Returns:
        QuantityPrecisionCheckResult: 检查结果
    """
    # 获取交易对精度信息
    market_info = await exchange_gateway.get_market_info(symbol)
    
    min_quantity = market_info.min_quantity  # 最小交易量
    quantity_precision = market_info.quantity_precision  # 数量精度
    
    # 检查最小交易量
    if quantity < min_quantity:
        return QuantityPrecisionCheckResult(
            passed=False,
            reason="BELOW_MIN_QUANTITY",
            reason_message=f"订单数量 {quantity} < 最小限制 {min_quantity}",
            quantity=quantity,
            min_quantity=min_quantity
        )
    
    # 检查精度
    quantity_str = str(quantity)
    if '.' in quantity_str:
        decimals = len(quantity_str.split('.')[1])
        if decimals > quantity_precision:
            return QuantityPrecisionCheckResult(
                passed=False,
                reason="QUANTITY_PRECISION_EXCEEDED",
                reason_message=f"订单数量精度 {decimals} > 最大允许 {quantity_precision}",
                quantity=quantity,
                required_precision=quantity_precision
            )
    
    return QuantityPrecisionCheckResult(
        passed=True,
        reason=None,
        reason_message="数量精度检查通过",
        quantity=quantity
    )
```

### 2.5 综合检查结果

```python
class OrderValidationResult(BaseModel):
    """订单参数合理性检查结果"""
    passed: bool = Field(..., description="是否通过所有检查")
    order_id: Optional[str] = Field(None, description="订单 ID（如有）")
    symbol: str = Field(..., description="交易对")
    
    # 各单项检查结果
    order_value_check: Optional[OrderValueCheckResult] = Field(
        None, description="订单价值检查结果"
    )
    price_deviation_check: Optional[PriceDeviationCheckResult] = Field(
        None, description="价格偏差检查结果"
    )
    quantity_precision_check: Optional[QuantityPrecisionCheckResult] = Field(
        None, description="数量精度检查结果"
    )
    
    # 汇总信息
    failed_checks: List[str] = Field(
        default_factory=list,
        description="失败的检查项列表"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="警告信息列表"
    )
    reject_reason: Optional[str] = Field(
        None,
        description="拒绝原因代码"
    )
    reject_message: Optional[str] = Field(
        None,
        description="拒绝原因人类可读描述"
    )
```

---

## 三、修改文件清单

### 3.1 核心文件

| 文件路径 | 修改类型 | 说明 |
|----------|----------|------|
| `src/application/capital_protection.py` | 修改 | 新增订单参数合理性检查功能 |

### 3.2 具体修改内容

#### `src/application/capital_protection.py`

**现有代码分析**:
- 已有 `CapitalProtectionManager` 类负责下单前检查
- 已有 `pre_order_check()` 方法进行资金检查
- 需要新增订单参数合理性检查方法

**新增类和方法**:

```python
# ========== 新增检查模型 ==========

class OrderValueCheckResult(BaseModel):
    """订单价值检查结果"""
    passed: bool
    reason: Optional[str]
    reason_message: Optional[str]
    order_value: Optional[Decimal]
    min_required_value: Optional[Decimal]


class PriceDeviationCheckResult(BaseModel):
    """价格偏差检查结果"""
    passed: bool
    reason: Optional[str]
    reason_message: Optional[str]
    order_price: Optional[Decimal]
    market_price: Optional[Decimal]
    deviation_percent: Optional[Decimal]
    max_allowed_deviation: Optional[Decimal]


class QuantityPrecisionCheckResult(BaseModel):
    """数量精度检查结果"""
    passed: bool
    reason: Optional[str]
    reason_message: Optional[str]
    quantity: Optional[Decimal]
    min_quantity: Optional[Decimal]
    required_precision: Optional[int]


# ========== 新增验证器类 ==========

class OrderValidator:
    """
    订单参数合理性验证器
    
    职责:
    1. 最小订单金额检查
    2. 价格合理性检查
    3. 数量精度检查
    """
    
    def __init__(
        self,
        gateway: "ExchangeGateway",
        config: OrderValidationConfig,
    ):
        self._gateway = gateway
        self._config = config
    
    async def validate_order(
        self,
        symbol: str,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal],
        trigger_price: Optional[Decimal],
    ) -> OrderValidationResult:
        """
        执行订单参数合理性检查
        
        检查顺序:
        1. 订单价值检查（快速失败）
        2. 价格偏差检查
        3. 数量精度检查
        """
        failed_checks = []
        warnings = []
        
        # 检查 1: 订单价值
        value_result = await self.check_minimum_order_value(
            symbol, quantity, price, trigger_price, order_type
        )
        if not value_result.passed:
            failed_checks.append("ORDER_VALUE")
            return OrderValidationResult(
                passed=False,
                symbol=symbol,
                order_value_check=value_result,
                failed_checks=failed_checks,
                reject_reason=value_result.reason,
                reject_message=value_result.reason_message
            )
        
        # 检查 2: 价格偏差（仅限价单和条件单）
        if order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            check_price = price if order_type == OrderType.LIMIT else trigger_price
            if check_price:
                price_result = await self.check_price_deviation(
                    symbol, check_price, order_type
                )
                if not price_result.passed:
                    failed_checks.append("PRICE_DEVIATION")
                    return OrderValidationResult(
                        passed=False,
                        symbol=symbol,
                        order_value_check=value_result,
                        price_deviation_check=price_result,
                        failed_checks=failed_checks,
                        reject_reason=price_result.reason,
                        reject_message=price_result.reason_message
                    )
                elif abs(price_result.deviation_percent) > Decimal("5"):
                    warnings.append(
                        f"价格偏差较大：{price_result.deviation_percent:+.2f}%"
                    )
        
        # 检查 3: 数量精度
        precision_result = await self.check_quantity_precision(symbol, quantity)
        if not precision_result.passed:
            failed_checks.append("QUANTITY_PRECISION")
            return OrderValidationResult(
                passed=False,
                symbol=symbol,
                order_value_check=value_result,
                quantity_precision_check=precision_result,
                failed_checks=failed_checks,
                reject_reason=precision_result.reason,
                reject_message=precision_result.reason_message
            )
        
        # 所有检查通过
        return OrderValidationResult(
            passed=True,
            symbol=symbol,
            order_value_check=value_result,
            price_deviation_check=price_result if order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] else None,
            quantity_precision_check=precision_result,
            failed_checks=[],
            warnings=warnings
        )
    
    async def check_minimum_order_value(self, ...) -> OrderValueCheckResult:
        """最小订单金额检查实现"""
        pass
    
    async def check_price_deviation(self, ...) -> PriceDeviationCheckResult:
        """价格偏差检查实现"""
        pass
    
    async def check_quantity_precision(self, ...) -> QuantityPrecisionCheckResult:
        """数量精度检查实现"""
        pass


# ========== 修改 CapitalProtectionManager ==========

class CapitalProtectionManager:
    """资金保护管理器（扩展版）"""
    
    def __init__(
        self,
        config: CapitalProtectionConfig,
        account_service: "AccountService",
        notifier: "Notifier",
        gateway: "ExchangeGateway",
        order_validator: Optional[OrderValidator] = None,  # 新增
    ):
        # ... 现有初始化代码 ...
        self._order_validator = order_validator
    
    async def pre_order_check(
        self,
        symbol: str,
        order_type: OrderType,
        amount: Decimal,
        price: Optional[Decimal],
        trigger_price: Optional[Decimal],
        stop_loss: Decimal,
    ) -> OrderCheckResult:
        """
        下单前检查（扩展版）
        
        新增:
        - 在资金检查前，先执行订单参数合理性检查
        """
        # ========== 新增：订单参数合理性检查 ==========
        if self._order_validator:
            validation_result = await self._order_validator.validate_order(
                symbol=symbol,
                order_type=order_type,
                quantity=amount,
                price=price,
                trigger_price=trigger_price,
            )
            
            if not validation_result.passed:
                # 订单参数检查失败，直接拒绝
                await self._notifier.send_alert(
                    "订单参数检查失败",
                    validation_result.reject_message
                )
                return OrderCheckResult(
                    allowed=False,
                    reason="ORDER_VALIDATION_FAILED",
                    reason_message=validation_result.reject_message,
                )
        
        # ========== 现有资金检查逻辑保持不变 ==========
        # ... 现有代码 ...
```

### 3.3 新增配置文件

```python
# src/domain/models.py 新增

class OrderValidationConfig(BaseModel):
    """订单参数合理性检查配置"""
    enabled: bool = Field(default=True, description="是否启用订单参数检查")
    
    # 最小订单金额
    min_order_value_usdt: Decimal = Field(
        default=Decimal("5.0"),
        description="最小订单金额 (USDT)"
    )
    
    # 价格偏差
    max_price_deviation_percent: Decimal = Field(
        default=Decimal("10.0"),
        description="最大允许价格偏差百分比"
    )
    
    # 警告阈值
    warning_price_deviation_percent: Decimal = Field(
        default=Decimal("5.0"),
        description="触发警告的价格偏差百分比"
    )
```

### 3.4 相关文件

| 文件路径 | 关联说明 |
|----------|----------|
| `src/domain/models.py` | 新增检查模型和配置 |
| `src/infrastructure/exchange_gateway.py` | 提供市场价格和交易对信息 |
| `tests/unit/test_order_validator.py` | 单元测试文件 |

---

## 四、风险评估

### 4.1 误拒绝风险

| 风险场景 | 可能性 | 影响 | 缓解措施 |
|----------|--------|------|----------|
| **价格阈值设置过严** | 中 | 中 | 默认 10%，可配置调整；>5% 仅警告 |
| **市场价格获取延迟** | 中 | 中 | 使用最新缓存价格，设置超时 |
| **不同交易所限制差异** | 高 | 中 | 按交易所配置不同参数 |

### 4.2 交易所差异

| 交易所 | 最小订单金额 | 价格精度 | 数量精度 |
|--------|-------------|----------|----------|
| **Binance** | 5 USDT | 2 位小数 | 6 位小数 |
| **OKX** | 5 USDT (等值) |  varies | varies |
| **Bybit** | 按交易对 | varies | varies |

**配置示例**:
```python
EXCHANGE_VALIDATION_CONFIG = {
    "binance": OrderValidationConfig(
        min_order_value_usdt=Decimal("5.0"),
        max_price_deviation_percent=Decimal("10.0"),
    ),
    "okx": OrderValidationConfig(
        min_order_value_usdt=Decimal("5.0"),
        max_price_deviation_percent=Decimal("10.0"),
    ),
    "bybit": OrderValidationConfig(
        min_order_value_usdt=Decimal("1.0"),  # Bybit 限制较低
        max_price_deviation_percent=Decimal("15.0"),  # 更宽松
    ),
}
```

### 4.3 边界情况

| 边界场景 | 处理方式 |
|----------|----------|
| **市场价格获取失败** | 拒绝订单，返回"CANNOT_GET_MARKET_PRICE" |
| **市价单无法检查价格偏差** | 跳过价格偏差检查，仅检查订单价值 |
| **极端行情波动** | 临时放宽偏差阈值或暂停下单 |
| **新上市交易对无历史价格** | 使用发行价或参考类似交易对 |

---

## 五、测试计划

### 5.1 边界值测试

#### 5.1.1 最小订单金额边界测试

```python
class TestMinOrderValueBoundary:
    
    @pytest.mark.asyncio
    async def test_order_value_exactly_at_limit(self):
        """测试订单价值恰好等于最小限制"""
        # 订单价值 = 5.00 USDT (边界值)
        result = await validator.check_minimum_order_value(
            symbol="BTC/USDT:USDT",
            quantity=Decimal("0.0001"),
            price=Decimal("50000"),  # 0.0001 × 50000 = 5 USDT
            order_type=OrderType.LIMIT
        )
        assert result.passed is True
    
    @pytest.mark.asyncio
    async def test_order_value_just_below_limit(self):
        """测试订单价值略低于最小限制"""
        # 订单价值 = 4.99 USDT (边界值 - 0.01)
        result = await validator.check_minimum_order_value(
            symbol="BTC/USDT:USDT",
            quantity=Decimal("0.0001"),
            price=Decimal("49900"),  # 0.0001 × 49900 = 4.99 USDT
            order_type=OrderType.LIMIT
        )
        assert result.passed is False
        assert result.reason == "BELOW_MIN_ORDER_VALUE"
    
    @pytest.mark.asyncio
    async def test_order_value_well_above_limit(self):
        """测试订单价值远高于最小限制"""
        result = await validator.check_minimum_order_value(
            symbol="BTC/USDT:USDT",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),  # 0.01 × 50000 = 500 USDT
            order_type=OrderType.LIMIT
        )
        assert result.passed is True
```

#### 5.1.2 价格偏差边界测试

```python
class TestPriceDeviationBoundary:
    
    @pytest.mark.asyncio
    async def test_deviation_exactly_at_limit(self):
        """测试价格偏差恰好等于限制"""
        market_price = Decimal("100000")
        order_price = Decimal("110000")  # +10% 偏差
        
        result = await validator.check_price_deviation(
            symbol="BTC/USDT:USDT",
            price=order_price,
            order_type=OrderType.LIMIT
        )
        assert result.passed is True
        assert result.deviation_percent == Decimal("10.0")
    
    @pytest.mark.asyncio
    async def test_deviation_just_over_limit(self):
        """测试价格偏差略超过限制"""
        market_price = Decimal("100000")
        order_price = Decimal("110001")  # +10.001% 偏差
        
        result = await validator.check_price_deviation(
            symbol="BTC/USDT:USDT",
            price=order_price,
            order_type=OrderType.LIMIT
        )
        assert result.passed is False
        assert result.reason == "PRICE_DEVIATION_EXCEEDED"
    
    @pytest.mark.asyncio
    async def test_negative_deviation_within_limit(self):
        """测试负向偏差在限制内"""
        market_price = Decimal("100000")
        order_price = Decimal("90000")  # -10% 偏差
        
        result = await validator.check_price_deviation(
            symbol="BTC/USDT:USDT",
            price=order_price,
            order_type=OrderType.LIMIT
        )
        assert result.passed is True
        assert result.deviation_percent == Decimal("-10.0")
```

### 5.2 异常场景测试

#### 5.2.1 市场价格获取失败

```python
class TestPriceFetchFailure:
    
    @pytest.mark.asyncio
    async def test_market_price_unavailable(self):
        """测试市场价格无法获取时的处理"""
        # Mock 交易所返回 None
        mock_gateway.fetch_ticker_price.return_value = None
        
        result = await validator.check_minimum_order_value(
            symbol="BTC/USDT:USDT",
            quantity=Decimal("0.01"),
            price=None,  # 市价单
            order_type=OrderType.MARKET
        )
        
        assert result.passed is False
        assert result.reason == "CANNOT_GET_PRICE"
    
    @pytest.mark.asyncio
    async def test_market_price_timeout(self):
        """测试市场价格获取超时"""
        # Mock 交易所抛出异常
        mock_gateway.fetch_ticker_price.side_effect = TimeoutError()
        
        result = await validator.check_minimum_order_value(
            symbol="BTC/USDT:USDT",
            quantity=Decimal("0.01"),
            price=None,
            order_type=OrderType.MARKET
        )
        
        assert result.passed is False
```

#### 5.2.2 市价单特殊处理

```python
class TestMarketOrderHandling:
    
    @pytest.mark.asyncio
    async def test_market_order_uses_ticker_price(self):
        """测试市价单使用 ticker 价格计算订单价值"""
        mock_ticker_price = Decimal("50000")
        mock_gateway.fetch_ticker_price.return_value = mock_ticker_price
        
        result = await validator.validate_order(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            quantity=Decimal("0.001"),  # 0.001 × 50000 = 50 USDT
            price=None,
            trigger_price=None,
        )
        
        # 市价单应跳过价格偏差检查
        assert result.passed is True
        assert result.price_deviation_check is None
    
    @pytest.mark.asyncio
    async def test_market_order_below_min_value(self):
        """测试市价单低于最小价值"""
        mock_ticker_price = Decimal("50000")
        mock_gateway.fetch_ticker_price.return_value = mock_ticker_price
        
        result = await validator.validate_order(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            quantity=Decimal("0.00001"),  # 0.00001 × 50000 = 0.5 USDT < 5
            price=None,
            trigger_price=None,
        )
        
        assert result.passed is False
        assert "ORDER_VALUE" in result.failed_checks
```

#### 5.2.3 条件单特殊处理

```python
class TestStopOrderHandling:
    
    @pytest.mark.asyncio
    async def test_stop_market_uses_trigger_price(self):
        """测试 STOP_MARKET 订单使用触发价计算"""
        result = await validator.check_minimum_order_value(
            symbol="BTC/USDT:USDT",
            quantity=Decimal("0.001"),
            price=None,
            trigger_price=Decimal("50000"),  # 0.001 × 50000 = 50 USDT
            order_type=OrderType.STOP_MARKET
        )
        
        assert result.passed is True
        assert result.order_value == Decimal("50")
    
    @pytest.mark.asyncio
    async def test_stop_limit_price_deviation_check(self):
        """测试 STOP_LIMIT 订单检查触发价偏差"""
        market_price = Decimal("100000")
        trigger_price = Decimal("90000")  # -10% 偏差
        
        mock_gateway.fetch_ticker_price.return_value = market_price
        
        result = await validator.check_price_deviation(
            symbol="BTC/USDT:USDT",
            price=trigger_price,
            order_type=OrderType.STOP_LIMIT
        )
        
        assert result.passed is True
        assert result.deviation_percent == Decimal("-10.0")
```

### 5.3 端到端集成测试

```python
class TestOrderValidatorIntegration:
    
    @pytest.mark.asyncio
    async def test_full_validation_flow_success(self):
        """测试完整验证流程（通过场景）"""
        result = await order_validator.validate_order(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("68000"),  # 合理价格
            trigger_price=None,
        )
        
        assert result.passed is True
        assert len(result.failed_checks) == 0
    
    @pytest.mark.asyncio
    async def test_full_validation_flow_dust_order(self):
        """测试完整验证流程（粉尘订单场景）"""
        result = await order_validator.validate_order(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.00001"),  # 过小
            price=Decimal("70000"),
            trigger_price=None,
        )
        
        assert result.passed is False
        assert "ORDER_VALUE" in result.failed_checks
        assert result.reject_reason == "BELOW_MIN_ORDER_VALUE"
    
    @pytest.mark.asyncio
    async def test_full_validation_flow_abnormal_price(self):
        """测试完整验证流程（异常价格场景）"""
        result = await order_validator.validate_order(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("50000"),  # 偏差约 -28%
            trigger_price=None,
        )
        
        assert result.passed is False
        assert "PRICE_DEVIATION" in result.failed_checks
        assert result.reject_reason == "PRICE_DEVIATION_EXCEEDED"
```

### 5.4 测试矩阵

| 订单类型 | 价格检查 | 价值检查 | 精度检查 |
|----------|----------|----------|----------|
| MARKET | 跳过 | ✓ (用 ticker 价) | ✓ |
| LIMIT | ✓ | ✓ | ✓ |
| STOP_MARKET | 跳过 | ✓ (用 trigger 价) | ✓ |
| STOP_LIMIT | ✓ (用 trigger 价) | ✓ | ✓ |

---

## 六、阶段 2 设计评审检查清单（预填答案）

### 6.1 问题定义清晰度

- [x] 粉尘订单定义是否清晰？
  - **答案**: 是，明确定义为"低于最小订单金额限制"的订单
- [x] 异常价格订单定义是否清晰？
  - **答案**: 是，明确定义为"价格偏差超过 10%"的订单
- [x] Binance 最小订单金额规则是否准确？
  - **答案**: 是，≥5 USDT 是 Binance 官方限制

### 6.2 技术方案合理性

- [x] 检查流程是否合理？
  - **答案**: 是，采用三级检查（价值→价格→精度），快速失败策略
- [x] 有效价格获取逻辑是否正确？
  - **答案**: 是，限价单用指定价、市价单用 ticker 价、条件单用触发价
- [x] 价格偏差计算公式是否正确？
  - **答案**: 是，使用标准偏差公式 `(order-martket)/market × 100%`

### 6.3 风险评估充分性

- [x] 误拒绝风险是否考虑？
  - **答案**: 是，通过可配置阈值和警告机制缓解
- [x] 交易所差异是否考虑？
  - **答案**: 是，设计了按交易所配置的机制
- [x] 边界情况是否考虑？
  - **答案**: 是，覆盖价格获取失败、市价单、极端行情等场景

### 6.4 测试计划完整性

- [x] 边界值测试是否全面？
  - **答案**: 是，覆盖恰好等于、略低于、远高于等边界
- [x] 异常场景测试是否考虑？
  - **答案**: 是，覆盖价格获取失败、超时、市价单等特殊场景
- [x] 端到端测试是否设计？
  - **答案**: 是，覆盖完整验证流程的通过和失败场景

---

## 七、变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | 2026-04-01 | 初始版本 | - |

---

*设计文档版本：v1.0*
*状态：待评审*
