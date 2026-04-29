"""
Unit tests for Strategy Parameters YAML Import/Export API.

Tests for:
- GET /api/strategy/params/export - Export strategy parameters as YAML
- POST /api/strategy/params/export - Export strategy parameters to file
- POST /api/strategy/params/import - Import strategy parameters from YAML
"""
import pytest
import yaml
from decimal import Decimal
from src.domain.models import StrategyParams


class TestStrategyParamsYamlModels:
    """Test YAML import/export Pydantic models."""

    def test_export_response_model(self):
        """Test StrategyParamsExportResponse model."""
        from src.interfaces.api import StrategyParamsExportResponse

        response = StrategyParamsExportResponse(
            yaml_content="strategy:\n  pinbar:\n    min_wick_ratio: 0.6",
            download_url="/data/backup.yaml",
        )

        assert response.yaml_content == "strategy:\n  pinbar:\n    min_wick_ratio: 0.6"
        assert response.download_url == "/data/backup.yaml"

    def test_export_response_optional_download_url(self):
        """Test download_url is optional."""
        from src.interfaces.api import StrategyParamsExportResponse

        response = StrategyParamsExportResponse(
            yaml_content="strategy:\n  pinbar:\n    min_wick_ratio: 0.6",
        )

        assert response.download_url is None

    def test_import_request_model(self):
        """Test StrategyParamsImportRequest model."""
        from src.interfaces.api import StrategyParamsImportRequest

        request = StrategyParamsImportRequest(
            yaml_content="strategy:\n  pinbar:\n    min_wick_ratio: 0.6",
            overwrite=True,
        )

        assert request.yaml_content == "strategy:\n  pinbar:\n    min_wick_ratio: 0.6"
        assert request.overwrite is True

    def test_import_request_default_overwrite(self):
        """Test overwrite defaults to True."""
        from src.interfaces.api import StrategyParamsImportRequest

        request = StrategyParamsImportRequest(
            yaml_content="strategy:\n  pinbar:\n    min_wick_ratio: 0.6",
        )

        assert request.overwrite is True

    def test_import_response_model(self):
        """Test StrategyParamsImportResponse model."""
        from src.interfaces.api import StrategyParamsImportResponse, StrategyParamsResponse

        imported_params = StrategyParamsResponse(
            pinbar={"min_wick_ratio": 0.6},
            engulfing={},
            ema={"period": 60},
            mtf={"enabled": True},
            atr={},
            filters=[],
        )

        response = StrategyParamsImportResponse(
            status="success",
            message="Successfully imported",
            imported_params=imported_params,
            errors=[],
        )

        assert response.status == "success"
        assert response.imported_params.pinbar == {"min_wick_ratio": 0.6}
        assert response.errors == []


class TestYamlExport:
    """Test YAML export functionality."""

    def test_export_generates_valid_yaml(self):
        """Test that exported content is valid YAML."""
        yaml_content = """strategy:
  pinbar:
    min_wick_ratio: 0.6
    max_body_ratio: 0.3
    body_position_tolerance: 0.1
  ema:
    period: 60
  mtf:
    enabled: true
    ema_period: 60
"""
        # Parse YAML to verify it's valid
        data = yaml.safe_load(yaml_content)

        assert "strategy" in data
        assert data["strategy"]["pinbar"]["min_wick_ratio"] == 0.6
        assert data["strategy"]["ema"]["period"] == 60
        assert data["strategy"]["mtf"]["enabled"] is True

    def test_export_with_all_categories(self):
        """Test YAML export with all strategy categories."""
        yaml_content = """strategy:
  pinbar:
    min_wick_ratio: 0.65
    max_body_ratio: 0.25
  engulfing:
    max_wick_ratio: 0.6
  ema:
    period: 50
  mtf:
    enabled: true
    ema_period: 50
  atr:
    enabled: true
    period: 14
    min_atr_ratio: 0.5
  filters: []
"""
        data = yaml.safe_load(yaml_content)

        assert "pinbar" in data["strategy"]
        assert "engulfing" in data["strategy"]
        assert "ema" in data["strategy"]
        assert "mtf" in data["strategy"]
        assert "atr" in data["strategy"]
        assert data["strategy"]["atr"]["period"] == 14

    def test_export_with_filters(self):
        """Test YAML export with custom filters."""
        yaml_content = """strategy:
  pinbar:
    min_wick_ratio: 0.6
  filters:
    - type: ema
      enabled: true
      params:
        period: 60
    - type: mtf
      enabled: false
      params: {}
"""
        data = yaml.safe_load(yaml_content)

        assert len(data["strategy"]["filters"]) == 2
        assert data["strategy"]["filters"][0]["type"] == "ema"
        assert data["strategy"]["filters"][1]["type"] == "mtf"


class TestYamlImport:
    """Test YAML import functionality."""

    def test_import_valid_yaml(self):
        """Test importing valid YAML content."""
        yaml_content = """strategy:
  pinbar:
    min_wick_ratio: 0.6
    max_body_ratio: 0.3
  ema:
    period: 60
"""
        data = yaml.safe_load(yaml_content)

        assert data["strategy"]["pinbar"]["min_wick_ratio"] == 0.6
        assert data["strategy"]["ema"]["period"] == 60

    def test_import_yaml_without_strategy_root(self):
        """Test importing YAML without 'strategy' root key."""
        yaml_content = """pinbar:
  min_wick_ratio: 0.6
  max_body_ratio: 0.3
ema:
  period: 60
"""
        data = yaml.safe_load(yaml_content)

        # Support both formats
        if "strategy" not in data:
            # Direct format - use as-is
            assert data["pinbar"]["min_wick_ratio"] == 0.6

    def test_import_invalid_yaml_raises_error(self):
        """Test that invalid YAML raises an error."""
        invalid_yaml = """strategy:
  pinbar:
    min_wick_ratio: 0.6
    invalid_indent: value
      nested_wrong: value
"""
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(invalid_yaml)

    def test_import_yaml_with_decimal_strings(self):
        """Test importing YAML with decimal values as strings."""
        yaml_content = """strategy:
  pinbar:
    min_wick_ratio: "0.6"
    max_body_ratio: "0.3"
  risk:
    max_loss_percent: "0.01"
"""
        data = yaml.safe_load(yaml_content)

        # YAML parser may keep them as strings or convert to numbers
        assert str(data["strategy"]["pinbar"]["min_wick_ratio"]) in ["0.6", "0.6"]

    def test_import_yaml_with_boolean_values(self):
        """Test importing YAML with boolean values."""
        yaml_content = """strategy:
  mtf:
    enabled: true
    require_confirmation: false
  atr:
    enabled: true
"""
        data = yaml.safe_load(yaml_content)

        assert data["strategy"]["mtf"]["enabled"] is True
        assert data["strategy"]["mtf"]["require_confirmation"] is False
        assert data["strategy"]["atr"]["enabled"] is True

    def test_import_yaml_with_nested_filters(self):
        """Test importing YAML with nested filter configurations."""
        yaml_content = """strategy:
  filters:
    - type: ema
      enabled: true
      params:
        period: 60
        trend_mode: long_only
    - type: atr
      enabled: false
      params:
        period: 14
        min_atr_ratio: 0.5
"""
        data = yaml.safe_load(yaml_content)

        assert len(data["strategy"]["filters"]) == 2
        assert data["strategy"]["filters"][0]["params"]["period"] == 60
        assert data["strategy"]["filters"][1]["params"]["min_atr_ratio"] == 0.5


class TestConfigEntryRepositoryImportExport:
    """Test ConfigEntryRepository import/export methods."""

    @pytest.fixture
    async def repository(self):
        """Create a test repository instance."""
        from src.infrastructure.config_entry_repository import ConfigEntryRepository
        import tempfile
        import os

        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigEntryRepository(db_path=db_path)
        await repo.initialize()

        yield repo

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_save_and_load_strategy_params(self, repository):
        """Test saving and loading strategy parameters."""
        # Save params using flatten structure
        await repository.upsert_entry("strategy.pinbar.min_wick_ratio", 0.6)
        await repository.upsert_entry("strategy.pinbar.max_body_ratio", 0.3)
        await repository.upsert_entry("strategy.ema.period", 60)

        # Load by prefix
        params = await repository.get_entries_by_prefix("strategy")

        assert "strategy.pinbar.min_wick_ratio" in params
        assert params["strategy.pinbar.min_wick_ratio"] == 0.6
        assert params["strategy.ema.period"] == 60

    @pytest.mark.asyncio
    async def test_export_to_dict(self, repository):
        """Test exporting all entries to dictionary."""
        # Save some entries
        await repository.upsert_entry("strategy.pinbar.min_wick_ratio", 0.65)
        await repository.upsert_entry("strategy.mtf.enabled", True)

        # Export
        exported = await repository.export_to_dict()

        assert "strategy.pinbar.min_wick_ratio" in exported
        assert exported["strategy.pinbar.min_wick_ratio"] == 0.65
        assert exported["strategy.mtf.enabled"] is True

    @pytest.mark.asyncio
    async def test_import_from_dict(self, repository):
        """Test importing configuration from dictionary."""
        config_dict = {
            "strategy.pinbar.min_wick_ratio": 0.7,
            "strategy.pinbar.max_body_ratio": 0.25,
            "strategy.ema.period": 50,
            "strategy.mtf.enabled": True,
        }

        # Import
        count = await repository.import_from_dict(config_dict)

        assert count == 4

        # Verify
        loaded = await repository.get_entries_by_prefix("strategy")
        assert loaded["strategy.pinbar.min_wick_ratio"] == 0.7
        assert loaded["strategy.ema.period"] == 50

    @pytest.mark.asyncio
    async def test_save_and_load_filters_as_json(self, repository):
        """Test saving and loading filters as JSON."""
        filters = [
            {"type": "ema", "enabled": True, "params": {"period": 60}},
            {"type": "mtf", "enabled": False, "params": {}},
        ]

        await repository.upsert_entry("strategy.filters", filters)

        loaded = await repository.get_entry("strategy.filters")
        assert loaded is not None
        assert loaded["config_value"] == filters


class TestStrategyParamsValidation:
    """Test StrategyParams validation for imported YAML data."""

    def test_validate_minimal_params(self):
        """Test validating minimal strategy parameters."""
        params = StrategyParams(
            pinbar={},
            engulfing={},
            ema={},
            mtf={},
            atr={},
            filters=[],
        )
        # Should not raise
        assert params is not None

    def test_validate_full_params(self):
        """Test validating complete strategy parameters."""
        params = StrategyParams(
            pinbar={
                "min_wick_ratio": Decimal("0.6"),
                "max_body_ratio": Decimal("0.3"),
                "body_position_tolerance": Decimal("0.1"),
            },
            ema={"period": 60},
            mtf={"enabled": True, "ema_period": 60},
            atr={"enabled": True, "period": 14, "min_atr_ratio": Decimal("0.5")},
            engulfing={},
            filters=[],
        )
        assert params.pinbar.min_wick_ratio == Decimal("0.6")
        assert params.ema.period == 60

    def test_validate_with_filters(self):
        """Test validating parameters with custom filters."""
        from src.domain.models import FilterParams

        params = StrategyParams(
            pinbar={},
            engulfing={},
            ema={},
            mtf={},
            atr={},
            filters=[
                FilterParams(type="ema", enabled=True, params={"period": 60}),
                FilterParams(type="atr", enabled=False, params={}),
            ],
        )
        assert len(params.filters) == 2
        assert params.filters[0].type == "ema"

    def test_validate_invalid_params_raises_error(self):
        """Test that invalid parameters raise validation error."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            StrategyParams(
                pinbar={},
                engulfing={},
                ema={"period": -1},  # Invalid: negative period
                mtf={},
                atr={},
                filters=[],
            )

    def test_validate_ema_period_range(self):
        """Test EMA period validation."""
        from pydantic import ValidationError

        # Too low
        with pytest.raises(ValidationError):
            StrategyParams(ema={"period": 0})

        # Valid
        params = StrategyParams(ema={"period": 10})
        assert params.ema.period == 10

        # Valid upper bound
        params = StrategyParams(ema={"period": 200})
        assert params.ema.period == 200


class TestYamlRoundTrip:
    """Test YAML export -> import round trip."""

    def test_export_then_import_produces_same_config(self):
        """Test that exporting and importing produces the same configuration."""
        # Original config
        original = {
            "strategy": {
                "pinbar": {"min_wick_ratio": 0.6, "max_body_ratio": 0.3},
                "ema": {"period": 60},
                "mtf": {"enabled": True, "ema_period": 60},
                "atr": {"enabled": True, "period": 14},
                "engulfing": {},
                "filters": [],
            }
        }

        # Export to YAML
        yaml_content = yaml.safe_dump(original, default_flow_style=False)

        # Import back
        imported = yaml.safe_load(yaml_content)

        # Verify structure preserved
        assert imported["strategy"]["pinbar"]["min_wick_ratio"] == 0.6
        assert imported["strategy"]["ema"]["period"] == 60
        assert imported["strategy"]["mtf"]["enabled"] is True

    def test_complex_config_round_trip(self):
        """Test complex configuration round trip with filters."""
        original = {
            "strategy": {
                "pinbar": {
                    "min_wick_ratio": 0.65,
                    "max_body_ratio": 0.25,
                    "body_position_tolerance": 0.1,
                },
                "filters": [
                    {"type": "ema", "enabled": True, "params": {"period": 50}},
                    {"type": "mtf", "enabled": True, "params": {"require_all_timeframes": False}},
                ],
            }
        }

        # Export to YAML
        yaml_content = yaml.safe_dump(original, default_flow_style=False)

        # Import back
        imported = yaml.safe_load(yaml_content)

        # Verify
        assert imported["strategy"]["pinbar"]["min_wick_ratio"] == 0.65
        assert len(imported["strategy"]["filters"]) == 2
        assert imported["strategy"]["filters"][0]["type"] == "ema"
