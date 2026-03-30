"""
DCA (Dollar-Cost Averaging) 分批建仓策略

Phase 5: 实盘集成 - DCA 分批建仓策略
Reference: docs/designs/phase5-detailed-design.md Section 3.5

核心特性:
- 支持 2-5 批次入场
- G-003 修复：提前预埋限价单（Maker 挂单，低滑点 + 低手续费）
- 平均成本法计算持仓成本
- Decimal 精度保证
"""
from decimal import Decimal
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
import time

from .models import Direction, OrderType


# ============================================================
# DCA 配置模型
# ============================================================
class DcaBatchTrigger(BaseModel):
    """单个批次的触发配置"""
    batch_index: int = Field(..., ge=1, description="批次序号 (从 1 开始)")
    order_type: OrderType = Field(..., description="订单类型 (MARKET/LIMIT)")
    ratio: Decimal = Field(..., gt=0, le=1, description="该批次的资金比例 (如 0.5 = 50%)")
    trigger_drop_percent: Optional[Decimal] = Field(
        default=None,
        description="触发跌幅百分比 (LIMIT 订单专用，多头为负值如 -2.0 表示下跌 2%)"
    )

    @field_validator('ratio')
    @classmethod
    def validate_ratio(cls, v):
        """验证比例在合理范围内"""
        if v <= 0 or v > 1:
            raise ValueError("ratio 必须在 (0, 1] 范围内")
        return v


class DcaConfig(BaseModel):
    """DCA 策略配置"""
    enabled: bool = Field(default=True, description="是否启用 DCA 策略")
    entry_batches: int = Field(default=3, ge=2, le=5, description="入场批次数量 (2-5)")
    entry_ratios: List[Decimal] = Field(
        default_factory=lambda: [Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
        description="各批次资金比例列表 (总和必须为 1.0)"
    )
    place_all_orders_upfront: bool = Field(
        default=True,
        description="G-003 修复：是否提前预埋所有限价单"
    )
    batch_triggers: List[DcaBatchTrigger] = Field(
        default_factory=list,
        description="各批次触发配置"
    )
    cost_basis_mode: Literal["average"] = Field(
        default="average",
        description="成本计算模式 (average = 平均成本法)"
    )
    total_amount: Decimal = Field(
        default=Decimal("0"),
        description="计划投入的总数量 (由外部计算传入)"
    )

    @field_validator('entry_ratios')
    @classmethod
    def validate_ratios_sum(cls, v):
        """验证比例总和是否接近 1.0"""
        if not v:
            raise ValueError("entry_ratios 不能为空")
        total = sum(v)
        if abs(total - Decimal("1.0")) > Decimal("0.0001"):
            raise ValueError(f"entry_ratios 总和必须为 1.0，当前为 {total}")
        return v

    @field_validator('entry_batches')
    @classmethod
    def validate_batches_count(cls, v, info):
        """验证批次数量与比例列表长度一致"""
        # 注意：validation_info 在某些 pydantic 版本中可能不可用
        # 这里仅做基本验证
        if v < 2 or v > 5:
            raise ValueError("entry_batches 必须在 2-5 范围内")
        return v


# ============================================================
# DCA 状态追踪
# ============================================================
class DcaBatch(BaseModel):
    """单个批次的执行记录"""
    batch_index: int = Field(..., description="批次序号")
    order_type: str = Field(..., description="订单类型")
    ratio: Decimal = Field(..., description="资金比例")
    executed_qty: Optional[Decimal] = Field(default=None, description="已成交数量")
    executed_price: Optional[Decimal] = Field(default=None, description="成交价格")
    trigger_drop_percent: Optional[Decimal] = Field(default=None, description="触发跌幅")
    order_id: Optional[str] = Field(default=None, description="订单 ID (G-003 预埋单)")
    limit_price: Optional[Decimal] = Field(default=None, description="限价单价格 (G-003)")
    status: str = Field(default="pending", description="批次状态 (pending/placed/filled/cancelled)")


class DcaState(BaseModel):
    """DCA 批次建仓状态追踪"""
    signal_id: str = Field(..., description="关联的信号 ID")
    symbol: str = Field(..., description="币种对")
    direction: Direction = Field(..., description="方向")

    # 批次配置
    total_batches: int = Field(..., ge=2, le=5, description="总批次数量")
    entry_ratios: List[Decimal] = Field(..., description="各批次比例")
    place_all_orders_upfront: bool = Field(default=True, description="G-003 预埋单模式")
    total_amount: Decimal = Field(default=Decimal("0"), description="计划投入的总数量")

    # 执行状态
    executed_batches: List[DcaBatch] = Field(default_factory=list, description="已执行的批次")
    pending_batches: List[DcaBatch] = Field(default_factory=list, description="已挂出但未成交的订单")

    # 成本追踪
    total_executed_qty: Decimal = Field(default=Decimal("0"), description="累计成交数量")
    total_executed_value: Decimal = Field(default=Decimal("0"), description="累计成交金额")

    # 第一批成交价 (用于计算后续限价单价格)
    first_exec_price: Optional[Decimal] = Field(default=None, description="第一批成交价")

    # 元数据
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000), description="创建时间戳")
    updated_at: int = Field(default_factory=lambda: int(time.time() * 1000), description="更新时间戳")

    @property
    def average_cost(self) -> Decimal:
        """
        平均持仓成本 (平均成本法)

        公式：average_cost = total_executed_value / total_executed_qty
        """
        if self.total_executed_qty == Decimal("0"):
            return Decimal("0")
        return self.total_executed_value / self.total_executed_qty

    def calculate_batch_qty(self, ratio: Decimal) -> Decimal:
        """
        根据比例计算批次数量

        Args:
            ratio: 该批次的资金比例

        Returns:
            该批次应买入的数量
        """
        # 注意：total_amount 必须在执行前设置
        return self.total_amount * ratio

    def calculate_limit_price(self, batch_index: int, batch_trigger: DcaBatchTrigger) -> Optional[Decimal]:
        """
        计算限价单价格 (G-003 修复核心)

        基于第一批成交价计算绝对价格，提前预埋到交易所享受 Maker 费率

        多头公式：limit_price = first_exec_price * (1 + trigger_drop_percent/100)
        空头公式：limit_price = first_exec_price * (1 - trigger_drop_percent/100)

        Args:
            batch_index: 批次序号
            batch_trigger: 批次触发配置

        Returns:
            计算后的限价单价格，如果无法计算则返回 None
        """
        if self.first_exec_price is None:
            return None

        if batch_trigger.order_type != OrderType.LIMIT:
            return None

        if batch_trigger.trigger_drop_percent is None:
            return None

        # 计算限价单价格
        drop_ratio = batch_trigger.trigger_drop_percent / Decimal("100")

        if self.direction == Direction.LONG:
            # 多头：价格下跌时买入，所以用 1 + drop_ratio (drop_ratio 为负值)
            # 例如：first_exec_price=100, drop=-2%，则 limit_price = 100 * (1 - 0.02) = 98
            limit_price = self.first_exec_price * (Decimal("1") + drop_ratio)
        else:
            # 空头：价格上涨时卖出，所以用 1 - drop_ratio
            # 例如：first_exec_price=100, drop=-2%，则 limit_price = 100 * (1 + 0.02) = 102
            limit_price = self.first_exec_price * (Decimal("1") - drop_ratio)

        # 确保价格为正数
        if limit_price <= Decimal("0"):
            return None

        return limit_price.quantize(Decimal("0.01"))


# ============================================================
# 类型提示修复
# ============================================================
from typing import Literal

# 重建模型以解析前向引用
DcaConfig.model_rebuild()
DcaState.model_rebuild()


# ============================================================
# OrderManager 接口 (用于依赖注入)
# ============================================================
class OrderManagerProtocol:
    """
    OrderManager 协议接口

    用于 DCA 策略与订单管理器的解耦
    """

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        reduce_only: bool = False,
    ) -> str:
        """
        下市价单

        Returns:
            订单 ID
        """
        raise NotImplementedError

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        reduce_only: bool = False,
    ) -> str:
        """
        下降价单

        Returns:
            订单 ID
        """
        raise NotImplementedError


# ============================================================
# DCA 策略核心类
# ============================================================
class DcaStrategy:
    """
    DCA (Dollar-Cost Averaging) 分批建仓策略

    核心功能:
    1. 第一批市价单立即入场
    2. G-003 修复：第一批成交后，立即预埋第 2、3 批限价单到交易所
    3. 平均成本法计算持仓成本
    4. 批次状态追踪

    使用示例:
        config = DcaConfig(
            entry_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
            place_all_orders_upfront=True,
        )
        strategy = DcaStrategy(config)

        # 执行第一批
        first_qty = await strategy.execute_first_batch(symbol, total_amount)

        # 记录第一批成交价
        strategy.state.first_exec_price = Decimal("100")

        # 预埋所有限价单
        await strategy.place_all_limit_orders(order_manager)
    """

    def __init__(self, config: DcaConfig, signal_id: str, symbol: str, direction: Direction):
        """
        初始化 DCA 策略

        Args:
            config: DCA 配置
            signal_id: 关联的信号 ID
            symbol: 币种对
            direction: 方向 (LONG/SHORT)
        """
        self._config = config
        self._state = DcaState(
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            total_batches=config.entry_batches,
            entry_ratios=config.entry_ratios,
            place_all_orders_upfront=config.place_all_orders_upfront,
            total_amount=config.total_amount,
        )

        # 初始化批次触发配置
        self._init_batch_triggers()

    def _init_batch_triggers(self) -> None:
        """初始化批次触发配置"""
        if self._config.batch_triggers:
            # 使用用户自定义配置
            return

        # 自动生成默认配置
        batch_triggers = []
        for i, ratio in enumerate(self._config.entry_ratios):
            batch_index = i + 1
            if batch_index == 1:
                # 第一批：市价单
                batch_triggers.append(DcaBatchTrigger(
                    batch_index=batch_index,
                    order_type=OrderType.MARKET,
                    ratio=ratio,
                ))
            else:
                # 第 2-N 批：限价单，跌幅递增
                # 例如：第 2 批 -2%，第 3 批 -4%，第 4 批 -6%
                trigger_drop = Decimal("-2.0") * (batch_index - 1)
                batch_triggers.append(DcaBatchTrigger(
                    batch_index=batch_index,
                    order_type=OrderType.LIMIT,
                    ratio=ratio,
                    trigger_drop_percent=trigger_drop,
                ))

        self._config.batch_triggers = batch_triggers

    @property
    def state(self) -> DcaState:
        """获取当前状态"""
        return self._state

    @property
    def config(self) -> DcaConfig:
        """获取配置"""
        return self._config

    async def execute_first_batch(
        self,
        order_manager: OrderManagerProtocol,
        symbol: str,
        total_amount: Decimal,
    ) -> Decimal:
        """
        执行第一批市价单

        记录 first_exec_price 用于计算后续限价单价格

        Args:
            order_manager: 订单管理器
            symbol: 币种对
            total_amount: 计划投入的总数量

        Returns:
            第一批执行的订单 ID

        Raises:
            ValueError: 当第一批不是市价单时
        """
        # 更新总数量 (使用 copy_and_update 模式)
        self._state.total_amount = total_amount

        # 获取第一批配置
        first_trigger = self._config.batch_triggers[0]
        if first_trigger.order_type != OrderType.MARKET:
            raise ValueError("第一批必须是市价单 (MARKET)")

        # 计算第一批数量
        batch_qty = self._state.calculate_batch_qty(first_trigger.ratio)

        # 确定买卖方向
        side = "buy" if self._state.direction == Direction.LONG else "sell"

        # 下市价单
        order_id = await order_manager.place_market_order(
            symbol=symbol,
            side=side,
            qty=batch_qty,
            reduce_only=False,
        )

        # 记录批次状态
        batch = DcaBatch(
            batch_index=first_trigger.batch_index,
            order_type=OrderType.MARKET.value,
            ratio=first_trigger.ratio,
            order_id=order_id,
            status="placed",
        )
        self._state.executed_batches.append(batch)

        return order_id

    def record_first_execution(self, executed_qty: Decimal, executed_price: Decimal) -> None:
        """
        记录第一批成交信息

        Args:
            executed_qty: 成交数量
            executed_price: 成交价格
        """
        # 更新第一批状态
        if self._state.executed_batches:
            first_batch = self._state.executed_batches[0]
            first_batch.executed_qty = executed_qty
            first_batch.executed_price = executed_price
            first_batch.status = "filled"

        # 更新状态
        self._state.first_exec_price = executed_price
        self._state.total_executed_qty = executed_qty
        self._state.total_executed_value = executed_qty * executed_price
        self._state.updated_at = int(time.time() * 1000)

    async def place_all_limit_orders(
        self,
        order_manager: OrderManagerProtocol,
    ) -> List[Dict[str, Any]]:
        """
        G-003 修复：提前预埋所有限价单

        第一批成交后，立即计算第 2、3 批的绝对限价
        一次性挂出到交易所，享受 Maker 费率

        Args:
            order_manager: 订单管理器

        Returns:
            已挂出的限价单列表，每项包含 {"batch_index": int, "order_id": str, "limit_price": Decimal}

        Raises:
            ValueError: 当 first_exec_price 未设置时
        """
        if self._state.first_exec_price is None:
            raise ValueError("必须先记录第一批成交价 (first_exec_price)")

        if not self._config.place_all_orders_upfront:
            # 如果不启用预埋单模式，返回空列表
            return []

        placed_orders = []

        # 从第 2 批开始遍历
        for i in range(1, len(self._config.batch_triggers)):
            batch_trigger = self._config.batch_triggers[i]

            # 计算限价单价格
            limit_price = self._state.calculate_limit_price(
                batch_trigger.batch_index,
                batch_trigger
            )

            if limit_price is None:
                continue

            # 计算批次数量
            batch_qty = self._state.calculate_batch_qty(batch_trigger.ratio)

            # 确定买卖方向
            side = "buy" if self._state.direction == Direction.LONG else "sell"

            # 下降价单
            order_id = await order_manager.place_limit_order(
                symbol=self._state.symbol,
                side=side,
                qty=batch_qty,
                price=limit_price,
                reduce_only=False,
            )

            # 记录批次状态
            batch = DcaBatch(
                batch_index=batch_trigger.batch_index,
                order_type=OrderType.LIMIT.value,
                ratio=batch_trigger.ratio,
                order_id=order_id,
                limit_price=limit_price,
                trigger_drop_percent=batch_trigger.trigger_drop_percent,
                status="placed",
            )
            self._state.pending_batches.append(batch)

            placed_orders.append({
                "batch_index": batch_trigger.batch_index,
                "order_id": order_id,
                "limit_price": limit_price,
            })

        return placed_orders

    def calculate_limit_price(self, batch_index: int) -> Optional[Decimal]:
        """
        计算限价单价格 (公共方法)

        Args:
            batch_index: 批次序号

        Returns:
            计算后的限价单价格
        """
        if self._state.first_exec_price is None:
            return None

        # 找到对应的批次触发配置
        for trigger in self._config.batch_triggers:
            if trigger.batch_index == batch_index:
                return self._state.calculate_limit_price(batch_index, trigger)

        return None

    def record_batch_execution(
        self,
        batch_index: int,
        executed_qty: Decimal,
        executed_price: Decimal,
    ) -> None:
        """
        记录批次成交信息

        Args:
            batch_index: 批次序号
            executed_qty: 成交数量
            executed_price: 成交价格
        """
        # 尝试从 pending 移动到 executed
        moved = False
        for i, batch in enumerate(self._state.pending_batches):
            if batch.batch_index == batch_index:
                batch.executed_qty = executed_qty
                batch.executed_price = executed_price
                batch.status = "filled"
                self._state.pending_batches.pop(i)
                self._state.executed_batches.append(batch)
                moved = True
                break

        # 如果批次不在 pending 中，直接创建 executed 记录（用于测试或直接执行场景）
        if not moved:
            # 找到对应的批次触发配置
            trigger = None
            for t in self._config.batch_triggers:
                if t.batch_index == batch_index:
                    trigger = t
                    break

            if trigger:
                batch = DcaBatch(
                    batch_index=batch_index,
                    order_type=trigger.order_type.value,
                    ratio=trigger.ratio,
                    executed_qty=executed_qty,
                    executed_price=executed_price,
                    status="filled",
                )
                self._state.executed_batches.append(batch)

        # 更新累计成本
        self._state.total_executed_qty += executed_qty
        self._state.total_executed_value += executed_qty * executed_price
        self._state.updated_at = int(time.time() * 1000)

    def get_average_cost(self) -> Decimal:
        """
        获取平均持仓成本

        Returns:
            平均成本价格
        """
        return self._state.average_cost

    def is_completed(self) -> bool:
        """
        检查 DCA 策略是否已完成

        Returns:
            True 表示所有批次已执行完毕
        """
        return len(self._state.executed_batches) == self._config.entry_batches

    def get_execution_summary(self) -> Dict[str, Any]:
        """
        获取执行摘要

        Returns:
            执行摘要字典
        """
        return {
            "signal_id": self._state.signal_id,
            "symbol": self._state.symbol,
            "direction": self._state.direction.value,
            "total_batches": self._config.entry_batches,
            "executed_batches": len(self._state.executed_batches),
            "pending_batches": len(self._state.pending_batches),
            "total_executed_qty": str(self._state.total_executed_qty),
            "total_executed_value": str(self._state.total_executed_value),
            "average_cost": str(self._state.average_cost),
            "first_exec_price": str(self._state.first_exec_price) if self._state.first_exec_price else None,
            "is_completed": self.is_completed(),
        }
