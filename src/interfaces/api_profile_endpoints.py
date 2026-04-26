
# ============================================================
# 配置域 Profile 管理 API (legacy config domain)
# Reference: docs/products/config-profile-management-prd.md
#
# 说明：
# - 该组端点服务的是旧配置域（config_profiles / config_entries）。
# - 它不是 Sim-1 runtime freeze 的真源入口。
# - 当前 runtime 真源是 runtime_profiles + RuntimeConfigResolver 在启动期
#   解析出的 ResolvedRuntimeConfig。
# ============================================================

from src.infrastructure.config_profile_repository import ConfigProfileRepository
from src.application.config_profile_service import ConfigProfileService, ProfileDiff
from pydantic import BaseModel, Field
from typing import Optional

# Profile 管理 Pydantic 模型
class ProfileCreateRequest(BaseModel):
    """创建 Profile 请求"""
    name: str = Field(..., description="Profile 名称 (1-32 字符)")
    description: Optional[str] = Field(None, description="描述 (0-100 字符)")
    copy_from: Optional[str] = Field(None, description="源 Profile 名称（复制配置）")
    switch_immediately: bool = Field(False, description="创建后是否立即在配置域中激活（不影响当前已冻结的 runtime）")


class ProfileCreateResponse(BaseModel):
    """创建 Profile 响应"""
    status: str
    profile: dict
    message: str


class ProfileListResponse(BaseModel):
    """Profile 列表响应"""
    profiles: list
    total: int
    active_profile: Optional[str] = None


class ProfileSwitchRequest(BaseModel):
    """切换 Profile 请求"""
    name: str = Field(..., description="Profile 名称")
    confirm: bool = Field(False, description="必须显式确认切换，避免误操作污染 runtime freeze")


class ProfileSwitchResponse(BaseModel):
    """切换 Profile 响应"""
    status: str
    profile: dict
    diff: dict
    message: str


class ProfileDeleteResponse(BaseModel):
    """删除 Profile 响应"""
    status: str
    message: str


class ProfileExportResponse(BaseModel):
    """导出 Profile 响应"""
    status: str
    profile_name: str
    yaml_content: str


class ProfileImportRequest(BaseModel):
    """导入 Profile 请求"""
    yaml_content: str = Field(..., description="YAML 内容")
    profile_name: Optional[str] = Field(None, description="指定 Profile 名称")
    mode: str = Field("create", description="导入模式：create | overwrite")


class ProfileImportResponse(BaseModel):
    """导入 Profile 响应"""
    status: str
    profile: dict
    imported_count: int
    message: str


# ------------------------------------------------------------
# Profile Repository 和 Service 初始化
# ------------------------------------------------------------
_profile_repository: Optional[ConfigProfileRepository] = None
_profile_service: Optional[ConfigProfileService] = None
_config_manager: Optional[Any] = None  # ConfigManager for cache refresh


def set_profile_dependencies(
    profile_repository: Optional[ConfigProfileRepository] = None,
    config_manager: Optional[Any] = None,
):
    """Inject dependencies for profile endpoints."""
    global _profile_repository, _profile_service, _config_manager
    _profile_repository = profile_repository
    _config_manager = config_manager
    _profile_service = None  # Reset service to force re-initialization


def _get_profile_repository() -> ConfigProfileRepository:
    """Get profile repository or raise error if not initialized."""
    global _profile_repository
    if _profile_repository is None:
        _profile_repository = ConfigProfileRepository()
        # 注意：Repository 的 initialize 需要在应用启动时调用
    return _profile_repository


def _get_config_manager() -> Optional[Any]:
    """Get ConfigManager or None."""
    return _config_manager


def _get_profile_service() -> ConfigProfileService:
    """Get profile service or raise error if not initialized."""
    global _profile_service
    if _profile_service is None:
        repo = _get_profile_repository()
        from src.infrastructure.config_entry_repository import ConfigEntryRepository
        config_repo = ConfigEntryRepository()
        config_manager = _get_config_manager()
        _profile_service = ConfigProfileService(repo, config_repo, config_manager)
    return _profile_service


# ------------------------------------------------------------
# Profile Management Endpoints
# ------------------------------------------------------------

@app.get("/api/config/profiles", response_model=ProfileListResponse)
async def list_profiles():
    """
    获取所有配置域 Profile 列表

    Returns:
        Profile 列表，包含激活状态标识

    说明：
        这里的 Profile 属于旧配置域，不是 runtime profile。
    """
    try:
        service = _get_profile_service()
        profiles = await service.list_profiles()

        # 获取当前激活的 Profile
        active = await service.get_active_profile()

        return ProfileListResponse(
            profiles=[p.to_dict() for p in profiles],
            total=len(profiles),
            active_profile=active.name if active else None,
        )
    except Exception as e:
        logger.error(f"获取 Profile 列表失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/profiles/{name}", response_model=dict)
async def get_profile(name: str):
    """
    获取单个配置域 Profile 详情

    Args:
        name: Profile 名称

    Returns:
        Profile 详情
    """
    try:
        service = _get_profile_service()
        profile = await service.get_profile(name)

        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")

        return profile.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 Profile 详情失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/profiles", response_model=ProfileCreateResponse)
async def create_profile(request: ProfileCreateRequest):
    """
    创建新的配置域 Profile

    Args:
        name: Profile 名称 (1-32 字符)
        description: 描述 (可选)
        copy_from: 源 Profile 名称（复制配置，可选）
        switch_immediately: 创建后是否立即切换

    Returns:
        创建的 Profile 信息

    说明：
        这里只会更新旧配置域，不会直接改动当前已冻结的 execution runtime。
    """
    try:
        service = _get_profile_service()

        # 名称验证
        if not request.name or len(request.name) > 32:
            raise HTTPException(status_code=400, detail="Profile 名称长度为 1-32 个字符")

        # 创建 Profile
        profile = await service.create_profile(
            name=request.name,
            description=request.description,
            copy_from=request.copy_from,
            switch_immediately=request.switch_immediately,
        )

        return ProfileCreateResponse(
            status="success",
            profile=profile.to_dict(),
            message=f"Profile '{request.name}' 创建成功",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/profiles/{name}/activate", response_model=ProfileSwitchResponse)
async def switch_profile(name: str, confirm: bool = Query(False, description="必须显式确认切换，避免误操作污染 runtime freeze")):
    """
    切换到指定的配置 Profile（带差异预览）

    Args:
        name: Profile 名称
        confirm: 必须为 True 才执行切换，否则返回 409

    Returns:
        切换结果和配置差异

    说明：
        该接口更新的是旧配置域中的 active profile。
        对当前已经启动并冻结的 execution runtime，默认应视为
        “下次启动 / 显式 reload 流程生效”，而不是静默热切当前进程。
    """
    if not confirm:
        raise HTTPException(
            status_code=409,
            detail="Profile 切换需要显式确认：请设置 confirm=true 参数以确认切换操作",
        )

    try:
        service = _get_profile_service()

        # 验证 Profile 存在
        profile = await service.get_profile(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")

        # 执行切换（返回差异）
        diff = await service.switch_profile(name)

        return ProfileSwitchResponse(
            status="success",
            profile=profile.to_dict(),
            diff=diff.to_dict(),
            message=f"已切换配置域 Profile '{name}'（下次启动或显式 reload 生效，不影响当前 runtime），共 {diff.total_changes} 项配置变更",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"切换 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/config/profiles/{name}", response_model=ProfileDeleteResponse)
async def delete_profile(name: str):
    """
    删除配置 Profile

    Args:
        name: Profile 名称

    Returns:
        删除结果

    Raises:
        HTTPException:
            - 400: 不能删除 default 或当前激活的 Profile
            - 404: Profile 不存在
    """
    try:
        service = _get_profile_service()

        # 验证 Profile 存在
        profile = await service.get_profile(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")

        # 执行删除
        success = await service.delete_profile(name)

        return ProfileDeleteResponse(
            status="success",
            message=f"Profile '{name}' 已删除",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/profiles/{name}/export", response_model=ProfileExportResponse)
async def export_profile(name: str):
    """
    导出配置 Profile 为 YAML 格式

    Args:
        name: Profile 名称

    Returns:
        YAML 格式的配置内容
    """
    try:
        service = _get_profile_service()

        # 验证 Profile 存在
        profile = await service.get_profile(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")

        # 导出 YAML
        yaml_content = await service.export_profile_yaml(name)

        return ProfileExportResponse(
            status="success",
            profile_name=name,
            yaml_content=yaml_content,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导出 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/profiles/import", response_model=ProfileImportResponse)
async def import_profile(request: ProfileImportRequest):
    """
    从 YAML 导入配置 Profile

    Args:
        yaml_content: YAML 格式的配置内容
        profile_name: 指定 Profile 名称（可选）
        mode: 导入模式（create | overwrite）

    Returns:
        导入结果
    """
    try:
        service = _get_profile_service()

        # 导入 YAML
        profile, count = await service.import_profile_yaml(
            yaml_content=request.yaml_content,
            profile_name=request.profile_name,
            mode=request.mode,
        )

        return ProfileImportResponse(
            status="success",
            profile=profile.to_dict(),
            imported_count=count,
            message=f"成功导入 {count} 项配置到 Profile '{profile.name}'",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导入 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/profiles/compare")
async def compare_profiles(
    from_name: str = Query(..., description="源 Profile 名称"),
    to_name: str = Query(..., description="目标 Profile 名称"),
):
    """
    对比两个配置 Profile 的差异

    Args:
        from_name: 源 Profile 名称
        to_name: 目标 Profile 名称

    Returns:
        差异对比结果
    """
    try:
        service = _get_profile_service()

        # 验证两个 Profile 都存在
        from_profile = await service.get_profile(from_name)
        if not from_profile:
            raise HTTPException(status_code=404, detail=f"Profile '{from_name}' 不存在")

        to_profile = await service.get_profile(to_name)
        if not to_profile:
            raise HTTPException(status_code=404, detail=f"Profile '{to_name}' 不存在")

        # 计算差异
        diff = await service._calculate_profile_diff(from_name, to_name)

        return {
            "status": "success",
            "from_profile": from_name,
            "to_profile": to_name,
            "diff": diff.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"对比 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
