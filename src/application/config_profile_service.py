"""
Config Profile Service - legacy config-domain profile management.

配置 Profile 管理服务：支持 Profile 的创建、切换、删除、导出/导入等操作。

边界说明：
- 该服务管理的是 SQLite 配置域中的 KV Profile（config_profiles / config_entries）。
- 它不是 Sim-1 runtime freeze 的真源；当前 runtime 真源是 runtime_profiles
  + RuntimeConfigResolver 在启动期解析出的 ResolvedRuntimeConfig。
- 因此这里的 switch/activate 语义应理解为“更新配置域 active profile”，默认对后续
  启动或显式 reload 生效，而不是静默热切当前 execution runtime。
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import yaml
import logging

from src.infrastructure.config_profile_repository import ConfigProfileRepository, ProfileInfo
from src.infrastructure.config_entry_repository import ConfigEntryRepository
from src.domain.exceptions import FatalStartupError

logger = logging.getLogger(__name__)


class ProfileDiff:
    """Profile 差异对比结果"""

    def __init__(
        self,
        from_profile: str,
        to_profile: str,
        diff: Dict[str, Dict[str, Dict[str, Any]]],
        total_changes: int,
    ):
        self.from_profile = from_profile
        self.to_profile = to_profile
        self.diff = diff  # {category: {key: {"old": ..., "new": ...}}}
        self.total_changes = total_changes

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "from_profile": self.from_profile,
            "to_profile": self.to_profile,
            "diff": self.diff,
            "total_changes": self.total_changes,
        }


class ConfigProfileService:
    """
    Service layer for legacy config-domain profile management.

    核心功能:
    - Profile 列表查询
    - 创建 Profile (支持从现有配置复制)
    - 切换 Profile (带差异预览)
    - 删除 Profile
    - 导出 Profile (YAML)
    - 导入 Profile (YAML)
    """

    def __init__(
        self,
        profile_repository: ConfigProfileRepository,
        config_repository: ConfigEntryRepository,
        config_manager: Optional[Any] = None,  # ConfigManager for cache refresh
    ):
        """
        Initialize ConfigProfileService.

        Args:
            profile_repository: Profile 数据仓库
            config_repository: 配置项数据仓库
            config_manager: ConfigManager 实例（用于缓存刷新，可选）
        """
        self.profile_repository = profile_repository
        self.config_repository = config_repository
        self.config_manager = config_manager  # May be None in some contexts

    async def list_profiles(self) -> List[ProfileInfo]:
        """
        获取所有 Profile 列表

        Returns:
            ProfileInfo 列表
        """
        return await self.profile_repository.list_profiles()

    async def get_profile(self, name: str) -> Optional[ProfileInfo]:
        """
        获取单个 Profile 详情

        Args:
            name: Profile 名称

        Returns:
            ProfileInfo 或 None
        """
        return await self.profile_repository.get_profile(name)

    async def get_active_profile(self) -> Optional[ProfileInfo]:
        """
        获取当前激活的 Profile

        Returns:
            激活的 ProfileInfo 或 None
        """
        return await self.profile_repository.get_active_profile()

    async def create_profile(
        self,
        name: str,
        description: Optional[str] = None,
        copy_from: Optional[str] = None,
        switch_immediately: bool = False,
    ) -> ProfileInfo:
        """
        创建新的 Profile

        Args:
            name: Profile 名称
            description: 描述
            copy_from: 从中复制配置的源 Profile 名称
            switch_immediately: 创建后是否立即切换

        Returns:
            创建的 ProfileInfo

        Raises:
            ValueError: 名称已存在或源 Profile 不存在
        """
        # 创建 Profile
        profile = await self.profile_repository.create_profile(
            name=name,
            description=description,
            copy_from=copy_from,
        )

        # 如果需要立即切换
        if switch_immediately:
            await self.profile_repository.activate_profile(name)

        return profile

    async def switch_profile(self, name: str) -> ProfileDiff:
        """
        切换到指定的配置域 Profile

        Args:
            name: Profile 名称

        Returns:
            差异对比结果（针对 config_entries 配置域）

        Raises:
            ValueError: Profile 不存在
        """
        # 获取当前激活的 Profile
        current = await self.profile_repository.get_active_profile()
        current_name = current.name if current else "default"

        # 计算差异
        diff = await self._calculate_profile_diff(current_name, name)

        # 执行切换
        await self.profile_repository.activate_profile(name)

        # 新增：通知 ConfigManager 刷新缓存（如果已注入）
        if self.config_manager is not None:
            try:
                await self.config_manager.reload_all_configs_from_db()
                logger.info(f"ConfigProfileService: Cache refreshed after switching to profile '{name}'")
            except Exception as e:
                logger.error(f"Failed to refresh config cache after profile switch: {e}")

        return diff

    async def _calculate_profile_diff(
        self,
        from_name: str,
        to_name: str,
    ) -> ProfileDiff:
        """
        计算两个 Profile 之间的差异

        Args:
            from_name: 源 Profile 名称
            to_name: 目标 Profile 名称

        Returns:
            ProfileDiff 结果
        """
        # 获取两个 Profile 的配置
        from_configs = await self.profile_repository.get_profile_configs(from_name)
        to_configs = await self.profile_repository.get_profile_configs(to_name)

        # 合并所有 key
        all_keys = set(from_configs.keys()) | set(to_configs.keys())

        # 分类映射 (config_key -> category)
        def get_category(key: str) -> str:
            if key.startswith("strategy."):
                return "strategy"
            elif key.startswith("risk."):
                return "risk"
            elif key.startswith("exchange."):
                return "exchange"
            else:
                return "other"

        # 计算差异
        diff: Dict[str, Dict[str, Dict[str, Any]]] = {}
        total_changes = 0

        for key in all_keys:
            from_value = from_configs.get(key)
            to_value = to_configs.get(key)

            # 跳过相同的配置
            if from_value == to_value:
                continue

            category = get_category(key)
            if category not in diff:
                diff[category] = {}

            diff[category][key] = {
                "old": self._format_value(from_value),
                "new": self._format_value(to_value),
            }
            total_changes += 1

        return ProfileDiff(
            from_profile=from_name,
            to_profile=to_name,
            diff=diff,
            total_changes=total_changes,
        )

    def _format_value(self, value: Any) -> str:
        """格式化配置值用于显示"""
        if value is None:
            return "(未配置)"
        elif isinstance(value, bool):
            return "开启" if value else "关闭"
        elif isinstance(value, (int, float)):
            # 百分比字段
            if "percent" in str(value).lower():
                return f"{value}%"
            return str(value)
        elif isinstance(value, list):
            return f"[{', '.join(map(str, value))}]"
        else:
            return str(value)

    async def delete_profile(self, name: str) -> bool:
        """
        删除 Profile

        Args:
            name: Profile 名称

        Returns:
            True 如果删除成功

        Raises:
            ValueError: 不能删除 default 或当前激活的 Profile
        """
        return await self.profile_repository.delete_profile(name)

    async def rename_profile(
        self,
        old_name: str,
        new_name: str,
        description: Optional[str] = None,
    ) -> ProfileInfo:
        """
        重命名 Profile

        Args:
            old_name: 原 Profile 名称
            new_name: 新 Profile 名称
            description: 新描述（可选）

        Returns:
            重命名后的 ProfileInfo

        Raises:
            ValueError: 名称冲突或不能重命名为 default
        """
        # 边界检查：不能重命名为 default
        if new_name == "default":
            raise ValueError("不能重命名为 'default'")

        # 验证原 Profile 存在
        old_profile = await self.profile_repository.get_profile(old_name)
        if not old_profile:
            raise ValueError(f"Profile '{old_name}' 不存在")

        # 检查新名称是否已被占用（排除自身）
        existing = await self.profile_repository.get_profile(new_name)
        if existing and existing.name != old_name:
            raise ValueError(f"Profile '{new_name}' 已存在")

        # 执行重命名
        return await self.profile_repository.rename_profile(
            old_name, new_name, description
        )

    async def export_profile_yaml(self, profile_name: str) -> str:
        """
        导出 Profile 为 YAML 格式

        Args:
            profile_name: Profile 名称

        Returns:
            YAML 字符串

        Raises:
            ValueError: Profile 不存在
        """
        # 验证 Profile 存在
        profile = await self.profile_repository.get_profile(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' 不存在")

        # 获取配置
        configs = await self.profile_repository.get_profile_configs(profile_name)

        # 组织为嵌套结构
        def organize_configs(configs: Dict[str, Any]) -> Dict[str, Any]:
            """将 flat configs 组织为嵌套结构"""
            from decimal import Decimal

            result: Dict[str, Any] = {}
            for key, value in configs.items():
                parts = key.split(".")
                current = result
                for i, part in enumerate(parts[:-1]):
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                # 转换 Decimal 为 float 以便 YAML 序列化
                if isinstance(value, Decimal):
                    value = float(value)
                current[parts[-1]] = value
            return result

        nested_configs = organize_configs(configs)

        # 构建 YAML 文档
        now = datetime.now(timezone.utc).isoformat()
        yaml_data = {
            "profile": {
                "name": profile_name,
                "description": profile.description,
                "exported_at": now,
            },
            **nested_configs,
        }

        # 序列化为 YAML
        yaml_str = yaml.dump(
            yaml_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        return yaml_str

    async def import_profile_yaml(
        self,
        yaml_content: str,
        profile_name: Optional[str] = None,
        mode: str = "create",
    ) -> Tuple[ProfileInfo, int]:
        """
        从 YAML 导入 Profile

        Args:
            yaml_content: YAML 内容
            profile_name: 指定 Profile 名称（可选）
            mode: 导入模式 ("create" | "overwrite")

        Returns:
            (ProfileInfo, 导入的配置项数量)

        Raises:
            ValueError: YAML 格式无效或 Profile 名称冲突
        """
        # 解析 YAML
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML 格式无效：{e}")

        if not isinstance(data, dict):
            raise ValueError("YAML 根元素必须是字典")

        # 提取 Profile 信息
        profile_data = data.get("profile", {})
        if profile_name is None:
            profile_name = profile_data.get("name", "imported")

        # 验证名称
        if not profile_name or len(profile_name) > 32:
            raise ValueError("Profile 名称长度为 1-32 个字符")

        # 检查名称冲突
        existing = await self.profile_repository.get_profile(profile_name)
        if existing and mode == "create":
            raise ValueError(f"Profile '{profile_name}' 已存在")

        # 提取配置项（移除 profile 字段）
        configs = {k: v for k, v in data.items() if k != "profile"}

        # 扁平化配置
        def flatten(d: Dict[str, Any], parent_key: str = "") -> Dict[str, Any]:
            items = []
            for k, v in d.items():
                new_key = f"{parent_key}.{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten(v, new_key).items())
                else:
                    items.append((new_key, v))
            return dict(items)

        flat_configs = flatten(configs)

        # 创建或覆盖 Profile
        if mode == "overwrite" and existing:
            # 删除现有配置
            await self.config_repository.delete_entries_by_prefix("")
            # 更新 Profile 描述
            # TODO: 需要添加更新方法
        else:
            # 创建新 Profile
            await self.profile_repository.create_profile(
                name=profile_name,
                description=profile_data.get("description"),
                copy_from=None,
            )

        # 保存配置项
        count = 0
        for key, value in flat_configs.items():
            await self.config_repository.upsert_entry(key, value)
            count += 1

        profile = await self.profile_repository.get_profile(profile_name)
        return profile, count
