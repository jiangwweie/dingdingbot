"""
Account Service - 账户服务接口

P0 修复：将 AccountService 从 capital_protection.py 移到独立模块，避免循环依赖。
"""
from decimal import Decimal
from typing import TYPE_CHECKING

# Avoid circular imports
if TYPE_CHECKING:
    from src.infrastructure.exchange_gateway import ExchangeGateway


class AccountService:
    """
    账户服务接口（用于解耦）

    实际使用时，应该注入真实的账户服务实现
    """

    async def get_balance(self) -> Decimal:
        """
        获取可用余额

        Returns:
            Decimal: 可用余额 (USDT)
        """
        raise NotImplementedError("Subclasses must implement get_balance")


class BinanceAccountService(AccountService):
    """
    基于 ExchangeGateway 的真实账户服务实现

    用于全链路集成测试和生产环境
    """

    def __init__(self, gateway: "ExchangeGateway"):
        """
        初始化账户服务

        Args:
            gateway: ExchangeGateway 实例
        """
        self._gateway = gateway

    async def get_balance(self) -> Decimal:
        """
        获取 USDT 可用余额

        Returns:
            Decimal: USDT 可用余额
        """
        balance = await self._gateway.rest_exchange.fetch_balance()
        usdt_balance = balance.get("USDT", {})
        # 返回可用余额（free），而非总余额（total）
        return Decimal(str(usdt_balance.get("free", 0)))
