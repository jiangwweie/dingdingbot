# P1-5: ConfigParser 单元测试设计文档

> **创建时间**: 2026-04-07  
> **最后更新**: 2026-04-07 13:16
> **负责人**: qa-tester  
> **状态**: ✅ 已完成
> **并行依赖**: Backend Dev 已完成 `src/application/config/config_parser.py` 实现

---

## 测试结果

**测试通过率**: 38/38 = 100%  
**测试覆盖率**: 98%（85 行中仅 2 行日志记录未覆盖）  
**Git 提交**: `23780cd`

### 测试用例清单（共 38 个）

| 分类 | 数量 | 通过率 |
|------|------|--------|
| YAML 解析测试 | 5 | 100% |
| Decimal 精度测试 | 7 | 100% |
| 模型验证测试 | 7 | 100% |
| 序列化测试 | 5 | 100% |
| 集成测试 | 5 | 100% |
| 边界情况测试 | 9 | 100% |

---

## 测试目标

为 `ConfigParser` 类编写完整的单元测试，确保：
1. YAML 文件解析功能正确
2. Decimal 精度在序列化和反序列化过程中不丢失
3. Pydantic 模型验证正确
4. 异常处理健壮

---

## ConfigParser 接口设计（已实现）

`ConfigParser` 类已在 `src/application/config/config_parser.py` 中实现，提供以下功能：

```python
class ConfigParser:
    """YAML 配置解析器，负责 YAML 与 Python 对象之间的转换。"""
    
    def parse_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """解析 YAML 文件为字典。"""
        
    def dump_to_yaml(self, data: Dict[str, Any]) -> str:
        """将字典序列化为 YAML 字符串（保持 Decimal 精度）。"""
        
    def parse_core_config(self, data: Dict[str, Any]) -> CoreConfig:
        """将字典解析为 CoreConfig 模型。"""
        
    def parse_user_config(self, data: Dict[str, Any]) -> UserConfig:
        """将字典解析为 UserConfig 模型。"""
        
    def parse_risk_config(self, data: Dict[str, Any]) -> RiskConfig:
        """将字典解析为 RiskConfig 模型。"""
        
    def create_default_core_config(self) -> CoreConfig:
        """创建默认核心配置（fallback）。"""
        
    def create_default_user_config(self) -> UserConfig:
        """创建默认用户配置（fallback）。"""
        
    def load_core_config_from_yaml(self, config_dir: Path) -> CoreConfig:
        """从 YAML 文件加载核心配置（含 fallback）。"""
        
    def load_user_config_from_yaml(self, config_dir: Path) -> UserConfig:
        """从 YAML 文件加载用户配置（含 fallback）。"""
```

### 辅助函数

```python
# Decimal 序列化辅助函数（已全局注册到 yaml）
_decimal_representer(dumper, data) -> yaml.Node
_decimal_constructor(loader, node) -> Decimal
_convert_decimals_to_str(obj: Any) -> Any
```

---

## 测试用例清单（共 20 个）

### 1. YAML 解析测试 (5 个)

| 编号 | 测试名称 | 测试内容 | 优先级 |
|------|----------|----------|--------|
| Y1 | `test_parse_yaml_file_valid` | 有效 YAML 文件解析 | P0 |
| Y2 | `test_parse_yaml_file_not_found` | 文件不存在异常 | P0 |
| Y3 | `test_parse_yaml_file_invalid_syntax` | YAML 语法错误处理 | P1 |
| Y4 | `test_parse_yaml_file_empty` | 空 YAML 文件处理 | P2 |
| Y5 | `test_parse_yaml_file_unicode` | Unicode（中文）文件名和内容处理 | P2 |

### 2. Decimal 精度测试 (5 个) ⭐核心

| 编号 | 测试名称 | 测试内容 | 优先级 |
|------|----------|----------|--------|
| D1 | `test_decimal_representer_preserves_precision` | Decimal 表示器精度保持 (20 位+) | P0 |
| D2 | `test_decimal_constructor_restores_precision` | Decimal 构造器精度恢复 | P0 |
| D3 | `test_decimal_in_complex_config` | 复杂配置中 Decimal 精度 | P0 |
| D4 | `test_dump_to_yaml_with_decimal_zero` | 零值 Decimal 处理 | P1 |
| D5 | `test_dump_to_yaml_with_large_decimal` | 极大值 Decimal 处理 | P2 |

### 3. 模型验证测试 (5 个)

| 编号 | 测试名称 | 测试内容 | 优先级 |
|------|----------|----------|--------|
| M1 | `test_parse_core_config_valid` | 有效核心配置解析 | P0 |
| M2 | `test_parse_core_config_missing_field` | 缺少必填字段异常 | P0 |
| M3 | `test_parse_user_config_valid` | 有效用户配置解析 | P0 |
| M4 | `test_parse_risk_config_valid` | 有效风控配置解析 | P0 |
| M5 | `test_parse_risk_config_invalid_percent` | 无效百分比值验证（负数） | P1 |

### 4. 序列化测试 (3 个)

| 编号 | 测试名称 | 测试内容 | 优先级 |
|------|----------|----------|--------|
| S1 | `test_dump_to_yaml_basic` | 基本 YAML 序列化 | P0 |
| S2 | `test_dump_to_yaml_with_decimal` | Decimal 序列化 | P0 |
| S3 | `test_roundtrip_yaml_serialization` | YAML 往返序列化 (解析→序列化→解析) | P0 |

### 5. Fallback 方法测试 (2 个)

| 编号 | 测试名称 | 测试内容 | 优先级 |
|------|----------|----------|--------|
| F1 | `test_create_default_core_config` | 默认核心配置创建 | P1 |
| F2 | `test_create_default_user_config` | 默认用户配置创建 | P1 |

---

## 测试数据 Fixture

### YAML 测试文件

```yaml
# fixtures/config_valid.yaml
risk:
  max_loss_percent: 0.01
  max_leverage: 20
  max_total_exposure: 0.9
  cooldown_minutes: 300

system:
  core_symbols:
    - BTC/USDT:USDT
    - ETH/USDT:USDT
  ema_period: 60
  mtf_ema_period: 60
  mtf_mapping:
    "15m": "1h"
    "1h": "4h"
```

### Decimal 测试值

```python
DECIMAL_TEST_VALUES = [
    Decimal("0.01"),                    # 1% 风险
    Decimal("0.12345678901234567890"),  # 20 位精度
    Decimal("0"),                       # 零值
    Decimal("-0.005"),                  # 负值
    Decimal("999999.999999"),           # 极大值
]
```

---

## 覆盖率目标

| 模块 | 行覆盖率 | 分支覆盖率 |
|------|----------|------------|
| ConfigParser | >= 95% | >= 90% |

---

## 执行步骤

1. **等待 Backend Dev 实现代码** (阻塞最多 30 分钟)
2. **创建测试文件** `tests/unit/test_config_parser.py`
3. **编写 Fixture** `tests/fixtures/config_parser/`
4. **运行测试** `pytest tests/unit/test_config_parser.py -v`
5. **生成覆盖率** `pytest --cov=src/application/config --cov-report=html`
6. **修复失败的测试** (如有)
7. **提交代码**

---

## 验收标准

- [ ] 测试用例数量 >= 15 个
- [ ] 测试覆盖率 >= 95%
- [ ] 所有 P0 测试通过
- [ ] Decimal 精度验证通过
- [ ] Git 提交：`test(P1-5): ConfigParser 单元测试完成`

---

## 备注

- 如果 Backend Dev 未完成实现，先编写测试框架（使用 mock）
- Decimal 精度测试是核心，必须确保 20 位精度不丢失
- 所有测试必须独立可运行，不依赖外部服务
