# MD 文档读取问题解决方案

## 问题根源

项目中的 MD 文档读取失败是由以下两个原因导致：

### 1. 文件名空格问题
- **实际文件名**: `叮盘狗 - 系统演进全景路线图.md`（无空格）
- **用户输入**: `叮盘狗 - 系统演进全景路线图.md`（有空格）
- **Shell 行为**: 空格会被 shell 拆分导致文件路径解析错误

### 2. Unicode 规范化问题 (NFD vs NFC)
- **macOS 文件系统**: 使用 NFD (Normalized Form Decomposed) 存储 Unicode 文件名
- **大多数工具**: 期望 NFC (Normalized Form Composed) 格式
- **表现**: 看起来相同的文件名，实际编码不同导致匹配失败

## 解决方案

### 方案 1: 批量重命名文件（推荐 - 一劳永逸）

执行脚本自动修复所有文件名：

```bash
# 在项目根目录执行
python3 scripts/fix_filenames.py
```

此脚本会：
1. 将 NFD 文件名转换为 NFC 格式
2. 移除文件名中的所有空格
3. 保持文件内容不变

### 方案 2: 读取时使用包装脚本

如果暂时不能修改文件名，使用包装脚本读取：

```bash
# 使用 read_markdown.py 脚本
python3 scripts/read_markdown.py "docs/tasks/文件名.md"
```

此脚本提供：
- Unicode 规范化 (NFC/NFD) 自动转换
- 文件名模糊匹配（忽略多余空格）

### 方案 3: 在代码中正确处理路径

Python 代码中读取文件的正确方式：

```python
from pathlib import Path
import unicodedata

# 方法 1: 使用 pathlib（推荐）
path = Path("docs/tasks/文件名.md")
content = path.read_text(encoding='utf-8')

# 方法 2: Unicode 规范化后读取
filepath = unicodedata.normalize('NFC', "docs/tasks/文件名.md")
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
```

### 方案 4: Shell 命令中使用引号

在终端中使用文件时，始终用引号包裹路径：

```bash
# ✅ 正确
cat "docs/tasks/叮盘狗 - 系统演进全景路线图.md"
vim "docs/tasks/2026-03-25-子任务 F-强类型递归引擎与 Schema 自动化开发.md"

# ❌ 错误（会被空格拆分）
cat docs/tasks/叮盘狗 - 系统演进全景路线图.md
```

## 预防措施

### 更新 CLAUDE.md

已在 `CLAUDE.md` 中添加文件命名规范章节，要求：
- 禁止在文件名中使用空格
- 使用 UTF-8 无 BOM 编码
- 中文文件名使用 NFC 格式

### Git 钩子（可选）

创建 `.git/hooks/pre-commit` 钩子检查文件名：

```bash
#!/bin/bash
# .git/hooks/pre-commit

# 检查文件名是否包含空格
if git diff --cached --name-only | grep ' '; then
    echo "错误：文件名不能包含空格"
    echo "请使用连字符替代空格：'file name.md' → 'file-name.md'"
    exit 1
fi
```

## 工具脚本

### scripts/fix_filenames.py
批量重命名文件，移除空格并规范化 Unicode。

### scripts/read_markdown.py
读取 Markdown 文件的包装器，处理中文路径问题。

### 使用方法

```bash
# 修复所有文件名
python3 scripts/fix_filenames.py

# 读取单个文件
python3 scripts/read_markdown.py "docs/tasks/文件名.md"

# 检查文件是否可读取
python3 -c "from pathlib import Path; print(Path('文件名.md').exists())"
```

## 已修复的文件

以下文件已规范化（无需再次修复）：

```
docs/tasks/
├── 2026-03-25-子任务 A-实盘引擎热重载与稳定性重构.md
├── 2026-03-25-子任务 B-策略工作台与 CRUD 接口开发.md
├── 2026-03-25-子任务 C-信号结果动态标签系统重构.md
├── 2026-03-25-子任务 E-递归表单驱动与动态预览重构.md
├── 2026-03-25-子任务 F-强类型递归引擎与 Schema 自动化开发.md
└── 叮盘狗 - 系统演进全景路线图.md
```

## 未来新增文件时

创建新文件时遵循以下命名规则：

1. **使用连字符替代空格**
   - ✅ `子任务 F-强类型递归引擎.md`
   - ❌ `子任务 F - 强类型递归引擎.md`

2. **统一使用小写字母（可选）**
   - ✅ `task-f-recursive-engine.md`
   - ⚠️ `Task-F-Recursive-Engine.md` (可能在某些系统有问题)

3. **中文文件名使用标准输入**
   - 直接从系统输入法输入，避免复制粘贴

4. **提交前检查**
   ```bash
   # 检查文件名
   git status

   # 如有问题，运行修复脚本
   python3 scripts/fix_filenames.py
   ```

## 参考资源

- [Unicode 规范化形式](https://unicode.org/reports/tr15/)
- [macOS 文件系统 Unicode 处理](https://developer.apple.com/documentation/foundation/nsfilemanager/1413444-fileexistsatpath)
- [Python unicodedata 模块](https://docs.python.org/3/library/unicodedata.html)

---

**最后更新**: 2026-03-26
