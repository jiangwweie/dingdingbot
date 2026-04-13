/**
 * Backtest Page 完整测试
 *
 * 测试覆盖：
 * - 初始渲染 (4 个测试)
 * - 快速配置区交互 (2 个测试)
 * - 高级配置折叠 (2 个测试)
 * - 表单验证 (2 个测试)
 * - 回测执行流程 (2 个测试)
 * - 错误处理 (1 个测试)
 * - 结果展示 (2 个测试)
 * - 策略导入与历史 (2 个测试)
 *
 * 共计：17 个测试用例
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import Backtest from '../Backtest';

// ============================================================
// Mock API 模块
// ============================================================

vi.mock('../../lib/api', () => ({
  runSignalBacktest: vi.fn(),
  fetchBacktestSignals: vi.fn().mockResolvedValue({ signals: [] }),
}));

const { runSignalBacktest, fetchBacktestSignals } = await import('../../lib/api');

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
      <button onClick={() => onStartChange(1700000000000)}>设置开始时间</button>
      <button onClick={() => onEndChange(1700086400000)}>设置结束时间</button>
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
        <button onClick={() => onSelect({ id: 'template-1', name: 'Pinbar 保守策略' })}>
          选择 Pinbar 策略
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

const mockBacktestReport = {
  total_signals: 15,
  total_filtered: 42,
  filtered_by_filters: {
    ema_trend: 25,
    mtf_validation: 12,
    volume_surge: 5,
  },
  signal_logs: [
    {
      timestamp: 1700000000000,
      symbol: 'BTC/USDT:USDT',
      timeframe: '1h',
      strategy_name: 'Pinbar 保守策略',
      trigger_type: 'pinbar',
      trigger_passed: true,
      filters_passed: [
        { node_name: 'ema', passed: true },
        { node_name: 'mtf', passed: true },
      ],
      signal_fired: true,
      direction: 'long',
      entry_price: 52000,
      stop_loss: 51000,
    },
  ],
  execution_time_ms: 1250,
  klines_analyzed: 1000,
  signal_stats: {
    signals_fired: 15,
    filtered_by_filters: {
      ema_trend: 25,
      mtf_validation: 12,
      volume_surge: 5,
    },
  },
  attempts: [],
  candles_analyzed: 1000,
};

// ============================================================
// Tests
// ============================================================

describe('Backtest Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ============================================================
  // 1. 初始渲染测试 (4 个测试)
  // ============================================================

  describe('初始渲染', () => {
    it('renders symbol selector with 8 options', () => {
      render(<Backtest />);
      const symbolSelect = screen.getByTestId('symbol-select');
      expect(symbolSelect).toBeInTheDocument();
      expect(symbolSelect.querySelectorAll('option').length).toBe(8);
    });

    it('renders timeframe selector with 7 options', () => {
      render(<Backtest />);
      const timeframeSelect = screen.getByTestId('timeframe-select');
      expect(timeframeSelect).toBeInTheDocument();
      expect(timeframeSelect.querySelectorAll('option').length).toBe(7);
    });

    it('renders date range picker', () => {
      render(<Backtest />);
      expect(screen.getByTestId('date-picker')).toBeInTheDocument();
    });

    it('renders run backtest button', () => {
      render(<Backtest />);
      const runButton = screen.getByTestId('run-backtest-btn');
      expect(runButton).toBeInTheDocument();
      expect(runButton).toBeDisabled();
    });
  });

  // ============================================================
  // 2. 快速配置区交互 (2 个测试)
  // ============================================================

  describe('快速配置区交互', () => {
    it('updates symbol state on selection', () => {
      render(<Backtest />);
      const symbolSelect = screen.getByTestId('symbol-select');
      fireEvent.change(symbolSelect, { target: { value: 'ETH/USDT:USDT' } });
      expect(symbolSelect).toHaveValue('ETH/USDT:USDT');
    });

    it('updates timeframe state on selection', () => {
      render(<Backtest />);
      const timeframeSelect = screen.getByTestId('timeframe-select');
      fireEvent.change(timeframeSelect, { target: { value: '4h' } });
      expect(timeframeSelect).toHaveValue('4h');
    });
  });

  // ============================================================
  // 3. 高级配置折叠 (2 个测试)
  // ============================================================

  describe('高级配置折叠', () => {
    it('advanced config collapsed by default', () => {
      render(<Backtest />);
      expect(screen.getByText('高级配置')).toBeInTheDocument();
      expect(screen.queryByTestId('strategy-builder')).not.toBeInTheDocument();
    });

    it('toggles expand/collapse on click', async () => {
      render(<Backtest />);
      const expandButton = screen.getByText('高级配置').closest('div');
      fireEvent.click(expandButton!);
      await waitFor(() => {
        expect(screen.getByTestId('strategy-builder')).toBeInTheDocument();
      });
      fireEvent.click(expandButton!);
      await waitFor(() => {
        expect(screen.queryByTestId('strategy-builder')).not.toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 4. 表单验证 (2 个测试)
  // ============================================================

  describe('表单验证', () => {
    it('shows error when date not selected', async () => {
      render(<Backtest />);
      const expandButton = screen.getByText('高级配置').closest('div');
      fireEvent.click(expandButton!);
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });
      const runButton = screen.getByRole('button', { name: /一键执行回测/i });
      fireEvent.click(runButton);
      await waitFor(() => {
        expect(screen.getByText('请选择起始和结束时间')).toBeInTheDocument();
      });
    });

    it('shows error when start > end date', async () => {
      render(<Backtest />);
      const expandButton = screen.getByText('高级配置').closest('div');
      fireEvent.click(expandButton!);
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });
      const datePicker = screen.getByTestId('date-picker');
      const endBtn = within(datePicker).getByText('设置结束时间');
      const startBtn = within(datePicker).getByText('设置开始时间');
      fireEvent.click(endBtn);
      fireEvent.click(startBtn);
      const runButton = screen.getByRole('button', { name: /一键执行回测/i });
      fireEvent.click(runButton);
      await waitFor(() => {
        expect(screen.getByText('起始时间必须早于结束时间')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 5. 回测执行流程 (2 个测试)
  // ============================================================

  describe('回测执行流程', () => {
    it('calls API with correct payload on run', async () => {
      vi.mocked(runSignalBacktest).mockResolvedValue(mockBacktestReport as any);
      render(<Backtest />);
      const expandButton = screen.getByText('高级配置').closest('div');
      fireEvent.click(expandButton!);
      const symbolSelect = screen.getByRole('combobox');
      const timeframeSelect = screen.getAllByRole('combobox')[1];
      fireEvent.change(symbolSelect, { target: { value: 'ETH/USDT:USDT' } });
      fireEvent.change(timeframeSelect, { target: { value: '4h' } });
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });
      const datePicker = screen.getByTestId('date-picker');
      const startBtn = within(datePicker).getByText('设置开始时间');
      const endBtn = within(datePicker).getByText('设置结束时间');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);
      const runButton = screen.getByTestId('run-backtest-btn');
      fireEvent.click(runButton);
      await waitFor(() => {
        expect(runSignalBacktest).toHaveBeenCalledWith(
          expect.objectContaining({
            symbol: 'ETH/USDT:USDT',
            timeframe: '4h',
            start_time: 1700000000000,
            end_time: 1700086400000,
          })
        );
      });
    });

    it('shows loading state during execution', async () => {
      vi.mocked(runSignalBacktest).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockBacktestReport as any), 100))
      );
      render(<Backtest />);
      const expandButton = screen.getByText('高级配置').closest('div');
      fireEvent.click(expandButton!);
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });
      const datePicker = screen.getByTestId('date-picker');
      const startBtn = within(datePicker).getByText('设置开始时间');
      const endBtn = within(datePicker).getByText('设置结束时间');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);
      const runButton = screen.getByTestId('run-backtest-btn');
      fireEvent.click(runButton);
      await waitFor(() => {
        expect(screen.getByText('回测引擎运行中...')).toBeInTheDocument();
      });
      await waitFor(() => {
        expect(screen.queryByText('回测引擎运行中...')).not.toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 6. 错误处理 (1 个测试)
  // ============================================================

  describe('错误处理', () => {
    it('shows error message on API failure', async () => {
      vi.mocked(runSignalBacktest).mockRejectedValue({
        info: {
          detail: [
            { loc: ['body', 'symbol'], msg: 'invalid symbol' },
          ],
        },
      });
      render(<Backtest />);
      const expandButton = screen.getByText('高级配置').closest('div');
      fireEvent.click(expandButton!);
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });
      const datePicker = screen.getByTestId('date-picker');
      const startBtn = within(datePicker).getByText('设置开始时间');
      const endBtn = within(datePicker).getByText('设置结束时间');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);
      const runButton = screen.getByTestId('run-backtest-btn');
      fireEvent.click(runButton);
      await waitFor(() => {
        expect(screen.getByText('回测失败')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 7. 回测结果展示 (2 个测试)
  // ============================================================

  describe('回测结果展示', () => {
    it('displays backtest report dashboard after successful execution', async () => {
      vi.mocked(runSignalBacktest).mockResolvedValue(mockBacktestReport as any);
      render(<Backtest />);
      const expandButton = screen.getByText('高级配置').closest('div');
      fireEvent.click(expandButton!);
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });
      const datePicker = screen.getByTestId('date-picker');
      const startBtn = within(datePicker).getByText('设置开始时间');
      const endBtn = within(datePicker).getByText('设置结束时间');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);
      const runButton = screen.getByTestId('run-backtest-btn');
      fireEvent.click(runButton);
      await waitFor(() => {
        expect(screen.getByText('符合策略信号')).toBeInTheDocument();
      });
      expect(screen.getByText('被拦截信号')).toBeInTheDocument();
      expect(screen.getByText('分析 K 线数')).toBeInTheDocument();
    });

    it('switches between dashboard and logs view', async () => {
      vi.mocked(runSignalBacktest).mockResolvedValue(mockBacktestReport as any);
      render(<Backtest />);
      const expandButton = screen.getByText('高级配置').closest('div');
      fireEvent.click(expandButton!);
      await waitFor(() => {
        const addStrategyBtn = screen.getByText('添加策略');
        fireEvent.click(addStrategyBtn);
      });
      const datePicker = screen.getByTestId('date-picker');
      const startBtn = within(datePicker).getByText('设置开始时间');
      const endBtn = within(datePicker).getByText('设置结束时间');
      fireEvent.click(startBtn);
      fireEvent.click(endBtn);
      const runButton = screen.getByTestId('run-backtest-btn');
      fireEvent.click(runButton);
      await waitFor(() => {
        expect(screen.getByText('符合策略信号')).toBeInTheDocument();
      });
      const logsTab = screen.getByText('日志流水');
      fireEvent.click(logsTab);
      await waitFor(() => {
        expect(screen.getByText('时间戳')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 8. 策略导入与历史 (2 个测试)
  // ============================================================

  describe('策略导入与历史', () => {
    it('opens template picker on import button click', async () => {
      render(<Backtest />);
      const importButton = screen.getByText('从策略工作台导入');
      fireEvent.click(importButton);
      await waitFor(() => {
        expect(screen.getByTestId('template-picker')).toBeInTheDocument();
      });
    });

    it('opens history drawer on history button click', async () => {
      render(<Backtest />);
      const historyButton = screen.getByText('回测历史');
      fireEvent.click(historyButton);
      await waitFor(() => {
        expect(screen.getByText('回测信号历史')).toBeInTheDocument();
      });
    });
  });
});
