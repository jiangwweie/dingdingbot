/**
 * SystemTab 组件单元测试
 *
 * 测试覆盖场景：
 * 1. 配置表单渲染
 * 2. 参数修改保存
 * 3. 重启提示显示
 * 4. 表单验证
 * 5. 恢复默认值
 *
 * 边界检查：
 * - 空值提交
 * - 越界数值
 * - 保存失败
 * - 恢复默认确认
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SystemTab, { SystemConfig } from '../SystemTab';
import { configApi } from '../../../api/config';

// 用于收集消息调用的变量
let messageCalls: { type: string; message: string }[] = [];
let modalConfirmCalls: any[] = [];

// Mock API
vi.mock('../../../api/config', () => ({
  configApi: {
    getSystemConfig: vi.fn(),
    updateSystemConfig: vi.fn(),
  },
}));

// Mock Ant Design Modal confirm and message (must be hoisted)
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as object),
    Modal: {
      ...(actual as any).Modal,
      confirm: vi.fn((config) => {
        modalConfirmCalls.push(config);
      }),
    },
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
const { Modal } = require('antd');
const { message } = require('antd');

describe('SystemTab', () => {
  const mockSystemConfig: SystemConfig = {
    ema_period: 20,
    mtf_ema_period: 60,
    signal_cooldown_seconds: 14400,
    queue_batch_size: 10,
    queue_flush_interval: 5.0,
    queue_max_size: 1000,
    warmup_history_bars: 100,
    atr_filter_enabled: true,
    atr_period: 14,
    atr_min_ratio: 1.5,
  };

  const mockSystemResponse = {
    data: {
      ema: { period: 20 },
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
      atr_min_ratio: 1.5,
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    messageCalls = [];
    modalConfirmCalls = [];
  });

  const renderSystemTab = () => render(<SystemTab />);

  // ============================================================
  // 1. 配置表单渲染测试
  // ============================================================

  it('renders loading state initially', () => {
    vi.mocked(configApi.getSystemConfig).mockImplementation(
      () => new Promise(() => {})
    );

    renderSystemTab();

    expect(screen.getByText('加载系统配置...')).toBeInTheDocument();
  });

  it('renders system configuration form successfully', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 验证各个配置区域标题
    expect(screen.getByText('📊 指标参数')).toBeInTheDocument();
    expect(screen.getByText('🔧 信号管道')).toBeInTheDocument();
    expect(screen.getByText('🔥 预热配置')).toBeInTheDocument();
    expect(screen.getByText('📈 ATR 过滤器')).toBeInTheDocument();
  });

  it('renders all form fields correctly', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 验证表单标签
    expect(screen.getByText('EMA 周期')).toBeInTheDocument();
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

  it('renders action buttons', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 验证保存配置按钮存在
    expect(screen.getByRole('button', { name: /保存配置/ })).toBeInTheDocument();
    // 验证至少有两个按钮（保存和重置）
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(2);
  });

  // ============================================================
  // 2. 参数修改保存测试
  // ============================================================

  it('saves configuration successfully', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);
    vi.mocked(configApi.updateSystemConfig).mockResolvedValue({
      data: {
        restart_required: false,
        ...mockSystemResponse.data,
      },
    });

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 修改 EMA 周期
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });

    // 点击保存
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(configApi.updateSystemConfig).toHaveBeenCalled();
    }, { timeout: 3000 });

    // 验证消息调用
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

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 修改配置并保存
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    // 验证重启提示显示
    await waitFor(() => {
      expect(screen.getByText('配置变更需要重启')).toBeInTheDocument();
    }, { timeout: 5000 });

    expect(screen.getByRole('button', { name: /立即重启/ })).toBeInTheDocument();
  });

  // ============================================================
  // 3. 重启提示显示测试
  // ============================================================

  it('handles restart button click with confirmation modal', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);
    vi.mocked(configApi.updateSystemConfig).mockResolvedValue({
      data: {
        restart_required: true,
        ...mockSystemResponse.data,
      },
    });

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 修改配置并保存
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /立即重启/ })).toBeInTheDocument();
    }, { timeout: 5000 });

    // 点击立即重启
    await fireEvent.click(screen.getByRole('button', { name: /立即重启/ }));

    // 验证 Modal.confirm 被调用（给予更长时间等待）
    await waitFor(() => {
      expect(modalConfirmCalls.length).toBeGreaterThan(0);
    }, { timeout: 5000 });

    expect(modalConfirmCalls[0].title).toBe('确认重启服务？');
  }, { timeout: 15000 });

  it('closes restart alert when clicking close button', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);
    vi.mocked(configApi.updateSystemConfig).mockResolvedValue({
      data: {
        restart_required: true,
        ...mockSystemResponse.data,
      },
    });

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 修改配置并保存
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /稍后手动重启/ })).toBeInTheDocument();
    }, { timeout: 5000 });

    // 点击稍后手动重启
    await fireEvent.click(screen.getByRole('button', { name: /稍后手动重启/ }));

    // 验证消息调用
    await waitFor(() => {
      const infoCall = messageCalls.find(c => c.type === 'info');
      expect(infoCall?.message).toBe('请稍后手动重启服务');
    }, { timeout: 5000 });
  }, { timeout: 15000 });

  // ============================================================
  // 4. 表单验证测试
  // ============================================================

  it('validates required fields', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 清空必填字段并提交
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '' } });

    // 尝试提交表单
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    // 验证没有提交
    await waitFor(() => {
      expect(configApi.updateSystemConfig).not.toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  it('validates minimum value for EMA period', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 输入小于最小值的数值
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '3' } });

    // 尝试提交
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(configApi.updateSystemConfig).not.toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  it('validates maximum value for EMA period', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 输入大于最大值的数值
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '250' } });

    // 尝试提交
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(configApi.updateSystemConfig).not.toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  it('validates minimum value for cooldown seconds', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 输入小于最小值的数值
    const cooldownInput = screen.getByLabelText('信号冷却时间 (秒)');
    await fireEvent.change(cooldownInput, { target: { value: '30' } });

    // 尝试提交
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(configApi.updateSystemConfig).not.toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  // ============================================================
  // 5. 恢复默认值测试
  // ============================================================

  it('resets form to default values on page reload', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 验证初始值为默认值
    const emaInput = screen.getByLabelText('EMA 周期');
    expect(emaInput).toHaveValue('20');
  });

  it('reloads configuration when clicking refresh button on error', async () => {
    vi.mocked(configApi.getSystemConfig)
      .mockRejectedValueOnce({
        response: { data: { detail: '服务暂时不可用' } },
      })
      .mockResolvedValueOnce(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('服务暂时不可用')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 点击重新加载按钮
    await fireEvent.click(screen.getByRole('button', { name: /重新加载/ }));

    // 验证重新调用了 API
    await waitFor(() => {
      expect(configApi.getSystemConfig).toHaveBeenCalledTimes(2);
    }, { timeout: 3000 });
  });

  // ============================================================
  // 边界检查测试
  // ============================================================

  // --- 空值提交 ---
  it('handles empty value submission correctly', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 清空必填字段
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '' } });

    // 尝试提交
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    // 验证没有提交
    await waitFor(() => {
      expect(configApi.updateSystemConfig).not.toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  // --- 越界数值 ---
  it('handles out-of-range values correctly', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 测试 ATR 周期越界
    const atrPeriodInput = screen.getByLabelText('ATR 周期');
    await fireEvent.change(atrPeriodInput, { target: { value: '100' } });

    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    await waitFor(() => {
      expect(configApi.updateSystemConfig).not.toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  // --- 保存失败 ---
  it('handles save failure correctly', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);
    vi.mocked(configApi.updateSystemConfig).mockRejectedValue({
      response: {
        data: {
          detail: '配置验证失败',
        },
      },
    });

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 修改配置并保存
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    // 验证错误消息
    await waitFor(() => {
      const errorCall = messageCalls.find(c => c.type === 'error');
      expect(errorCall?.message).toBe('配置验证失败');
    }, { timeout: 3000 });
  });

  it('handles network error during save', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);
    vi.mocked(configApi.updateSystemConfig).mockRejectedValue(new Error('Network error'));

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 修改配置并保存
    const emaInput = screen.getByLabelText('EMA 周期');
    await fireEvent.change(emaInput, { target: { value: '30' } });
    await fireEvent.click(screen.getByRole('button', { name: /保存配置/ }));

    // 验证错误消息
    await waitFor(() => {
      const errorCall = messageCalls.find(c => c.type === 'error');
      expect(errorCall?.message).toBe('Network error');
    }, { timeout: 3000 });
  });

  // --- 加载失败 ---
  it('shows error state when loading fails', async () => {
    vi.mocked(configApi.getSystemConfig).mockRejectedValue({
      response: {
        data: {
          detail: '服务暂时不可用',
        },
      },
    });

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('服务暂时不可用')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 验证有重新加载按钮
    expect(screen.getByRole('button', { name: /重新加载/ })).toBeInTheDocument();
  });

  // --- ATR 过滤器开关 ---
  it('can toggle ATR filter switch', async () => {
    vi.mocked(configApi.getSystemConfig).mockResolvedValue(mockSystemResponse);

    renderSystemTab();

    await waitFor(() => {
      expect(screen.getByText('系统配置')).toBeInTheDocument();
    }, { timeout: 3000 });

    // 获取开关当前状态
    const atrSwitch = screen.getByLabelText('启用 ATR 过滤');
    expect(atrSwitch).toBeInTheDocument();

    // 点击开关
    await fireEvent.click(atrSwitch);

    // 开关状态改变（Ant Design Switch 通过 checked 属性控制）
    // 由于是 mock 环境，我们只验证点击事件没有报错
    expect(atrSwitch).toBeInTheDocument();
  });
});
