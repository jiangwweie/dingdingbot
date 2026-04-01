# T7 - 回测记录列表页面实现

**创建时间**: 2026-04-01
**优先级**: P0
**预计工时**: 3 小时
**状态**: 进行中

---

## 需求详情

### 功能需求
1. ✅ 表格展示回测记录列表
2. ✅ 支持按策略/币种/时间范围筛选
3. ✅ 支持按收益率/胜率/创建时间排序
4. ✅ 支持分页

### API 契约

**GET /api/v3/backtest/reports**

**Request Query Params**:
```typescript
interface ListBacktestReportsRequest {
  strategyId?: string;
  symbol?: string;
  startDate?: number;      // 毫秒时间戳
  endDate?: number;        // 毫秒时间戳
  page?: number;           // 默认 1
  pageSize?: number;       // 默认 20
  sortBy?: 'total_return' | 'win_rate' | 'created_at';
  sortOrder?: 'asc' | 'desc';
}
```

**Response**:
```typescript
interface BacktestReportSummary {
  id: string;
  strategy_id: string;
  strategy_name: string;
  strategy_version: string;
  symbol: string;
  timeframe: string;
  backtest_start: number;
  backtest_end: number;
  created_at: number;
  total_return: string;     // Decimal 字符串
  total_trades: number;
  win_rate: string;         // Decimal 字符串
  total_pnl: string;        // Decimal 字符串
  max_drawdown: string;     // Decimal 字符串
}

interface ListBacktestReportsResponse {
  reports: BacktestReportSummary[];
  total: number;
  page: number;
  pageSize: number;
}
```

---

## 实现清单

### 后端 (src/interfaces/api.py)
- [ ] 导入 BacktestReportSummary 类型
- [ ] 实现 GET /api/v3/backtest/reports 端点
- [ ] 集成 BacktestReportRepository.list_reports 方法
- [ ] 添加错误处理

### 前端类型 (web-front/src/types/backtest.ts)
- [ ] BacktestReportSummary 接口
- [ ] ListBacktestReportsRequest 接口
- [ ] ListBacktestReportsResponse 接口

### 前端 API 客户端 (web-front/src/lib/api.ts)
- [ ] fetchBacktestReports 函数

### 前端组件 (web-front/src/components/v3/backtest/)
- [ ] BacktestReportsTable.tsx - 表格组件
- [ ] BacktestReportsFilters.tsx - 筛选表单
- [ ] BacktestReportsPagination.tsx - 分页器

### 前端页面 (web-front/src/pages/)
- [ ] BacktestReports.tsx - 主页面

---

## 测试计划

### 前端测试
- [ ] 组件渲染测试
- [ ] 筛选功能测试
- [ ] 排序功能测试
- [ ] 分页功能测试
- [ ] TypeScript 类型检查

---

## 参考文档

- [PMS 回测修复计划](./pms-backtest-fix-plan.md)
- [PMS 回测需求规格](./pms-backtest-requirements.md)
- BacktestReportRepository: `src/infrastructure/backtest_repository.py`

---

*最后更新：2026-04-01*
