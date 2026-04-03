"""
Pytest 配置文件 - 集成测试专用
"""

import pytest

# 为 test_order_chain_api.py 禁用 asyncio 模式
# 这个文件使用同步 TestClient，需要跳过 pytest-asyncio 的事件循环管理
def pytest_collection_modifyitems(config, items):
    """根据文件名动态设置 asyncio 模式"""
    for item in items:
        if "test_order_chain_api" in str(item.fspath):
            # 为 test_order_chain_api.py 的所有测试禁用 asyncio
            item.add_marker(pytest.mark.asyncio_mode("strict"))