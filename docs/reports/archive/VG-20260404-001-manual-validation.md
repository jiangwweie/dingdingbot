# 前端页面交互验证指南 - VG-20260404-001

**生成日期**: 2026-04-04
**验证类型**: 关键页面手动验证（5 分钟）
**前置条件**: 前端（3000）+ 后端（8000）已运行

---

## ✅ API 验证结果

| API 端点 | 状态 | 数据 |
|----------|------|------|
| `/api/config/profiles` | ✅ 正常 | default profile |
| `/api/v3/orders?limit=5` | ✅ 正常 | 2238 个订单 |
| `/api/strategies` | ✅ 正常 | 1 个策略 |

---

## 🔍 页面验证清单（4 个关键页面）

### 1️⃣ Config 页面（策略参数配置）

**URL**: http://localhost:3000/config

**验证步骤**（30 秒）:
```markdown
1. 打开页面，检查是否显示 "default" Profile
2. 点击 "Pinbar 参数" 区域
3. 查看参数表单是否正常渲染：
   - min_wick_ratio: 0.6
   - max_body_ratio: 0.3
   - body_position_tolerance: 0.1
4. ✅ 验证点：参数值是否为数字（非 "0.60" 字符串）
```

**预期结果**:
- ✅ Profile 下拉菜单显示 "default"
- ✅ 参数表单显示正确的数字值
- ✅ 无 "toFixed is not a function" 错误

**如果失败**:
- 检查浏览器控制台错误
- 刷新页面（Cmd+Shift+R）

---

### 2️⃣ Orders 页面（订单列表）

**URL**: http://localhost:3000/orders

**验证步骤**（30 秒）:
```markdown
1. 打开页面，等待订单列表加载
2. 检查订单数量是否显示（预期：2000+）
3. 测试虚拟滚动：
   - 向下滚动查看更多订单
   - 检查滚动是否流畅（无卡顿）
4. ✅ 验证点：是否显示订单树形结构
```

**预期结果**:
- ✅ 订单列表正常渲染（虚拟滚动）
- ✅ 显示订单详情（symbol, status, price）
- ✅ 无 "Cannot read property 'length' of null" 错误

**如果失败**:
- 强制刷新（Cmd+Shift+R）
- 检查 react-window 组件渲染

---

### 3️⃣ Strategy 页面（动态表单）

**URL**: http://localhost:3000/strategy

**验证步骤**（1 分钟）:
```markdown
1. 打开页面，检查是否显示策略列表
2. 点击 "创建新策略" 按钮
3. 测试动态表单交互：
   - 添加触发器（Trigger）
   - 选择触发器类型（Pinbar/Engulfing）
   - 添加过滤器（Filter）
   - 选择过滤器类型（EMA/MTF）
4. ✅ 验证点：表单是否动态添加/删除
```

**预期结果**:
- ✅ 触发器/过滤器下拉菜单正常
- ✅ 动态添加表单项成功
- ✅ 参数输入框正常渲染

**如果失败**:
- 检查动态表单组件加载
- 测试删除按钮功能

---

### 4️⃣ Profile 管理页面

**URL**: http://localhost:3000/config （Profile 区域）

**验证步骤**（1 分钟）:
```markdown
1. 在 Config 页面顶部找到 Profile 管理区域
2. 测试 CRUD 功能：
   - 点击 Profile 下拉菜单
   - 测试 "创建新 Profile"
   - 测试 "切换 Profile"
   - 测试 "导出 Profile"
3. ✅ 验证点：Profile 操作是否成功
```

**预期结果**:
- ✅ Profile 下拉菜单显示列表
- ✅ 创建新 Profile 对话框弹出
- ✅ 切换 Profile 后参数更新

**如果失败**:
- 检查 Profile API 调用
- 测试导入/导出功能

---

## 📊 验证汇总表

| 页面 | 功能 | 验证点 | 状态 |
|------|------|--------|------|
| Config | 策略参数表单 | toFixed 修复 | ⏳ 待验证 |
| Orders | 虚拟滚动 | null 检查修复 | ⏳ 待验证 |
| Strategy | 动态表单 | 添加/删除功能 | ⏳ 待验证 |
| Profile | CRUD 操作 | 创建/切换/导出 | ⏳ 待验证 |

---

## 🚀 快速验证流程

**总耗时**: 5 分钟

```bash
# 1. 打开浏览器
open http://localhost:3000/config

# 2. 依次验证 4 个页面（按上述步骤）

# 3. 记录验证结果
# - 成功：页面功能正常
# - 失败：截图 + 错误日志
```

---

## 🐛 失败处理

### 如果页面加载失败
```bash
# 检查前端日志
cd gemimi-web-front
npm run dev

# 检查后端日志
cd /Users/jiangwei/Documents/final
tail -f logs/app.log
```

### 如果功能异常
1. 打开浏览器开发者工具（Cmd+Option+I）
2. 查看 Console 标签页错误信息
3. 检查 Network 标签页 API 请求状态
4. 截图保存错误信息

---

## 📝 验证后汇报

完成验证后，请反馈：

**格式**:
```
✅ Config 页面：参数表单正常 / 失败原因
✅ Orders 页面：虚拟滚动正常 / 失败原因
✅ Strategy 页面：动态表单正常 / 失败原因
✅ Profile 管理：CRUD 操作正常 / 失败原因
```

---

*验证指南生成时间: 2026-04-04 21:15*
*验证类型: 手动快速验证*
*前置条件: 前端 + 后端正常运行*