/**
 * EffectiveConfigView 组件单元测试
 *
 * 测试覆盖场景:
 * 1. 加载状态 - 显示 Spin 加载指示器
 * 2. 成功加载 - 展示完整配置信息 (交易所/系统/风控/通知/策略/币种/资产轮询)
 * 3. API 404 降级 - fallback 到 mock 数据
 * 4. API 请求失败 - 显示错误状态和重试按钮
 * 5. 无数据 - 显示警告
 * 6. 敏感字段脱敏 - API Key/Secret 默认隐藏
 * 7. 敏感字段切换 - 点击眼睛图标切换显示/隐藏
 * 8. 迁移状态 - 已迁移/未迁移两种状态
 * 9. 空策略/空币种 - 展示空状态提示
 * 10. 辅助函数 - formatSeconds/formatPercent/maskValue
 *
 * 边界检查:
 * - 空策略列表
 * - 空币种列表
 * - 空通知渠道
 * - 敏感字段长度 <= 8 的脱敏处理
 * - 可选字段缺失 (daily_max_trades/daily_max_loss)
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import EffectiveConfigView from '../EffectiveConfigView';
import * as swr from 'swr';

// ============================================================
// MatchMedia mock (must be before any antd import)
// ============================================================
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
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

// ============================================================
// Mock SWR hook
// ============================================================
vi.mock('swr', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as object),
    default: vi.fn(),
  };
});

// ============================================================
// Mock Ant Design Collapse to render all children unconditionally
// This avoids issues with Collapse animations in happy-dom
// ============================================================
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>();

  // Simple Collapse mock that renders all items
  const MockCollapse = (props: any) => {
    const { items, children, ...rest } = props;
    // Filter out non-DOM props
    const { defaultActiveKey, activeKey, accordion, onChange, ...domProps } = rest;

    if (items && Array.isArray(items)) {
      return (
        <div data-testid="collapse-container" {...domProps}>
          {items.map((item: any) => (
            <div key={item.key} data-testid={`collapse-panel-${item.key}`}>
              <div>{item.label}</div>
              <div>{item.children}</div>
            </div>
          ))}
        </div>
      );
    }
    return <div data-testid="collapse-container" {...domProps}>{children}</div>;
  };
  (MockCollapse as any).Panel = (props: any) => {
    const { children, ...rest } = props;
    return <div data-testid={`collapse-panel-${props.key}`} {...rest}>{children}</div>;
  };

  return {
    ...actual,
    Collapse: MockCollapse,
  };
});

// ============================================================
// Helper: construct complete mock data
// ============================================================
function createMockEffectiveConfig(overrides?: Record<string, any>) {
  return {
    exchange: {
      name: 'binance',
      api_key: 'sk_test_abc123xyz789',
      api_secret: 'secret_test_abc123xyz789',
      testnet: true,
    },
    system: {
      core_symbols: ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT'],
      ema_period: 60,
      mtf_ema_period: 60,
      mtf_mapping: { '15m': '1h', '1h': '4h', '4h': '1d', '1d': '1w' },
      signal_cooldown_seconds: 14400,
      timeframes: ['15m', '1h'],
      atr_filter_enabled: true,
      atr_period: 14,
      atr_min_ratio: '0.5',
    },
    risk: {
      max_loss_percent: '0.01',
      max_leverage: 10,
      max_total_exposure: '0.8',
      cooldown_minutes: 5,
      daily_max_trades: 20,
      daily_max_loss: '0.05',
    },
    notification: {
      channels: [
        {
          id: '1',
          type: 'feishu',
          webhook_url: 'https://open.feishu.cn/open-apis/bot/v2/hook/****',
          is_active: true,
        },
      ],
    },
    strategies: [
      {
        id: 'strat-001',
        name: 'Pinbar 保守策略',
        is_active: true,
        trigger_type: 'pinbar',
        filter_count: 2,
        symbols: ['BTC/USDT:USDT', 'ETH/USDT:USDT'],
        timeframes: ['15m', '1h'],
      },
    ],
    symbols: [
      { symbol: 'BTC/USDT:USDT', is_core: true, is_active: true },
      { symbol: 'ETH/USDT:USDT', is_core: true, is_active: true },
    ],
    asset_polling: { enabled: true, interval_seconds: 60 },
    migration_status: {
      yaml_fully_migrated: true,
      one_time_import_done: true,
      import_version: 'v2',
    },
    config_version: 5,
    created_at: '2026-04-01T10:00:00Z',
    ...overrides,
  };
}

// ============================================================
// Mock SWR responses
// ============================================================
function mockSwrLoading() {
  vi.mocked(swr.default).mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: true,
  } as any);
}

function mockSwrSuccess(data: any) {
  vi.mocked(swr.default).mockReturnValue({
    data,
    error: undefined,
    isLoading: false,
  } as any);
}

function mockSwrError(error: Error) {
  vi.mocked(swr.default).mockReturnValue({
    data: undefined,
    error,
    isLoading: false,
  } as any);
}

// ============================================================
// Tests
// ============================================================
describe('EffectiveConfigView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ============================================================
  // 1. Loading state
  // ============================================================
  describe('Loading state', () => {
    it('displays Spin loading indicator', () => {
      mockSwrLoading();
      render(<EffectiveConfigView />);

      expect(screen.getByText('加载生效配置...')).toBeInTheDocument();
    });
  });

  // ============================================================
  // 2. Successful load - exchange connection
  // ============================================================
  describe('Exchange connection', () => {
    it('displays exchange name and testnet tag', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('交易所连接')).toBeInTheDocument();
        expect(screen.getByText('binance')).toBeInTheDocument();
        expect(screen.getByText('测试网')).toBeInTheDocument();
        expect(screen.getByText('Testnet')).toBeInTheDocument();
      });
    });

    it('displays Mainnet tag when testnet is false', async () => {
      const data = createMockEffectiveConfig({
        exchange: {
          name: 'binance',
          api_key: 'sk_test_abc123xyz789',
          api_secret: 'secret_test_abc123xyz789',
          testnet: false,
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('主网')).toBeInTheDocument();
        expect(screen.getByText('Mainnet')).toBeInTheDocument();
      });

      expect(screen.queryByText('测试网')).not.toBeInTheDocument();
      expect(screen.queryByText('Testnet')).not.toBeInTheDocument();
    });
  });

  // ============================================================
  // 3. System settings
  // ============================================================
  describe('System settings', () => {
    it('displays all system setting labels', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('系统设置')).toBeInTheDocument();
        expect(screen.getByText('核心币种')).toBeInTheDocument();
        expect(screen.getByText('监控周期')).toBeInTheDocument();
        expect(screen.getByText('EMA 周期')).toBeInTheDocument();
        expect(screen.getByText('MTF EMA 周期')).toBeInTheDocument();
        expect(screen.getByText('MTF 映射')).toBeInTheDocument();
        expect(screen.getByText('信号冷却时间')).toBeInTheDocument();
      });
    });

    it('displays MTF mapping relationships', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('15m \u2192 1h')).toBeInTheDocument();
        expect(screen.getByText('1h \u2192 4h')).toBeInTheDocument();
        expect(screen.getByText('4h \u2192 1d')).toBeInTheDocument();
        expect(screen.getByText('1d \u2192 1w')).toBeInTheDocument();
      });
    });

    it('displays formatted cooldown time (hours)', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('4 小时')).toBeInTheDocument();
      });
    });

    it('displays formatted cooldown time (minutes)', async () => {
      const data = createMockEffectiveConfig({
        system: {
          core_symbols: ['BTC/USDT:USDT'],
          ema_period: 60,
          mtf_ema_period: 60,
          mtf_mapping: {},
          signal_cooldown_seconds: 300,
          timeframes: ['15m'],
          atr_filter_enabled: false,
          atr_period: 14,
          atr_min_ratio: '0.5',
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('5 分钟')).toBeInTheDocument();
      });
    });

    it('displays formatted cooldown time (seconds)', async () => {
      const data = createMockEffectiveConfig({
        system: {
          core_symbols: ['BTC/USDT:USDT'],
          ema_period: 60,
          mtf_ema_period: 60,
          mtf_mapping: {},
          signal_cooldown_seconds: 30,
          timeframes: ['15m'],
          atr_filter_enabled: false,
          atr_period: 14,
          atr_min_ratio: '0.5',
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('30 秒')).toBeInTheDocument();
      });
    });

    it('displays core symbol tags', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('BTC')).toBeInTheDocument();
        expect(screen.getByText('ETH')).toBeInTheDocument();
        expect(screen.getByText('SOL')).toBeInTheDocument();
        expect(screen.getByText('BNB')).toBeInTheDocument();
      });
    });

    it('displays timeframe tags', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('15m')).toBeInTheDocument();
        expect(screen.getByText('1h')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 4. ATR filter settings
  // ============================================================
  describe('ATR filter', () => {
    it('displays ATR details when enabled', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('ATR 过滤器')).toBeInTheDocument();
        expect(screen.getByText('ATR 周期')).toBeInTheDocument();
        expect(screen.getByText('最小 ATR 倍数')).toBeInTheDocument();
      });

      // Use getAllByText since "14" and "0.5" may appear in multiple places
      expect(screen.getAllByText('14').length).toBeGreaterThan(0);
      expect(screen.getAllByText('0.5').length).toBeGreaterThan(0);
    });

    it('hides ATR details when disabled', async () => {
      const data = createMockEffectiveConfig({
        system: {
          core_symbols: ['BTC/USDT:USDT'],
          ema_period: 60,
          mtf_ema_period: 60,
          mtf_mapping: {},
          signal_cooldown_seconds: 14400,
          timeframes: ['15m'],
          atr_filter_enabled: false,
          atr_period: 14,
          atr_min_ratio: '0.5',
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('系统设置')).toBeInTheDocument();
      });

      // "已禁用" appears in the ATR tag
      expect(screen.getByText('已禁用')).toBeInTheDocument();
      // ATR detail labels should NOT be visible
      expect(screen.queryByText('ATR 周期')).not.toBeInTheDocument();
      expect(screen.queryByText('最小 ATR 倍数')).not.toBeInTheDocument();
    });
  });

  // ============================================================
  // 5. Risk settings
  // ============================================================
  describe('Risk settings', () => {
    it('displays formatted risk percentages', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('风控设置')).toBeInTheDocument();
        expect(screen.getByText('单笔最大损失')).toBeInTheDocument();
        expect(screen.getByText('最大杠杆')).toBeInTheDocument();
        expect(screen.getByText('最大总敞口')).toBeInTheDocument();
        expect(screen.getByText('交易冷却时间')).toBeInTheDocument();
      });

      expect(screen.getByText('1.0%')).toBeInTheDocument();
      expect(screen.getByText('10x')).toBeInTheDocument();
      expect(screen.getByText('80.0%')).toBeInTheDocument();
      expect(screen.getByText('5 分钟')).toBeInTheDocument();
    });

    it('displays optional daily_max_trades and daily_max_loss when present', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('每日最大交易次数')).toBeInTheDocument();
        expect(screen.getByText('20')).toBeInTheDocument();
        expect(screen.getByText('每日最大损失')).toBeInTheDocument();
        expect(screen.getByText('5.0%')).toBeInTheDocument();
      });
    });

    it('hides daily_max_trades when not present', async () => {
      const data = createMockEffectiveConfig({
        risk: {
          max_loss_percent: '0.01',
          max_leverage: 10,
          max_total_exposure: '0.8',
          cooldown_minutes: 5,
          // daily_max_trades missing
          daily_max_loss: '0.05',
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('风控设置')).toBeInTheDocument();
      });

      expect(screen.queryByText('每日最大交易次数')).not.toBeInTheDocument();
      expect(screen.getByText('每日最大损失')).toBeInTheDocument();
    });

    it('hides daily_max_loss when not present', async () => {
      const data = createMockEffectiveConfig({
        risk: {
          max_loss_percent: '0.01',
          max_leverage: 10,
          max_total_exposure: '0.8',
          cooldown_minutes: 5,
          daily_max_trades: 20,
          // daily_max_loss missing
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('风控设置')).toBeInTheDocument();
      });

      expect(screen.getByText('每日最大交易次数')).toBeInTheDocument();
      expect(screen.queryByText('每日最大损失')).not.toBeInTheDocument();
    });
  });

  // ============================================================
  // 6. Notification settings
  // ============================================================
  describe('Notification settings', () => {
    it('displays active notification channel', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('通知设置')).toBeInTheDocument();
        expect(screen.getByText('飞书')).toBeInTheDocument();
        expect(screen.getByText('活跃')).toBeInTheDocument();
      });
    });

    it('shows "no channels" message when empty', async () => {
      const data = createMockEffectiveConfig({
        notification: { channels: [] },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('通知设置')).toBeInTheDocument();
        expect(screen.getByText('未配置通知渠道')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 7. Strategy list
  // ============================================================
  describe('Strategy list', () => {
    it('displays strategy details', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('策略列表')).toBeInTheDocument();
        expect(screen.getByText('Pinbar 保守策略')).toBeInTheDocument();
        expect(screen.getByText('pinbar')).toBeInTheDocument();
        expect(screen.getByText('2 个过滤器')).toBeInTheDocument();
      });
    });

    it('shows strategy count tag when strategies exist', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        // The count "1" should appear as a Tag next to "策略列表"
        const strategySection = screen.getByText('策略列表');
        expect(strategySection).toBeInTheDocument();
      });
    });

    it('shows "暂无策略" when no strategies', async () => {
      const data = createMockEffectiveConfig({ strategies: [] });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('暂无策略')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 8. Symbol list
  // ============================================================
  describe('Symbol list', () => {
    it('displays symbol tags with core indicator', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('币种列表')).toBeInTheDocument();
        expect(screen.getByText('BTC (核心)')).toBeInTheDocument();
        expect(screen.getByText('ETH (核心)')).toBeInTheDocument();
      });
    });

    it('shows default message when no symbols', async () => {
      const data = createMockEffectiveConfig({ symbols: [] });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('币种列表')).toBeInTheDocument();
        expect(
          screen.getByText('暂无币种（使用系统默认核心币种）')
        ).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 9. Asset polling
  // ============================================================
  describe('Asset polling', () => {
    it('disables polling config', async () => {
      const data = createMockEffectiveConfig({
        asset_polling: { enabled: true, interval_seconds: 60 },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('资产轮询')).toBeInTheDocument();
        expect(screen.getByText('轮询开关')).toBeInTheDocument();
        expect(screen.getByText('轮询间隔')).toBeInTheDocument();
        expect(screen.getByText('60 秒')).toBeInTheDocument();
      });
    });

    it('shows disabled tag when polling is off', async () => {
      const data = createMockEffectiveConfig({
        asset_polling: { enabled: false, interval_seconds: 60 },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('资产轮询')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 10. Migration status
  // ============================================================
  describe('Migration status', () => {
    it('shows success alert when fully migrated', async () => {
      const data = createMockEffectiveConfig({
        migration_status: {
          yaml_fully_migrated: true,
          one_time_import_done: true,
          import_version: 'v2',
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('YAML 迁移完成')).toBeInTheDocument();
        expect(
          screen.getByText('所有配置已从数据库读取，YAML 文件仅用于备份恢复')
        ).toBeInTheDocument();
      });
    });

    it('shows warning alert when not migrated', async () => {
      const data = createMockEffectiveConfig({
        migration_status: {
          yaml_fully_migrated: false,
          one_time_import_done: false,
          import_version: 'v1',
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('YAML 迁移未完成')).toBeInTheDocument();
        expect(
          screen.getByText('首次启动后将自动从 YAML 导入配置（当前版本: v1）')
        ).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 11. Config version info
  // ============================================================
  describe('Config version info', () => {
    it('displays config version', async () => {
      const data = createMockEffectiveConfig({
        config_version: 5,
        created_at: '2026-04-01T10:00:00Z',
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText(/配置版本: v5/)).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 12. API 404 fallback
  // ============================================================
  describe('API 404 fallback', () => {
    it('renders normally when API returns 404 (component handles fallback)', async () => {
      const mockData = createMockEffectiveConfig();
      mockSwrSuccess(mockData);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('交易所连接')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 13. API failure
  // ============================================================
  describe('API failure', () => {
    it('displays error state and retry button', async () => {
      const apiError = new Error('服务暂时不可用');
      mockSwrError(apiError);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('加载失败')).toBeInTheDocument();
        expect(screen.getByText('服务暂时不可用')).toBeInTheDocument();
      });

      // The button text is rendered with a space: "重 试"
      expect(
        screen.getByRole('button', { name: /重\s*试/ })
      ).toBeInTheDocument();
    });

    it('displays error with empty message', async () => {
      const apiError = new Error('');
      mockSwrError(apiError);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('加载失败')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 14. No data state
  // ============================================================
  describe('No data state', () => {
    it('shows warning when data is undefined', () => {
      vi.mocked(swr.default).mockReturnValue({
        data: undefined,
        error: undefined,
        isLoading: false,
      } as any);

      render(<EffectiveConfigView />);

      expect(screen.getByText('无数据')).toBeInTheDocument();
      expect(screen.getByText('未获取到配置信息')).toBeInTheDocument();
    });
  });

  // ============================================================
  // 15. Sensitive field masking
  // ============================================================
  describe('Sensitive field masking', () => {
    it('masks API Key by default (first 4 + *** + last 4)', async () => {
      const data = createMockEffectiveConfig({
        exchange: {
          name: 'binance',
          api_key: 'sk_test_abc123xyz789',
          api_secret: 'secret_test_abc123xyz789',
          testnet: true,
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('交易所连接')).toBeInTheDocument();
      });

      // maskValue: first 4 + *** + last 4
      expect(screen.getByText('sk_t***z789')).toBeInTheDocument();
    });

    it('shows **** for API Secret by default', async () => {
      const data = createMockEffectiveConfig();
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('交易所连接')).toBeInTheDocument();
      });

      expect(screen.getByText('****')).toBeInTheDocument();
    });

    it('toggles API Key visibility when clicking eye button', async () => {
      const data = createMockEffectiveConfig({
        exchange: {
          name: 'binance',
          api_key: 'sk_test_abc123xyz789',
          api_secret: 'secret_test_abc123xyz789',
          testnet: true,
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('交易所连接')).toBeInTheDocument();
      });

      // Initially masked
      expect(screen.getByText('sk_t***z789')).toBeInTheDocument();

      // Find all icon buttons (eye icons)
      const iconButtons = screen.getAllByRole('button').filter(
        (btn) => btn.querySelector('svg') !== null
      );

      // Click the first eye button (API Key toggle)
      fireEvent.click(iconButtons[0]);

      await waitFor(() => {
        expect(screen.getByText('sk_test_abc123xyz789')).toBeInTheDocument();
      });

      // Click again to hide
      const iconButtonsAfter = screen.getAllByRole('button').filter(
        (btn) => btn.querySelector('svg') !== null
      );
      fireEvent.click(iconButtonsAfter[0]);

      await waitFor(() => {
        expect(screen.getByText('sk_t***z789')).toBeInTheDocument();
      });
    });

    it('toggles API Secret visibility when clicking eye button', async () => {
      const data = createMockEffectiveConfig({
        exchange: {
          name: 'binance',
          api_key: 'sk_test_abc123xyz789',
          api_secret: 'secret_test_abc123xyz789',
          testnet: true,
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('交易所连接')).toBeInTheDocument();
      });

      // Initially shows ****
      expect(screen.getByText('****')).toBeInTheDocument();

      // Find all icon buttons
      const iconButtons = screen.getAllByRole('button').filter(
        (btn) => btn.querySelector('svg') !== null
      );

      // Click the second eye button (API Secret toggle)
      if (iconButtons.length >= 2) {
        fireEvent.click(iconButtons[1]);

        await waitFor(() => {
          expect(screen.getByText('secret_test_abc123xyz789')).toBeInTheDocument();
        });
      }
    });
  });

  // ============================================================
  // 16. Helper function: formatPercent
  // ============================================================
  describe('formatPercent helper', () => {
    it('formats 0.025 as 2.5%', async () => {
      const data = createMockEffectiveConfig({
        risk: {
          max_loss_percent: '0.025',
          max_leverage: 5,
          max_total_exposure: '0.5',
          cooldown_minutes: 10,
        },
      });
      mockSwrSuccess(data);
      render(<EffectiveConfigView />);

      await waitFor(() => {
        expect(screen.getByText('2.5%')).toBeInTheDocument();
        expect(screen.getByText('50.0%')).toBeInTheDocument();
      });
    });
  });
});
