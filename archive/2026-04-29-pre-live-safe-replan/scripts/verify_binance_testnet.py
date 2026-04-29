#!/usr/bin/env python3
"""
P0-005-1: Binance Testnet 连接与基础接口验证脚本

验证项目与 Binance Testnet 的连接和基础 API 接口兼容性
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.infrastructure.exchange_gateway import ExchangeGateway
from src.application.config_manager import load_all_configs


# ANSI 颜色代码
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(title: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")


def print_success(msg: str):
    print(f"{Colors.GREEN}✓{Colors.RESET} {msg}")


def print_error(msg: str):
    print(f"{Colors.RED}✗{Colors.RESET} {msg}")


def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {msg}")


async def verify_binance_testnet():
    """验证 Binance Testnet 连接与基础接口"""

    results = {
        "connection": False,
        "balance": False,
        "ticker": False,
        "market_order": False,
        "limit_order": False,
        "order_status": False,
        "cancel_order": False,
        "issues": []
    }

    # ========== Step 1: 加载配置 ==========
    print_header("Step 1: 加载配置文件")

    try:
        config = load_all_configs()
        api_key = config.user_config.exchange.api_key
        api_secret = config.user_config.exchange.api_secret
        testnet = config.user_config.exchange.testnet

        print_success(f"配置加载成功")
        print(f"  - 交易所：{config.user_config.exchange.name}")
        print(f"  - 测试网：{testnet}")
        print(f"  - API Key: {api_key[:8]}...{api_key[-8:]}")

    except Exception as e:
        print_error(f"配置加载失败：{e}")
        results["issues"].append(f"配置加载失败：{e}")
        return results

    # ========== Step 2: 初始化交易所网关 ==========
    print_header("Step 2: 初始化交易所网关")

    gateway = None
    try:
        gateway = ExchangeGateway(
            exchange_name="binance",
            api_key=api_key,
            api_secret=api_secret,
            testnet=True
        )

        print("正在连接 Binance Testnet...")
        await gateway.initialize()
        print_success("交易所网关初始化成功")
        results["connection"] = True

    except Exception as e:
        print_error(f"交易所网关初始化失败：{e}")
        results["issues"].append(f"交易所初始化失败：{e}")
        return results

    # ========== Step 3: 验证账户余额查询 ==========
    print_header("Step 3: 验证账户余额查询")

    try:
        print("正在查询账户余额...")
        snapshot = await gateway.fetch_account_balance()

        if snapshot:
            print_success(f"账户余额查询成功")
            print(f"  - 总权益：{snapshot.total_balance} USDT")
            print(f"  - 可用余额：{snapshot.available_balance} USDT")
            print(f"  - 未实现盈亏：{snapshot.unrealized_pnl} USDT")
            results["balance"] = True
        else:
            print_warning("账户余额查询返回空值")
            results["issues"].append("账户余额查询返回空值")

    except Exception as e:
        print_error(f"账户余额查询失败：{e}")
        results["issues"].append(f"余额查询失败：{e}")

    # ========== Step 4: 验证 ticker 价格查询 ==========
    print_header("Step 4: 验证 ticker 价格查询")

    try:
        symbol = "BTC/USDT:USDT"
        print(f"正在查询 {symbol} 价格...")
        price = await gateway.fetch_ticker_price(symbol)

        if price and price > 0:
            print_success(f"Ticker 价格查询成功")
            print(f"  - {symbol} = {price} USDT")
            results["ticker"] = True
        else:
            print_error("Ticker 价格查询返回无效值")
            results["issues"].append("Ticker 价格查询返回无效值")

    except Exception as e:
        print_error(f"Ticker 价格查询失败：{e}")
        results["issues"].append(f"Ticker 查询失败：{e}")

    # ========== Step 5: 验证市价单下单 ==========
    print_header("Step 5: 验证市价单下单")

    market_exchange_order_id = None

    try:
        symbol = "BTC/USDT:USDT"
        # Binance 最小名义价值 100 USDT，使用 0.002 BTC (≈140 USDT)
        amount = Decimal("0.002")

        print(f"市价单测试：买入 {amount} BTC (≈{amount * Decimal('69000')} USDT)")
        print(f"{Colors.YELLOW}注意：测试网可能不允许真实下单，此处仅验证接口连通性{Colors.RESET}")
        print(f"{Colors.YELLOW}注意：Binance 最小名义价值要求 100 USDT{Colors.RESET}")

        result = await gateway.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=amount,
            reduce_only=False
        )

        if result.is_success:
            print_success(f"市价单下单成功")
            print(f"  - 订单 ID (系统): {result.order_id}")
            print(f"  - 订单 ID (交易所): {result.exchange_order_id}")
            print(f"  - 状态：{result.status}")
            print(f"  - 价格：{result.price}")
            results["market_order"] = True

            # 保存交易所订单 ID 用于后续查询测试
            market_exchange_order_id = result.exchange_order_id

            # 市价单通常立即成交，不需要取消
            print(f"  - 市价单已成交，无需取消")
        else:
            print_error(f"市价单下单失败：{result.error_message}")
            results["issues"].append(f"市价单下单失败：{result.error_message}")

    except Exception as e:
        print_error(f"市价单下单异常：{e}")
        results["issues"].append(f"市价单异常：{e}")

    # ========== Step 6: 验证限价单下单 + 取消 ==========
    print_header("Step 6: 验证限价单下单 + 取消")

    limit_exchange_order_id = None

    try:
        symbol = "BTC/USDT:USDT"
        # Binance 最小名义价值 100 USDT，使用 0.002 BTC
        amount = Decimal("0.002")

        # 获取当前价格
        current_price = await gateway.fetch_ticker_price(symbol)
        limit_price = current_price * Decimal("0.95")  # 低于市价 5%

        print(f"限价单测试：买入 {amount} BTC @ {limit_price} USDT")
        print(f"(市价：{current_price} USDT, 名义价值≈{amount * limit_price} USDT)")

        result = await gateway.place_order(
            symbol=symbol,
            order_type="limit",
            side="buy",
            amount=amount,
            price=limit_price,
            reduce_only=False
        )

        if result.is_success:
            print_success(f"限价单下单成功")
            print(f"  - 订单 ID (系统): {result.order_id}")
            print(f"  - 订单 ID (交易所): {result.exchange_order_id}")
            print(f"  - 状态：{result.status}")
            results["limit_order"] = True

            # 保存交易所订单 ID 用于取消测试
            limit_exchange_order_id = result.exchange_order_id

            # 取消限价单
            print("正在取消限价单...")
            cancel_result = await gateway.cancel_order(limit_exchange_order_id, symbol)

            if cancel_result.is_success:
                print_success(f"限价单已取消")
                results["cancel_order"] = True
            else:
                print_error(f"限价单取消失败：{cancel_result.error_message}")
                results["issues"].append(f"限价单取消失败：{cancel_result.error_message}")
        else:
            print_error(f"限价单下单失败：{result.error_message}")
            results["issues"].append(f"限价单下单失败：{result.error_message}")

    except Exception as e:
        print_error(f"限价单下单异常：{e}")
        results["issues"].append(f"限价单异常：{e}")

    # ========== Step 7: 验证订单状态查询 ==========
    print_header("Step 7: 验证订单状态查询")

    # 使用市价单的交易所订单 ID 查询（如果存在）
    if market_exchange_order_id:
        try:
            symbol = "BTC/USDT:USDT"
            print(f"查询市价单状态：{market_exchange_order_id}")

            order = await gateway.fetch_order(market_exchange_order_id, symbol)

            if order:
                print_success(f"订单状态查询成功")
                print(f"  - 订单 ID: {order.order_id}")
                print(f"  - 交易所订单 ID: {order.exchange_order_id}")
                print(f"  - 状态：{order.status}")
                print(f"  - 类型：{order.order_type}")
                print(f"  - 数量：{order.amount}")
                print(f"  - 价格：{order.price}")
                results["order_status"] = True
            else:
                print_error("订单状态查询返回空值")
                results["issues"].append("订单状态查询返回空值")

        except Exception as e:
            print_error(f"订单状态查询异常：{e}")
            results["issues"].append(f"订单状态查询异常：{e}")
    else:
        print_warning("没有可用的订单 ID，跳过的订单状态查询测试")
        results["issues"].append("没有可用的订单 ID 进行测试")

    # ========== 汇总报告 ==========
    print_header("验证报告汇总")

    checks = [
        ("连接状态", results["connection"]),
        ("账户余额查询", results["balance"]),
        ("Ticker 价格查询", results["ticker"]),
        ("市价单下单", results["market_order"]),
        ("限价单下单", results["limit_order"]),
        ("订单状态查询", results["order_status"]),
        ("订单取消", results["cancel_order"]),
    ]

    passed = 0
    failed = 0

    for name, success in checks:
        if success:
            print_success(name)
            passed += 1
        else:
            print_error(name)
            failed += 1

    print(f"\n{Colors.BOLD}测试结果：{passed}/{len(checks)} 通过{Colors.RESET}")

    if results["issues"]:
        print(f"\n{Colors.YELLOW}问题清单:{Colors.RESET}")
        for i, issue in enumerate(results["issues"], 1):
            print(f"  {i}. {issue}")

    return results


async def main():
    """主函数"""
    print(f"\n{Colors.BOLD}P0-005-1: Binance Testnet 连接与基础接口验证{Colors.RESET}")
    print(f"执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        results = await verify_binance_testnet()

        # 退出码
        if all([
            results["connection"],
            results["balance"],
            results["ticker"],
            results["market_order"],
            results["limit_order"],
            results["order_status"],
            results["cancel_order"],
        ]):
            print(f"\n{Colors.GREEN}所有验证通过！{Colors.RESET}\n")
            sys.exit(0)
        else:
            print(f"\n{Colors.YELLOW}部分验证未通过，请检查问题清单{Colors.RESET}\n")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}执行异常：{e}{Colors.RESET}\n")
        sys.exit(1)
    finally:
        # 确保网关被关闭
        if 'gateway' in locals():
            try:
                await gateway.close()
            except:
                pass


if __name__ == "__main__":
    asyncio.run(main())
