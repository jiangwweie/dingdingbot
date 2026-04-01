# T8 - 订单详情与 K 线图渲染任务计划

## 任务背景
PMS 回测修复阶段 C (前端展示)，需要实现订单详情与 K 线图集成。

## 需求详情

### 功能需求
1. ✅ 订单详情展示 (抽屉或对话框)
2. ✅ K 线图标注订单位置 (入场点/出场点/止盈点)
3. ✅ 订单位置可视化

### API 契约

**后端 API 已存在**:
- `GET /api/v3/orders/{order_id}/klines?symbol={symbol}` - 获取订单详情和 K 线数据
- `GET /api/v3/backtest/reports` - 获取回测报告列表
- `GET /api/v3/backtest/reports/{id}` - 获取回测报告详情

**前端 API 客户端已存在**:
- `fetchOrderKlineContext(orderId, symbol)` - 获取订单 K 线上下文

## 任务分解

### T8-1: 后端 API 实现 ✅
- [x] 现有订单详情 API 已满足需求 (`/api/v3/orders/{order_id}/klines`)

### T8-2: 前端组件实现 ✅
- [x] OrderDetailsDrawer 组件已存在并扩展
- [x] K 线图集成 (使用 Recharts)
- [x] 订单位置标记 (ReferenceDot 标注)
- [x] K 线 Tooltip 显示 OHLC 数据

### T8-3: SST 测试 ✅
- [x] 前端组件测试创建 (`OrderDetailsDrawer.test.tsx`)

## 已完成工作

### 1. OrderDetailsDrawer 组件扩展
- 添加 `showKlineChart` 属性 (默认 true)
- 集成 K 线图展示 (使用 Recharts LineChart)
- 实现订单标记 (入场点/止盈点/止损点)
- 添加 K 线数据 Tooltip
- 加载/错误/空状态处理

### 2. 辅助函数
- `getMarkerColor(type)` - 根据标记类型返回颜色
- `KlineTooltip` - 自定义 K 线数据提示

### 3. SST 测试覆盖
- 基本渲染测试
- 订单参数显示测试
- 进度条显示测试
- 取消订单功能测试
- K 线图集成测试
- 关闭功能测试

## 进度追踪
- 启动时间：2026-04-01
- 完成时间：2026-04-01
- 状态：✅ 已完成
