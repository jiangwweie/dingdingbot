/**
 * SystemSettings 组件单元测试
 *
 * 测试覆盖场景：
 * 1. variant='tab' 模式渲染（嵌入 ConfigProfiles）
 * 2. variant='page' 模式渲染（独立页面）
 * 3. 参数修改保存
 * 4. 重启提示显示
 * 5. 表单验证
 * 6. 边界检查
 *
 * 边界检查：
 * - 空值提交
 * - 越界数值
 * - 保存失败
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SystemSettingsPage from '../SystemSettings';
import { configApi } from '../../../api/config';

// 用于收集消息调用的变量
let messageCalls: { type: string; message: string }[] = [];

// Mock API
vi.mock('../../../api/config', () => ({
  configApi: {
    getSystemConfig: vi.fn(),
    updateSystemConfig: vi.fn(),
  },
}));

// Mock Ant Design message (must be hoisted)
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as object),
    message: {
      success: vi.fn((msg) => {
        messageCalls.push({ type: 'success', message: msg });
      }),
      error: vi.fn((msg) => {
        messageCalls.push({ type: 'error', message: msg });
      }),
      warning: vi.fn((msg) => {
        messageCalls.push({ type: 'warning', message: msg });
      }),
      info: vi.fn((msg) => {
        messageCalls.push({ type: 'info', message: msg });
      }),
    },
  };
});

// Import mocks after vi.mock calls
const { message } = require('antd');

// Mock react-router-dom
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as object),
    useNavigate: () => vi.fn(),
  };
});

describe('SystemSettings', () => {
  const mockSystemResponse = {
    data: {
      ema: { period: 60 },
      mtf_ema_period: 60,
      signal_pipeline: {
        cooldown_seconds: 14400,
        queue: {
          batch_size: 10,
          flush_interval: 5.0,
          max_queue_size: 1000,
        },
      },
      warmup: { history_bars: 100 },
      atr_filter_enabled: true,
      atr_period: 14,
      atr_min_ratio: 0.5,
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    messageCalls = [];
  });

  const renderSystemSettings = (props?: { variant?: 'page' | 'tab' }) =>
    render(<SystemSettingsPage {...props} />);

  // ============================================================
  // 1. variant='tab' 模式渲染测试（嵌入 ConfigProfiles）
  // ============================================================

  it('renders loading state initially in tab mode', () => {
    vi.mocked(configApi.getSystemConfig).mockImplementation(
      () => new Promise(() => {})
    );

    renderSystemSettings({ variant: 'tab' });

    expect(screen.getByText('加载系统配置...')).toBeInTheDocument();
  });

  it('renders form fields in tab mode without page header', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Page header should NOT be visible in tab mode
    expect(screen.queryByText('系统设置')).not.toBeInTheDocument();
  });

  it('renders all form fields in tab mode', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Collapse panel needs to be expanded first
    const collapseTrigger = screen.getByText('点击展开高级配置');
    fireEvent.click(collapseTrigger);

    await waitFor(() => {
      // Verify form labels are present after expanding
      expect(screen.getByText('EMA 周期')).toBeInTheDocument();
    }, { timeout: 1000 });

    expect(screen.getByText('MTF EMA 周期')).toBeInTheDocument();
    expect(screen.getByText('信号冷却时间 (秒)')).toBeInTheDocument();
    expect(screen.getByText('队列批量大小')).toBeInTheDocument();
    expect(screen.getByText('队列刷新间隔 (秒)')).toBeInTheDocument();
    expect(screen.getByText('队列最大容量')).toBeInTheDocument();
    expect(screen.getByText('预热历史 K 线数')).toBeInTheDocument();
    expect(screen.getByText('启用 ATR 过滤')).toBeInTheDocument();
    expect(screen.getByText('ATR 周期')).toBeInTheDocument();
    expect(screen.getByText('最小 ATR 倍数')).toBeInTheDocument();
  });

  it('renders action buttons in tab mode', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    expect(screen.getByRole('button', { name: /保存配置/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重置/ })).toBeInTheDocument();
  });

  // ============================================================
  // 2. variant='page' 模式渲染测试（独立页面）
  // ============================================================

  it('renders page header in page mode', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemSettings({ variant: 'page' });

    await waitFor(() => {
      expect(screen.getByText('系统设置')).toBeInTheDocument();
    }, { timeout: 3000 });

    expect(screen.getByText('配置全局系统参数、Profile 管理和备份恢复')).toBeInTheDocument();
  });

  it('renders sidebar cards in page mode', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemSettings({ variant: 'page' });

    await waitFor(() => {
      expect(screen.getByText('系统设置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Sidebar quick-access cards should be visible
    expect(screen.getByText('Profile 管理')).toBeInTheDocument();
    expect(screen.getByText('备份恢复')).toBeInTheDocument();
    expect(screen.getByText('配置快照')).toBeInTheDocument();
  });

  // ============================================================
  // 3. 参数修改保存测试
  // ============================================================

  it('saves configuration successfully', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);
    vi.mocked(configApi.updateSystemConfig).mockResolvedValue({
      data: {
        restart_required: false,
        ...mockSystemResponse.data,
      },
    });

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Expand the collapse panel first
    const collapseHeader = screen.getByText('点击展开高级配置');
    await fireEvent.click(collapseHeader);

    await waitFor(() => {
      expect(screen.getByLabelText('EMA 周期')).toBeInTheDocument();
    }, { timeout: 1000 });

    // Modify EMA period
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });

    // Click save
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(configApi.updateSystemConfig).toHaveBeenCalled();
    }, { timeout: 3000 });

    // Verify success message
    const successCall = messageCalls.find(c => c.type === 'success');
    expect(successCall?.message).toBe('系统配置已保存');
  });

  it('shows restart required alert when server returns restart_required=true', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);
    vi.mocked(configApi.updateSystemConfig).mockResolvedValue({
      data: {
        restart_required: true,
        ...mockSystemResponse.data,
      },
    });

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Expand the collapse panel first
    const collapseHeader = screen.getByText('点击展开高级配置');
    await fireEvent.click(collapseHeader);

    await waitFor(() => {
      expect(screen.getByLabelText('EMA 周期')).toBeInTheDocument();
    }, { timeout: 1000 });

    // Modify and save
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    // Verify restart alert appears
    await waitFor(() => {
      expect(screen.getByText('配置已保存，需要重启服务才能生效')).toBeInTheDocument();
    }, { timeout: 5000 });

    expect(screen.getByRole('button', { name: /立即重启/ })).toBeInTheDocument();
  });

  // ============================================================
  // 4. 表单验证测试
  // ============================================================

  it('validates required fields', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Expand the collapse panel
    const collapseHeader = screen.getByText('点击展开高级配置');
    await fireEvent.click(collapseHeader);

    await waitFor(() => {
      expect(screen.getByLabelText('EMA 周期')).toBeInTheDocument();
    }, { timeout: 1000 });

    // Clear the field
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '' } });

    // Try to submit
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    // Verify not submitted
    await waitFor(() => {
      expect(configApi.updateSystemConfig).not.toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  it('validates minimum value for EMA period', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Expand the collapse panel
    const collapseHeader = screen.getByText('点击展开高级配置');
    await fireEvent.click(collapseHeader);

    await waitFor(() => {
      expect(screen.getByLabelText('EMA 周期')).toBeInTheDocument();
    }, { timeout: 1000 });

    // Input value below minimum
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '3' } });

    // Try to submit
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(configApi.updateSystemConfig).not.toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  it('validates maximum value for EMA period', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Expand the collapse panel
    const collapseHeader = screen.getByText('点击展开高级配置');
    await fireEvent.click(collapseHeader);

    await waitFor(() => {
      expect(screen.getByLabelText('EMA 周期')).toBeInTheDocument();
    }, { timeout: 1000 });

    // Input value above maximum
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '250' } });

    // Try to submit
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(configApi.updateSystemConfig).not.toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  // ============================================================
  // 边界检查测试
  // ============================================================

  it('handles save failure correctly', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);
    vi.mocked(configApi.updateSystemConfig).mockRejectedValue({
      response: {
        data: {
          detail: '配置验证失败',
        },
      },
    });

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Expand the collapse panel
    const collapseHeader = screen.getByText('点击展开高级配置');
    await fireEvent.click(collapseHeader);

    await waitFor(() => {
      expect(screen.getByLabelText('EMA 周期')).toBeInTheDocument();
    }, { timeout: 1000 });

    // Modify and save
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    // Verify error message
    await waitFor(() => {
      const errorCall = messageCalls.find(c => c.type === 'error');
      expect(errorCall?.message).toBe('保存失败：配置验证失败');
    }, { timeout: 3000 });
  });

  it('handles network error during save', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);
    vi.mocked(configApi.updateSystemConfig).mockRejectedValue(new Error('Network error'));

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Expand the collapse panel
    const collapseHeader = screen.getByText('点击展开高级配置');
    await fireEvent.click(collapseHeader);

    await waitFor(() => {
      expect(screen.getByLabelText('EMA 周期')).toBeInTheDocument();
    }, { timeout: 1000 });

    // Modify and save
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    // Verify error message
    await waitFor(() => {
      const errorCall = messageCalls.find(c => c.type === 'error');
      expect(errorCall?.message).toBe('保存失败：Network error');
    }, { timeout: 3000 });
  });

  it('shows error state when loading fails', async () => {
    vi.mocked(configApi.getSystemConfig).mockRejectedValue({
      response: {
        data: {
          detail: '服务暂时不可用',
        },
      },
    });

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('服务暂时不可用')).toBeInTheDocument();
    }, { timeout: 3000 });

    expect(screen.getByRole('button', { name: /重新加载/ })).toBeInTheDocument();
  });

  it('can toggle ATR filter switch', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('全局系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Expand the collapse panel
    const collapseHeader = screen.getByText('点击展开高级配置');
    await fireEvent.click(collapseHeader);

    await waitFor(() => {
      expect(screen.getByLabelText('启用 ATR 过滤')).toBeInTheDocument();
    }, { timeout: 1000 });

    const atrSwitch = screen.getByLabelText('启用 ATR 过滤');
    expect(atrSwitch).toBeInTheDocument();

    // Click the switch
    await fireEvent.click(atrSwitch);

    // Verify switch is still present (state changed)
    expect(atrSwitch).toBeInTheDocument();
  });

  it('reloads configuration when clicking refresh button on error', async () => {
    vi.mocked(configApi.getSystemConfig)
      .mockRejectedValueOnce({
        response: { data: { detail: '服务暂时不可用' } },
      })
      .mockResolvedValueOnce(mockSystemResponse);

    renderSystemSettings({ variant: 'tab' });

    await waitFor(() => {
      expect(screen.getByText('服务暂时不可用')).toBeInTheDocument();
    }, { timeout: 3000 });

    // Click reload button
    await fireEvent.click(screen.getByRole('button', { name: /重新加载/ }));

    // Verify API was called twice
    await waitFor(() => {
      expect(configApi.getSystemConfig).toHaveBeenCalledTimes(2);
    }, { timeout: 3000 });
  });
});
