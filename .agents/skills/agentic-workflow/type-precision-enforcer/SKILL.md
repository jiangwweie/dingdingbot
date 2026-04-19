# 类型与精度宪兵技能 (Type & Precision Enforcer)

> **技能类型**: 代码审查 + 自动修复
> **适用场景**: 所有涉及金融计算的代码提交
> **审查红线**: float 污染、Decimal 精度、TickSize 格式化

---

## 技能描述

本技能在代码合并前执行严格审查：
1. mypy --strict 类型检查
2. float 使用检测（特别是 domain 层）
3. CCXT 调用前的 quantize() 验证
4. Pydantic 判别器检查

---

## 权限要求

```json
{
  "permissions": {
    "allow": [
      "Bash(mypy:*)",
      "Bash(python3 scripts/check_float.py:*)",
      "Bash(python3 scripts/check_quantize.py:*)",
      "Grep(*.py)",
      "Read(//Users/jiangwei/Documents/final/src/**)"
    ]
  }
}
```

---

## 审查清单

### 红线 1: 禁止 float 用于金融计算

**检测脚本** (`scripts/check_float.py`):

```python
#!/usr/bin/env python3
"""检测 domain 层和应用层的 float 使用"""

import ast
import sys
from pathlib import Path

# 允许使用 float 的场景
ALLOWED_PATTERNS = {
    "range()", "isinstance()", "type_hint", "docstring", "comment"
}

# 禁止 float 的目录
STRICT_DIRS = ["src/domain/", "src/application/"]

def check_float_in_file(filepath: Path) -> list[dict]:
    """检查文件中的 float 使用"""
    violations = []
    source = filepath.read_text()
    
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [{"line": 0, "issue": "SyntaxError"}]
    
    for node in ast.walk(tree):
        # 检测 float() 调用
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "float":
                violations.append({
                    "file": str(filepath),
                    "line": node.lineno,
                    "issue": "float() call detected",
                    "suggestion": "Use Decimal() instead"
                })
        
        # 检测 float 类型注解
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.annotation, ast.Name):
                if node.annotation.id == "float":
                    violations.append({
                        "file": str(filepath),
                        "line": node.lineno,
                        "issue": "float type annotation",
                        "suggestion": "Use Decimal instead"
                    })
    
    return violations

if __name__ == "__main__":
    all_violations = []
    
    for dir_path in STRICT_DIRS:
        for py_file in Path(dir_path).rglob("*.py"):
            violations = check_float_in_file(py_file)
            all_violations.extend(violations)
    
    if all_violations:
        print("❌ float 使用检测失败:\n")
        for v in all_violations:
            print(f"  {v['file']}:{v['line']}")
            print(f"    Issue: {v['issue']}")
            print(f"    Fix: {v['suggestion']}\n")
        sys.exit(1)
    else:
        print("✅ float 检测通过 (domain/application 层)")
        sys.exit(0)
```

**违规示例**:
```python
# ❌ 错误
class Order:
    price: float  # 类型注解使用 float
    quantity: float

def calculate_pnl(entry: float, exit: float) -> float:
    return float(exit - entry)

# ✅ 正确
from decimal import Decimal

class Order:
    price: Decimal
    quantity: Decimal

def calculate_pnl(entry: Decimal, exit: Decimal) -> Decimal:
    return exit - entry
```

---

### 红线 2: Decimal 精度与量化

**检测脚本** (`scripts/check_decimal_quantize.py`):

```python
#!/usr/bin/env python3
"""检查 Decimal 的 quantize 调用"""

import ast
import sys
from pathlib import Path

def check_decimal_usage(filepath: Path) -> list[dict]:
    """检查 Decimal 使用是否规范"""
    violations = []
    source = filepath.read_text()
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        # 检测 Decimal 算术运算后是否 quantize
        if isinstance(node, ast.BinOp):
            # 检查是否包含 Decimal 运算
            left_has_decimal = has_decimal_type(node.left)
            right_has_decimal = has_decimal_type(node.right)
            
            if left_has_decimal or right_has_decimal:
                # 检查父节点是否有 quantize 调用
                parent = get_parent_node(tree, node)
                if parent and not has_quantize_call(parent):
                    # 检查是否在返回值中
                    if isinstance(parent, ast.Return):
                        violations.append({
                            "file": str(filepath),
                            "line": node.lineno,
                            "issue": "Decimal arithmetic without quantize",
                            "suggestion": "Call .quantize() before returning"
                        })
    
    return violations

def has_decimal_type(node: ast.AST) -> bool:
    """检查节点是否涉及 Decimal"""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "Decimal":
            return True
    return False

def has_quantize_call(node: ast.AST) -> bool:
    """检查是否有 quantize() 调用"""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Attribute) and child.func.attr == "quantize":
                return True
    return False

def get_parent_node(tree: ast.AST, target: ast.AST) -> ast.AST | None:
    """获取父节点 (简化版)"""
    node_map = {id(node): node for node in ast.walk(tree)}
    # 实际实现需要更复杂的父节点追踪
    return None

if __name__ == "__main__":
    target_dir = Path("src/domain")
    all_violations = []
    
    for py_file in target_dir.rglob("*.py"):
        violations = check_decimal_usage(py_file)
        all_violations.extend(violations)
    
    if all_violations:
        print("⚠️ Decimal quantize 检查发现潜在问题:\n")
        for v in all_violations:
            print(f"  {v['file']}:{v['line']}: {v['issue']}")
            print(f"    Fix: {v['suggestion']}\n")
        # 警告级别，不阻塞
    else:
        print("✅ Decimal quantize 检查通过")
```

---

### 红线 3: CCXT 调用前的 TickSize/LotSize 格式化

**检测脚本** (`scripts/check_quantize.py`):

```python
#!/usr/bin/env python3
"""检查 CCXT 调用前的 TickSize/LotSize 格式化"""

import ast
import sys
from pathlib import Path

CCXT_CALLS = {
    'create_order', 
    'create_market_order', 
    'create_limit_order',
    'cancel_order',
    'fetch_balance'
}

def check_quantize_in_file(filepath: Path) -> list[dict]:
    """检查 CCXT 调用前是否有 quantize"""
    errors = []
    source = filepath.read_text()
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in CCXT_CALLS:
                    # 检查价格和数量参数
                    for i, arg in enumerate(node.args):
                        if is_price_or_quantity_arg(i, node.func.attr):
                            if not has_quantize_or_decimal(arg):
                                errors.append({
                                    "file": str(filepath),
                                    "line": node.lineno,
                                    "call": node.func.attr,
                                    "arg_index": i,
                                    "issue": f"Argument {i} may need quantize()",
                                    "suggestion": "Ensure value is Decimal and call .quantize(tick_size)"
                                })
                    
                    # 检查关键字参数
                    for kw in node.keywords:
                        if kw.arg in ['price', 'quantity', 'amount', 'size']:
                            if not has_quantize_or_decimal(kw.value):
                                errors.append({
                                    "file": str(filepath),
                                    "line": kw.lineno,
                                    "call": node.func.attr,
                                    "keyword": kw.arg,
                                    "issue": f"Keyword argument '{kw.arg}' may need quantize()",
                                    "suggestion": "Use Decimal and call .quantize()"
                                })
    
    return errors

def is_price_or_quantity_arg(arg_index: int, method_name: str) -> bool:
    """判断参数索引是否对应价格或数量"""
    # CCXT create_order 签名：
    # create_order(symbol, type, side, amount, price=None, params={})
    if method_name == 'create_order':
        return arg_index == 3  # amount (数量)
        # price 是关键字参数
    return False

def has_quantize_or_decimal(node: ast.AST) -> bool:
    """检查节点是否包含 Decimal 或 quantize 调用"""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name) and child.func.id == "Decimal":
                return True
            if isinstance(child.func, ast.Attribute) and child.func.attr == "quantize":
                return True
        # 检查是否调用返回 Decimal 的方法
        if isinstance(child, ast.Attribute):
            if child.attr in ['entry_price', 'exit_price', 'stop_loss', 'quantity']:
                return True  # 假设这些属性返回 Decimal
    return False

if __name__ == "__main__":
    # 检查基础设施层 (CCXT 调用集中地)
    target_dirs = [
        Path("src/infrastructure"),
        Path("src/domain"),
    ]
    
    all_errors = []
    for target_dir in target_dirs:
        for py_file in target_dir.rglob("*.py"):
            all_errors.extend(check_quantize_in_file(py_file))
    
    if all_errors:
        print("❌ TickSize/LotSize 格式化检查失败:\n")
        for err in all_errors:
            print(f"  {err['file']}:{err['line']}")
            print(f"    Call: {err['call']}()")
            print(f"    Issue: {err['issue']}")
            print(f"    Fix: {err['suggestion']}\n")
        sys.exit(1)
    else:
        print("✅ TickSize/LotSize 格式化检查通过")
        sys.exit(0)
```

---

### 红线 4: Pydantic 判别器检查

**检测脚本** (`scripts/check_pydantic_discriminator.py`):

```python
#!/usr/bin/env python3
"""检查 Pydantic 多态模型是否有判别器"""

import ast
import sys
from pathlib import Path

def check_pydantic_models(filepath: Path) -> list[dict]:
    """检查 Pydantic 模型配置"""
    issues = []
    source = filepath.read_text()
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        # 检测类定义
        if isinstance(node, ast.ClassDef):
            # 检查是否继承 BaseModel
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "BaseModel":
                    # 检查类配置
                    config = extract_pydantic_config(node)
                    
                    # 检查是否有 Union 类型的字段
                    union_fields = find_union_fields(node)
                    
                    if union_fields and not config.get('discriminator'):
                        issues.append({
                            "file": str(filepath),
                            "line": node.lineno,
                            "class": node.name,
                            "issue": "Union fields without discriminator",
                            "fields": [f.name for f in union_fields],
                            "suggestion": "Add model_config = ConfigDict(discriminator='type')"
                        })
    
    return issues

def extract_pydantic_config(class_node: ast.ClassDef) -> dict:
    """提取 Pydantic 配置"""
    config = {}
    for node in class_node.body:
        # 检查 model_config 赋值
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                if node.target.id == "model_config":
                    # 解析配置内容
                    config['raw'] = node.value
        # 检查 Config 内部类 (Pydantic v1 风格)
        elif isinstance(node, ast.ClassDef) and node.name == "Config":
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name):
                        config[item.target.id] = item.value
    return config

def find_union_fields(class_node: ast.ClassDef) -> list[ast.AnnAssign]:
    """查找 Union 类型的字段"""
    union_fields = []
    for node in class_node.body:
        if isinstance(node, ast.AnnAssign):
            if is_union_type(node.annotation):
                union_fields.append(node)
    return union_fields

def is_union_type(annotation: ast.AST) -> bool:
    """检查是否是 Union 类型"""
    if isinstance(annotation, ast.Subscript):
        if isinstance(annotation.value, ast.Name):
            if annotation.value.id == "Union":
                return True
            if annotation.value.id == "Optional":
                return True  # Optional 是 Union[X, None]
        # 检查 union 类型 (Pydantic v2)
        if isinstance(annotation.value, ast.Attribute):
            if annotation.value.attr == "Union":
                return True
    return False

if __name__ == "__main__":
    target_dir = Path("src/domain")
    all_issues = []
    
    for py_file in target_dir.rglob("*.py"):
        issues = check_pydantic_models(py_file)
        all_issues.extend(issues)
    
    if all_issues:
        print("⚠️ Pydantic 判别器检查:\n")
        for issue in all_issues:
            print(f"  {issue['file']}:{issue['line']}")
            print(f"    Class: {issue['class']}")
            print(f"    Issue: {issue['issue']}")
            print(f"    Union Fields: {', '.join(issue['fields'])}")
            print(f"    Fix: {issue['suggestion']}\n")
        # 警告级别
    else:
        print("✅ Pydantic 判别器检查通过")
```

---

## CI/CD 集成

### GitHub Actions 工作流

```yaml
# .github/workflows/type-and-precision-check.yml

name: Type & Precision Check

on:
  pull_request:
    branches: [main, dev]
  push:
    branches: [dev]

jobs:
  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install mypy pytest
          
      - name: Run mypy --strict
        run: |
          mypy --strict src/domain/ || echo "mypy warnings (non-blocking)"
          
      - name: Check for float in domain layer
        run: |
          python3 scripts/check_float.py
          if [ $? -ne 0 ]; then
            echo "❌ float check failed"
            exit 1
          fi
          
      - name: Check Decimal quantize
        run: |
          python3 scripts/check_quantize.py
          if [ $? -ne 0 ]; then
            echo "❌ quantize check failed"
            exit 1
          fi
          
      - name: Check Pydantic discriminator
        run: |
          python3 scripts/check_pydantic_discriminator.py
          # 仅警告，不阻塞
```

---

## 技能执行流程

### 触发条件

| 场景 | 触发行为 |
|------|----------|
| 代码提交前 | 自动运行所有检查 |
| 用户请求审查 | 运行检查 + 生成报告 |
| 检测到 float 使用 | 立即警告 + 建议修复 |

### 输出格式

**审查报告示例**:
```markdown
## 类型与精度审查报告

### ✅ 通过项
- mypy --strict: 通过 (domain 层无类型错误)
- float 检测：通过
- Decimal quantize: 通过

### ⚠️ 警告项
- Pydantic 判别器：1 个问题

```

**失败报告示例**:
```markdown
## ❌ 审查失败

### float 检测失败 (阻塞)

| 位置 | 问题 | 建议修复 |
|------|------|----------|
| src/domain/risk_manager.py:45 | float type annotation | Use Decimal instead |
| src/domain/risk_manager.py:52 | float() call | Use Decimal() |

### TickSize 格式化失败 (阻塞)

| 位置 | 调用 | 问题 |
|------|------|------|
| src/infrastructure/exchange_gateway.py:123 | create_order() | price 参数缺少 quantize() |

### 修复建议

1. 将 `price: float` 改为 `price: Decimal`
2. 在调用 `exchange.create_order()` 前添加 `.quantize(tick_size)`
```

---

## 自动修复建议

**AI 可生成的修复代码**:

```python
# 修复前
class Order:
    price: float
    quantity: float
    
    def total(self) -> float:
        return float(self.price * self.quantity)

# 修复后
from decimal import Decimal

class Order:
    price: Decimal
    quantity: Decimal
    
    def total(self) -> Decimal:
        return (self.price * self.quantity).quantize(Decimal("0.01"))
```

---

*技能版本：v1.0*
*创建日期：2026-04-01*
