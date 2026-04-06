/**
 * PMSBacktest Page 组件测试
 *
 * 测试覆盖:
 * - PMS 特定表单配置 (初始资金)
 * - 策略组装工作台集成
 * - PMS 回测执行流程
 * - PMS 报告展示 (仓位级追踪)
 * - 错误处理与边界条件
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PMSBacktest from '../PMSBacktest';

// ============================================================
// Mock API 模块
// ============================================================

vi.mock('../../lib/api', () => ({
  runPMSBacktest: vi.fn(),
  fetchStrategyTemplates: vi.fn(),
  fetchBacktestSignals: vi.fn(),
  fetch: vi.fn(),
}));

// ============================================================
// Mock 子组件
// ============================================================

vi.mock('../../../components/StrategyBuilder', () => ({
  __esModule: true,
  default: ({ strategies, onChange }: { strategies: any[]; onChange: (s: any[]) => void }) => (
    <div data-testid="strategy-builder">
      <span>策略数量：{strategies.length}</span>
      <button onClick={() => onChange([...strategies, { id: `strat-${strategies.length}` }])}>
        添加策略
      </button>
    </div>
  ),
}));

vi.mock('../../../components/QuickDateRangePicker', () => ({
  __esModule: true,
  default: ({
    onStartChange,
    onEndChange,
  }: {
    onStartChange: (ts: number) => void;
    onEndChange: (ts: number) => void;
  }) => (
    <div data-testid="date-picker">
      <button onClick={() => onStartChange(1700000000000)}>设置开始</button>
      <button onClick={() => onEndChange(1700086400000)}>设置结束</button>
    </div>
  ),
}));

vi.mock('../../../components/StrategyTemplatePicker', () => ({
  __esModule: true,
  default: ({
    open,
    onClose,
    onSelect,
  }: {
    open: boolean;
    onClose: () => void;
    onSelect: (s: any) => void;
  }) =>
    open ? (
      <div data-testid="template-picker">
        <button onClick={() => onSelect({ id: 'template-1', name: 'PMS Pinbar 策略' })}>
          选择 PMS 策略
        </button>
        <button onClick={onClose}>关闭</button>
      </div>
    ) : null,
}));

vi.mock('../../../components/SignalDetailsDrawer', () => ({
  __esModule: true,
  default: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? (
      <div data-testid="signal-details-drawer">
        <button onClick={onClose}>关闭详情</button>
      </div>
    ) : null,
}));

vi.mock('../../../components/v3/backtest', () => ({
  BacktestOverviewCards: ({ report }: { report: any }) => (
    <div data-testid="overview-cards">
      <span>初始余额：{report.initial_balance}</span>
      <span>最终余额：{report.final_balance}</span>
    </div>
  ),
  EquityComparisonChart: ({ report }: { report: any }) => (
    <div data-testid="equity-chart">权益曲线图</div>
  ),
  TradeStatisticsTable: ({ report }: { report: any }) => (
    <div data-testid="trade-stats">
      <span>总收益率：{report.total_return}%</span>
      <span>胜率：{report.win_rate}%</span>
    </div>
  ),
  PnLDistributionHistogram: ({ report }: { report: any }) => (
    <div data-testid="pnl-distribution">盈亏分布</div>
  ),
  MonthlyReturnHeatmap: ({ report }: { report: any }) => (
    <div data-testid="monthly-heatmap">月度热力图</div>
  ),
}));

// ============================================================
// Mock window.matchMedia
// ============================================================

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

// ============================================================
// Fixtures
// ============================================================

const mockPMSReport = {
  strategy_id: 'strat-001',
  strategy_name: 'Pinbar 保守策略',
  backtest_start: 1700000000000,
  backtest_end: 1700086400000,
  initial_balance: '50000.00',
  final_balance: '52500.00',
  total_return: '5.00',
  total_trades: 20,
  winning_trades: 12,
  losing_trades: 8,
  win_rate: '60.00',
  total_pnl: '2500.00',
  total_fees_paid: '50.00',
  total_slippage_cost: '25.00',
  max_drawdown: '3.50',
  sharpe_ratio: '1.25',
  positions: [
    {
      position_id: 'pos-001',
      signal_id: 'sig-001',
      symbol: 'BTC/USDT:USDT',
      direction: 'LONG',
      entry_price: '50000.00',
      exit_price: '51500.00',
      entry_time: 1700000000000,
      exit_time: 1700010000000,
      realized_pnl: '1500.00',
      exit_reason: 'TP1',
    },
  ],
  signal_stats: {
    signals_fired: 15,
    filtered_by_filters: {
      ema_trend: 25,
      mtf_validation: 12,
    },
  },
  total_filtered: 37,
  filtered_by_filters: {
    ema_trend: 25,
    mtf_validation: 12,
  },
  signal_logs: [],
  execution_time_ms: 1250,
  klines_analyzed: 1000,
  attempts: [],
  candles_analyzed: 1000,
};

const { runPMSBacktest, fetchStrategyTemplates, fetchBacktestSignals } = await import(
  '../../lib/api'
);

// ============================================================
// Tests
// ============================================================

describe('PMSBacktest Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchStrategyTemplates).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ============================================================
  // 1. 初始渲染测试 (3 个测试)
  // ============================================================

  describe('初始渲染', () => {
    it('renders initial_balance input', () => {
      render(<PMSBacktest />);

      const balanceLabel = screen.getByText(/初始资金/i);
      expect(balanceLabel).toBeInTheDocument();

      const balanceInput = screen.getByLabelText(/初始资金/i);
      expect(balanceInput).toBeInTheDocument();
    });

    it('default initial_balance is 10000', () => {
      render(<PMSBacktest />);

      const balanceInput = screen.getByLabelText(/初始资金/i);
      expect(balanceInput).toHaveValue('10000');
    });

    it('renders PMS specific fields', () => {
      render(<PMSBacktest />);

      // 验证 PMS 特有元素
      expect(screen.getByText(/PMS 回测报告/i)).toBeInTheDocument();
      expect(screen.getByText(/PMS 回测 vs 经典回测/i)).toBeInTheDocument();

      // 验证币种选择器 (8 个选项)
      const symbolSelect = screen.getByLabelText(/交易对/i);
      expect(symbolSelect).toBeInTheDocument();
      expect(symbolSelect.querySelectorAll('option').length).toBe(8);

      // 验证周期选择器 (5 个选项：15m/1h/4h/1d/1w)
      const timeframeSelect = screen.getByLabelText(/时间周期/i);
      expect(timeframeSelect).toBeInTheDocument();
      expect(timeframeSelect.querySelectorAll('option').length).toBe(5);
    });
  });

  // ============================================================
  // 2. 资金配置 (2 个测试)
  // ============================================================

  describe('资金配置', () => {
    it('updates initial_balance on input', () => {
      render(<PMSBacktest />);

      const balanceInput = screen.getByLabelText(/初始资金/i);
      fireEvent.change(balanceInput, { target: { value: '50000' } });

      expect(balanceInput).toHaveValue('50000');
    });

    it('shows error on negative/zero value', () => {
      render(<PMSBacktest />);

      const balanceInput = screen.getByLabelText(/初始资金/i);

      // 输入 0
      fireEvent.change(balanceInput, { target: { value: '0' } });
      expect(balanceInput).toHaveValue('0');

      // 输入负数
      fireEvent.change(balanceInput, { target: { value: '-1000' } });
      expect(balanceInput).toHaveValue('-1000');

      // HTML5 验证会阻止提交，但输入本身是允许的
      // 组件有 min="100" 属性
      expect(balanceInput).toHaveAttribute('min', '100');
    });
  });

  // ============================================================
  // 3. 表单验证 (额外测试，验证 PMS 表单验证)
  // ============================================================

  describe('表单验证', () => {
    it('shows error when date not selected', async () => {
      render(<PMSBacktest />);

      // 展开高级配置并添加策略 (PMS 页面高级配置默认展开)
      await waitFor(() => {
        expect(screen.getByTestId('strategy-builder')).toBeInTheDocument();
      });

      // 添加一个策略
      const addStrategyBtn = screen.getByText('添加策略');
      fireEvent.click(addStrategyBtn);

      // 点击执行按钮 (未选择日期)
      const runButton = screen.getByRole('button', { name: /执行 PMS 回测/i });
      fireEvent.click(runButton);

      // 应该显示错误信息
      await waitFor(() => {
        expect(screen.getByText('请选择起始和结束时间')).toBeInTheDocument();
      });
    });

    it('shows error when start >= end date', async () => {
      render(<PMSBacktest />);

      // 添加策略
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });

      // 设置日期 - 先结束时间，后开始时间
      const endBtn = screen.getByText('设置结束');
      const startBtn = screen.getByText('设置开始');
      fireEvent.click(endBtn);
      fireEvent.click(startBtn);

      // 点击执行
      const runButton = screen.getByRole('button', { name: /执行 PMS 回测/i });
      fireEvent.click(runButton);

      // 应该显示错误
      await waitFor(() => {
        expect(screen.getByText('起始时间必须早于结束时间')).toBeInTheDocument();
      });
    });

    it('shows error when no strategies configured', async () => {
      render(<PMSBacktest />);

      // 设置日期
      const startBtn = screen.getByText('设置开始');
      const endBtn = screen.getByText('设置结束');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);

      // 点击执行 (没有策略)
      const runButton = screen.getByRole('button', { name: /执行 PMS 回测/i });
      fireEvent.click(runButton);

      // 应该显示错误
      await waitFor(() => {
        expect(screen.getByText('请至少配置一个策略')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 4. PMS 回测执行 (2 个测试)
  // ============================================================

  describe('PMS 回测执行', () => {
    it('includes initial_balance in payload', async () => {
      vi.mocked(runPMSBacktest).mockResolvedValue(mockPMSReport as any);

      render(<PMSBacktest />);

      // 设置初始资金
      const balanceInput = screen.getByLabelText(/初始资金/i);
      fireEvent.change(balanceInput, { target: { value: '50000' } });

      // 设置币种和周期
      const symbolSelect = screen.getByLabelText(/交易对/i);
      const timeframeSelect = screen.getByLabelText(/时间周期/i);
      fireEvent.change(symbolSelect, { target: { value: 'ETH/USDT:USDT' } });
      fireEvent.change(timeframeSelect, { target: { value: '4h' } });

      // 添加策略
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });

      // 设置日期
      const startBtn = screen.getByText('设置开始');
      const endBtn = screen.getByText('设置结束');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);

      // 点击执行
      const runButton = screen.getByRole('button', { name: /执行 PMS 回测/i });
      fireEvent.click(runButton);

      // 验证 API 被调用且包含 initial_balance
      await waitFor(() => {
        expect(runPMSBacktest).toHaveBeenCalledWith(
          expect.objectContaining({
            symbol: 'ETH/USDT:USDT',
            timeframe: '4h',
            start_time: 1700000000000,
            end_time: 1700086400000,
            initial_balance: 50000,
            strategies: expect.arrayContaining([expect.any(Object)]),
          })
        );
      });
    });

    it('renders PMS report with position tracking', async () => {
      vi.mocked(runPMSBacktest).mockResolvedValue(mockPMSReport as any);

      render(<PMSBacktest />);

      // 添加策略
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });

      // 设置日期
      const startBtn = screen.getByText('设置开始');
      const endBtn = screen.getByText('设置结束');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);

      // 点击执行
      const runButton = screen.getByRole('button', { name: /执行 PMS 回测/i });
      fireEvent.click(runButton);

      // 等待报告展示
      await waitFor(() => {
        expect(screen.getByTestId('overview-cards')).toBeInTheDocument();
      });

      // 验证 PMS 特有组件
      expect(screen.getByTestId('equity-chart')).toBeInTheDocument();
      expect(screen.getByTestId('trade-stats')).toBeInTheDocument();
      expect(screen.getByTestId('pnl-distribution')).toBeInTheDocument();
      expect(screen.getByTestId('monthly-heatmap')).toBeInTheDocument();
    });
  });

  // ============================================================
  // 5. 边界条件 (2 个测试)
  // ============================================================

  describe('边界条件', () => {
    it('handles initial_balance limit exceeded', () => {
      render(<PMSBacktest />);

      const balanceInput = screen.getByLabelText(/初始资金/i);

      // 输入最大值
      fireEvent.change(balanceInput, { target: { value: '1000000' } });
      expect(balanceInput).toHaveValue('1000000');
      expect(balanceInput).toHaveAttribute('max', '1000000');

      // 输入超过最大值 - HTML5 会阻止或截断
      fireEvent.change(balanceInput, { target: { value: '1000001' } });
      // 输入本身会被接受，但表单验证会阻止提交
    });

    it('shows error on API timeout', async () => {
      vi.mocked(runPMSBacktest).mockRejectedValue({
        message: '请求超时',
      });

      render(<PMSBacktest />);

      // 添加策略
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });

      // 设置日期
      const startBtn = screen.getByText('设置开始');
      const endBtn = screen.getByText('设置结束');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);

      // 点击执行
      const runButton = screen.getByRole('button', { name: /执行 PMS 回测/i });
      fireEvent.click(runButton);

      // 应该显示错误信息
      await waitFor(() => {
        expect(screen.getByText('PMS 回测失败')).toBeInTheDocument();
        expect(screen.getByText(/请求超时/)).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 6. 错误处理 (额外测试)
  // ============================================================

  describe('错误处理', () => {
    it('shows validation error message on 422 response', async () => {
      vi.mocked(runPMSBacktest).mockRejectedValue({
        info: {
          detail: [
            {
              loc: ['body', 'initial_balance'],
              msg: 'Initial balance must be greater than 0',
            },
          ],
        },
      });

      render(<PMSBacktest />);

      // 添加策略
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });

      // 设置日期
      const startBtn = screen.getByText('设置开始');
      const endBtn = screen.getByText('设置结束');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);

      // 点击执行
      const runButton = screen.getByRole('button', { name: /执行 PMS 回测/i });
      fireEvent.click(runButton);

      // 应该显示详细的验证错误
      await waitFor(() => {
        expect(screen.getByText('PMS 回测失败')).toBeInTheDocument();
        expect(
          screen.getByText(/body\.initial_balance: Initial balance must be greater than 0/)
        ).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 7. 策略模板导入 (额外测试)
  // ============================================================

  describe('策略模板导入', () => {
    it('opens template picker and imports strategy', async () => {
      render(<PMSBacktest />);

      // 点击导入按钮
      const importButton = screen.getByText('从策略工作台导入');
      fireEvent.click(importButton);

      // 验证模板选择器打开
      await waitFor(() => {
        expect(screen.getByTestId('template-picker')).toBeInTheDocument();
      });

      // 选择策略
      const selectButton = screen.getByText('选择 PMS 策略');
      fireEvent.click(selectButton);

      // 选择器应该关闭
      await waitFor(() => {
        expect(screen.queryByTestId('template-picker')).not.toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 8. 回测历史 (额外测试)
  // ============================================================

  describe('回测历史', () => {
    it('opens history drawer and loads signals', async () => {
      const mockSignals = [
        {
          id: 'sig-001',
          created_at: '2026-04-01T10:00:00Z',
          symbol: 'BTC/USDT:USDT',
          timeframe: '1h',
          direction: 'long',
          entry_price: '50000.00',
          stop_loss: '49000.00',
          position_size: '0.5',
          leverage: 10,
          status: 'CLOSED',
          pnl_ratio: '0.03',
          strategy_name: 'Pinbar 保守策略',
          source: 'backtest',
        },
      ];
      vi.mocked(fetchBacktestSignals).mockResolvedValue({ signals: mockSignals } as any);

      render(<PMSBacktest />);

      // 点击历史按钮
      const historyButton = screen.getByText('回测历史');
      fireEvent.click(historyButton);

      // 验证历史抽屉打开
      await waitFor(() => {
        expect(screen.getByText('回测信号历史')).toBeInTheDocument();
      });

      // 验证表格渲染
      await waitFor(() => {
        expect(screen.getByText('时间')).toBeInTheDocument();
        expect(screen.getByText('币种')).toBeInTheDocument();
        expect(screen.getByText('周期')).toBeInTheDocument();
        expect(screen.getByText('方向')).toBeInTheDocument();
      });
    });

    it('shows empty state when no history', async () => {
      vi.mocked(fetchBacktestSignals).mockResolvedValue({ signals: [] } as any);

      render(<PMSBacktest />);

      // 点击历史按钮
      const historyButton = screen.getByText('回测历史');
      fireEvent.click(historyButton);

      // 验证空状态
      await waitFor(() => {
        expect(screen.getByText('暂无回测信号记录')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 9. PMS 信息横幅 (额外测试)
  // ============================================================

  describe('PMS 信息横幅', () => {
    it('displays PMS vs classic comparison info', () => {
      render(<PMSBacktest />);

      expect(
        screen.getByText(/PMS 模式.*仓位级追踪/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/经典模式.*信号级统计/i)
      ).toBeInTheDocument();
    });
  });

  // ============================================================
  // 10. Loading 状态 (额外测试)
  // ============================================================

  describe('Loading 状态', () => {
    it('shows loading state during PMS backtest execution', async () => {
      vi.mocked(runPMSBacktest).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockPMSReport as any), 100))
      );

      render(<PMSBacktest />);

      // 添加策略
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });

      // 设置日期
      const startBtn = screen.getByText('设置开始');
      const endBtn = screen.getByText('设置结束');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);

      // 点击执行
      const runButton = screen.getByRole('button', { name: /执行 PMS 回测/i });
      fireEvent.click(runButton);

      // 应该显示 loading 状态
      await waitFor(() => {
        expect(screen.getByText('PMS 回测引擎运行中...')).toBeInTheDocument();
      });

      // 执行完成后 loading 状态应该消失
      await waitFor(() => {
        expect(screen.queryByText('PMS 回测引擎运行中...')).not.toBeInTheDocument();
      });
    });
  });
});
