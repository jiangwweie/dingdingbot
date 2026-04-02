"""
Config Snapshot Service - Business logic for configuration version control.
"""
import json
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from src.application.config_manager import UserConfig
from src.domain.models import ConfigSnapshot
from src.infrastructure.config_snapshot_repository import ConfigSnapshotRepository
from src.infrastructure.logger import mask_secret


class ConfigSnapshotError(Exception):
    """Base exception for config snapshot operations."""
    def __init__(self, message: str, error_code: str):
        self.error_code = error_code
        super().__init__(f"[{error_code}] {message}")


class SnapshotNotFoundError(ConfigSnapshotError):
    """Snapshot not found."""
    def __init__(self, snapshot_id: int):
        super().__init__(f"Snapshot {snapshot_id} not found", "CONFIG-004")


class SnapshotValidationError(ConfigSnapshotError):
    """Snapshot validation failed."""
    def __init__(self, message: str):
        super().__init__(message, "CONFIG-003")


class SnapshotProtectedError(ConfigSnapshotError):
    """Cannot delete protected snapshot."""
    def __init__(self, snapshot_id: int, protect_count: int):
        super().__init__(
            f"Cannot delete snapshot {snapshot_id}: protected (keeping last {protect_count} snapshots)",
            "CONFIG-006"
        )


class ConfigSnapshotService:
    """
    Service layer for configuration snapshot management.
    Handles business logic, validation, and auto-snapshot hooks.
    """

    # Semantic version pattern: v1.0.0, v2.3.14, etc.
    # Also supports timestamp-based versions: v20260402.153045 (vYYYYMMDD.HHMMSS)
    # Date part: exactly 8 digits (YYYYMMDD), Time part: 2-6 digits (H to HHMMSS)
    VERSION_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$|^v\d{8}\.\d{2,6}$")

    def __init__(
        self,
        repository: ConfigSnapshotRepository,
        protect_recent_count: int = 5
    ):
        """
        Initialize ConfigSnapshotService.

        Args:
            repository: ConfigSnapshotRepository instance
            protect_recent_count: Number of recent snapshots to protect from deletion
        """
        self.repo = repository
        self.protect_recent_count = protect_recent_count

    async def create_manual_snapshot(
        self,
        version: str,
        config: UserConfig,
        description: str = "",
        created_by: str = "user"
    ) -> int:
        """
        Create a manual configuration snapshot.

        Args:
            version: Semantic version string (e.g., 'v1.0.0')
            config: UserConfig model to snapshot
            description: Optional description
            created_by: Creator identifier

        Returns:
            Created snapshot ID

        Raises:
            SnapshotValidationError: If version format is invalid
        """
        # Validate version format
        if not self.VERSION_PATTERN.match(version):
            raise SnapshotValidationError(
                f"Invalid version format '{version}': must match pattern 'vX.Y' where X is date (YYYYMMDD) and Y is time (HHMMSS or HH), e.g., 'v1.0.0' or 'v20260402.153045'"
            )

        # Serialize config to JSON (with masking for sensitive fields)
        config_dict = config.model_dump(mode='json')
        masked_config = self._mask_config(config_dict)
        config_json = json.dumps(masked_config, indent=2)

        snapshot_data = {
            "version": version,
            "config_json": config_json,
            "description": description,
            "created_by": created_by,
        }

        return await self.repo.create(snapshot_data)

    async def create_auto_snapshot(
        self,
        config: UserConfig,
        description: str = "配置变更自动快照"
    ) -> Optional[int]:
        """
        Create an automatic configuration snapshot (before config change).

        Auto-generates version based on timestamp.
        Version format: vYYYYMMDD.HHMMSS (e.g., v20260402.153045)

        Args:
            config: UserConfig model to snapshot
            description: Auto-generated description

        Returns:
            Created snapshot ID, or None if snapshot creation failed
        """
        try:
            # Generate version from timestamp: vYYYYMMDD.HHMMSS (semantic version compatible)
            now = datetime.now(timezone.utc)
            version = now.strftime("v%Y%m%d.%H%M%S")

            # Append description with timestamp
            full_description = f"{description} - {now.isoformat()}"

            return await self.create_manual_snapshot(
                version=version,
                config=config,
                description=full_description,
                created_by="system"
            )
        except Exception as e:
            # Log error but don't block config update
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Auto-snapshot creation failed: {e}")
            return None

    async def get_snapshot_list(
        self,
        limit: int = 20,
        offset: int = 0,
        created_by: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get snapshot list with pagination.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            created_by: Filter by creator
            is_active: Filter by active status

        Returns:
            Tuple of (list of snapshot dicts, total count)
        """
        return await self.repo.get_list(
            limit=limit,
            offset=offset,
            created_by=created_by,
            is_active=is_active
        )

    async def get_snapshot_detail(self, snapshot_id: int) -> Dict[str, Any]:
        """
        Get detailed snapshot information.

        Args:
            snapshot_id: Snapshot record ID

        Returns:
            Snapshot detail dict with parsed config

        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist
        """
        snapshot = await self.repo.get_by_id(snapshot_id)

        if not snapshot:
            raise SnapshotNotFoundError(snapshot_id)

        # Parse config JSON for display
        try:
            config = json.loads(snapshot["config_json"])
        except (json.JSONDecodeError, KeyError):
            config = {}

        return {
            "id": snapshot["id"],
            "version": snapshot["version"],
            "config": config,  # Parsed config (already masked)
            "config_json": snapshot["config_json"],  # Raw JSON string
            "description": snapshot["description"],
            "created_at": snapshot["created_at"],
            "created_by": snapshot["created_by"],
            "is_active": bool(snapshot["is_active"]),
        }

    async def rollback_to_snapshot(self, snapshot_id: int) -> Dict[str, Any]:
        """
        Rollback to a snapshot (activate it).

        Args:
            snapshot_id: Snapshot record ID

        Returns:
            Activated snapshot detail

        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist
            SnapshotValidationError: If snapshot config is invalid
        """
        # Get snapshot first to validate
        snapshot = await self.repo.get_by_id(snapshot_id)
        if not snapshot:
            raise SnapshotNotFoundError(snapshot_id)

        # Validate config JSON
        try:
            config_data = json.loads(snapshot["config_json"])
            # Validate against UserConfig schema
            UserConfig(**config_data)
        except json.JSONDecodeError as e:
            raise SnapshotValidationError(f"Snapshot config JSON is invalid: {e}")
        except Exception as e:
            raise SnapshotValidationError(f"Snapshot config validation failed: {e}")

        # Activate the snapshot
        success = await self.repo.set_active(snapshot_id)
        if not success:
            raise SnapshotNotFoundError(snapshot_id)

        # Return detail
        return await self.get_snapshot_detail(snapshot_id)

    async def delete_snapshot(self, snapshot_id: int) -> bool:
        """
        Delete a snapshot (with protection for recent snapshots).

        Args:
            snapshot_id: Snapshot record ID

        Returns:
            True if deleted successfully

        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist
            SnapshotProtectedError: If snapshot is protected
        """
        # Check if snapshot exists
        snapshot = await self.repo.get_by_id(snapshot_id)
        if not snapshot:
            raise SnapshotNotFoundError(snapshot_id)

        # Get recent snapshot IDs (protected)
        recent_ids = await self.repo.get_recent_snapshots(self.protect_recent_count)

        if snapshot_id in recent_ids:
            raise SnapshotProtectedError(snapshot_id, self.protect_recent_count)

        # Delete
        return await self.repo.delete(snapshot_id)

    async def get_active_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Get the currently active snapshot.

        Returns:
            Active snapshot detail or None
        """
        snapshot = await self.repo.get_active()
        if not snapshot:
            return None

        try:
            config = json.loads(snapshot["config_json"])
        except (json.JSONDecodeError, KeyError):
            config = {}

        return {
            "id": snapshot["id"],
            "version": snapshot["version"],
            "config": config,
            "description": snapshot["description"],
            "created_at": snapshot["created_at"],
            "created_by": snapshot["created_by"],
            "is_active": True,
        }

    def _mask_config(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mask sensitive fields in config dict.

        Args:
            config_dict: Raw config dictionary

        Returns:
            Config with sensitive fields masked
        """
        masked = config_dict.copy()

        # Mask exchange credentials
        if "exchange" in masked:
            exchange = masked["exchange"]
            if isinstance(exchange, dict):
                if "api_key" in exchange:
                    exchange["api_key"] = mask_secret(exchange["api_key"])
                if "api_secret" in exchange:
                    exchange["api_secret"] = mask_secret(exchange["api_secret"])

        # Mask notification webhook URLs
        if "notification" in masked:
            notification = masked["notification"]
            if isinstance(notification, dict) and "channels" in notification:
                for channel in notification.get("channels", []):
                    if isinstance(channel, dict) and "webhook_url" in channel:
                        channel["webhook_url"] = mask_secret(channel["webhook_url"])

        return masked

    def generate_next_version(self) -> str:
        """
        Generate next semantic version based on current snapshots.

        Returns:
            Next version string (e.g., 'v1.0.1')
        """
        # This would need async access to repo, so we use timestamp-based instead
        now = datetime.now(timezone.utc)
        return now.strftime("v%Y%m%d.%H%M%S")
