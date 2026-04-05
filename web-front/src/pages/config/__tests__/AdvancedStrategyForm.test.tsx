/**
 * AdvancedStrategyForm 组件测试
 *
 * 覆盖场景:
 * 1. 表单渲染（创建/编辑模式）
 * 2. 触发器配置
 * 3. 过滤器链配置
 * 4. 表单验证（必填项、数值范围）
 * 5. 动态字段渲染
 * 6. 提交成功/失败处理
 */

import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { message } from 'antd';
import { AdvancedStrategyForm } from '../AdvancedStrategyForm';
import type { Strategy, CreateStrategyRequest } from '../../api/config';

// ============================================================
// Mock Setup
// ============================================================

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
      loading: vi.fn(),
      destroy: vi.fn(),
    },
  };
});

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
global.ResizeObserver = ResizeObserver;

class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
}
global.IntersectionObserver = MockIntersectionObserver;

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
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
// Test Data
// ============================================================

const mockStrategy: Strategy = {
  id: 'strat-001',
  name: 'Pinbar 保守策略',
  description: '基于 Pinbar 形态的保守交易策略',
  is_active: true,
  trigger_config: {
    type: 'pinbar',
    params: { min_wick_ratio: 0.6, max_body_ratio: 0.3, body_position_tolerance: 0.3 },
  },
  filter_configs: [
    { type: 'ema', enabled: true, params: { period: 60 } },
    { type: 'mtf', enabled: false, params: { mapping: '15m->1h' } },
  ],
  filter_logic: 'AND',
  symbols: ['BTC/USDT:USDT', 'ETH/USDT:USDT'],
  timeframes: ['15m', '1h'],
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-05T00:00:00Z',
};

const mockOnCancel = vi.fn();
const mockOnSubmit = vi.fn();

// ============================================================
// Helper Functions
// ============================================================

const getModalContainer = () => document.querySelector('.ant-modal');

const getSubmitButton = () => {
  const footer = document.querySelector('.ant-modal-footer');
  if (footer) {
    const buttons = footer.querySelectorAll('button.ant-btn');
    return Array.from(buttons).find(btn =>
      btn.className?.includes('ant-btn-primary') ||
      btn.textContent?.includes('确定')
    ) as HTMLButtonElement;
  }
  return null;
};

const getCancelButton = () => {
  const footer = document.querySelector('.ant-modal-footer');
  if (footer) {
    const buttons = footer.querySelectorAll('button.ant-btn');
    return Array.from(buttons).find(btn =>
      btn.textContent?.includes('取消')
    ) as HTMLButtonElement;
  }
  return null;
};

// ============================================================
// Test Suite
// ============================================================

describe('AdvancedStrategyForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    message.destroy();
  });

  afterEach(() => {
    cleanup();
    message.destroy();
  });

  const renderForm = (props = {}) => {
    return render(
      <AdvancedStrategyForm
        visible={true}
        onCancel={mockOnCancel}
        onSubmit={mockOnSubmit}
        {...props}
      />
    );
  };

  // ============================================================
  // 1. 表单渲染测试
  // ============================================================

  describe('表单渲染', () => {
    it('创建模式：显示创建标题', () => {
      renderForm({ initialData: null });
      expect(screen.getByText('创建策略')).toBeInTheDocument();
    });

    it('创建模式：显示策略名称输入框', () => {
      renderForm({ initialData: null });
      expect(screen.getByPlaceholderText('例如：Pinbar EMA60 策略')).toBeInTheDocument();
    });

    it('创建模式：显示描述输入框', () => {
      renderForm({ initialData: null });
      expect(screen.getByPlaceholderText('简要描述策略特点和适用场景')).toBeInTheDocument();
    });

    it('编辑模式：显示编辑标题', () => {
      renderForm({ initialData: mockStrategy });
      expect(screen.getByText('编辑策略')).toBeInTheDocument();
    });

    it('编辑模式：显示现有策略名称', () => {
      renderForm({ initialData: mockStrategy });
      expect(screen.getByDisplayValue('Pinbar 保守策略')).toBeInTheDocument();
    });

    it('编辑模式：显示现有策略描述', () => {
      renderForm({ initialData: mockStrategy });
      expect(screen.getByDisplayValue('基于 Pinbar 形态的保守交易策略')).toBeInTheDocument();
    });

    it('显示触发器配置面板', () => {
      renderForm({ initialData: null });
      const titles = screen.getAllByText('触发器配置');
      expect(titles.length).toBeGreaterThan(0);
    });

    it('显示过滤器链面板', () => {
      renderForm({ initialData: null });
      const titles = screen.getAllByText('过滤器链');
      expect(titles.length).toBeGreaterThan(0);
    });
  });

  // ============================================================
  // 2. 触发器配置测试
  // ============================================================

  describe('触发器配置', () => {
    it('显示触发器类型选择器', () => {
      renderForm({ initialData: null });
      const selects = screen.getAllByPlaceholderText('选择触发器类型');
      expect(selects.length).toBeGreaterThan(0);
    });

    it('默认触发器类型为 Pinbar', () => {
      renderForm({ initialData: null });
      const options = screen.getAllByText('Pinbar (锤子线)');
      expect(options.length).toBeGreaterThan(0);
    });

    it('显示 Pinbar 参数标签', () => {
      renderForm({ initialData: null });
      const labels = screen.getAllByText('最小影线比例');
      expect(labels.length).toBeGreaterThan(0);
    });

    it('修改 Pinbar 参数值', async () => {
      renderForm({ initialData: null });
      const inputs = document.querySelectorAll('input[type="number"]');
      const minWickInput = Array.from(inputs).find(input =>
        input.parentElement?.parentElement?.textContent?.includes('最小影线比例')
      ) as HTMLInputElement;

      if (minWickInput) {
        fireEvent.change(minWickInput, { target: { value: '0.8' } });
        expect(minWickInput).toHaveValue(0.8);
      }
    });

    it('切换触发器类型下拉选项', async () => {
      renderForm({ initialData: null });
      const selects = screen.getAllByPlaceholderText('选择触发器类型');
      fireEvent.mouseDown(selects[0]);

      await waitFor(() => {
        expect(screen.getByText('Engulfing (吞没)')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 3. 过滤器链配置测试
  // ============================================================

  describe('过滤器链配置', () => {
    it('空状态显示提示信息', () => {
      renderForm({ initialData: null });
      expect(screen.getByText('暂无过滤器配置')).toBeInTheDocument();
    });

    it('显示添加过滤器按钮', () => {
      renderForm({ initialData: null });
      expect(screen.getByText('添加第一个过滤器')).toBeInTheDocument();
    });

    it('添加过滤器', async () => {
      renderForm({ initialData: null });
      fireEvent.click(screen.getByText('添加第一个过滤器'));

      await waitFor(() => {
        expect(screen.getByText('过滤器 1')).toBeInTheDocument();
      });
    });

    it('添加多个过滤器', async () => {
      renderForm({ initialData: null });

      fireEvent.click(screen.getByText('添加第一个过滤器'));
      await waitFor(() => screen.getByText('过滤器 1'));

      fireEvent.click(screen.getByText('添加过滤器'));
      await waitFor(() => screen.getByText('过滤器 2'));

      expect(screen.getByText('过滤器 1')).toBeInTheDocument();
      expect(screen.getByText('过滤器 2')).toBeInTheDocument();
    });

    it('删除过滤器', async () => {
      renderForm({ initialData: null });

      fireEvent.click(screen.getByText('添加第一个过滤器'));
      await waitFor(() => screen.getByText('过滤器 1'));

      // 查找该过滤器卡片内的删除按钮
      const filterCard = screen.getByText('过滤器 1').closest('.ant-card');
      const deleteBtn = filterCard?.querySelector('.ant-btn-dangerous') as HTMLButtonElement;

      if (deleteBtn) {
        fireEvent.click(deleteBtn);
      }

      await waitFor(() => {
        expect(screen.queryByText('过滤器 1')).not.toBeInTheDocument();
      }, { timeout: 5000 });
    });

    it('显示过滤器启用开关', async () => {
      renderForm({ initialData: null });

      fireEvent.click(screen.getByText('添加第一个过滤器'));
      await waitFor(() => screen.getByText('过滤器 1'));

      const switches = screen.getAllByRole('switch');
      expect(switches.length).toBeGreaterThan(0);
    });

    it('切换过滤器启用状态', async () => {
      renderForm({ initialData: null });

      fireEvent.click(screen.getByText('添加第一个过滤器'));
      await waitFor(() => screen.getByText('过滤器 1'));

      const switches = screen.getAllByRole('switch');
      const firstSwitch = switches[0];
      expect(firstSwitch).toHaveAttribute('aria-checked', 'true');

      fireEvent.click(firstSwitch);
      expect(firstSwitch).toHaveAttribute('aria-checked', 'false');
    });

    it('切换过滤器类型为 ATR', async () => {
      renderForm({ initialData: null });

      fireEvent.click(screen.getByText('添加第一个过滤器'));
      await waitFor(() => screen.getByText('过滤器 1'));

      // 查找类型选择器并打开
      const typeSelect = screen.getByText('EMA 趋势');
      fireEvent.mouseDown(typeSelect);

      await waitFor(() => {
        expect(screen.getByText('ATR 波动率')).toBeInTheDocument();
      });

      // 选择 ATR
      fireEvent.click(screen.getByText('ATR 波动率'));

      await waitFor(() => {
        expect(screen.getByText('ATR 周期')).toBeInTheDocument();
      });
    });

    it('切换过滤器类型为 MTF', async () => {
      renderForm({ initialData: null });

      fireEvent.click(screen.getByText('添加第一个过滤器'));
      await waitFor(() => screen.getByText('过滤器 1'));

      const typeSelect = screen.getByText('EMA 趋势');
      fireEvent.mouseDown(typeSelect);

      await waitFor(() => {
        expect(screen.getByText('MTF 多周期')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('MTF 多周期'));

      await waitFor(() => {
        expect(screen.getByText('MTF 映射')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 4. 表单验证测试
  // ============================================================

  describe('表单验证', () => {
    it('空表单提交显示错误消息', async () => {
      renderForm({ initialData: null });

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(message.error).toHaveBeenCalledWith('请完善表单信息');
      });
    });

    it('策略名称必填验证', async () => {
      renderForm({ initialData: null });

      const nameInput = screen.getByPlaceholderText('例如：Pinbar EMA60 策略');
      fireEvent.change(nameInput, { target: { value: '' } });

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(message.error).toHaveBeenCalled();
      });
    });

    it('策略名称长度验证', async () => {
      renderForm({ initialData: null });

      const nameInput = screen.getByPlaceholderText('例如：Pinbar EMA60 策略');
      fireEvent.change(nameInput, { target: { value: 'a'.repeat(51) } });

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText('策略名称不能超过 50 个字符')).toBeInTheDocument();
      });
    });

    it('策略描述长度验证', async () => {
      renderForm({ initialData: null });

      const nameInput = screen.getByPlaceholderText('例如：Pinbar EMA60 策略');
      fireEvent.change(nameInput, { target: { value: 'Test' } });

      const descInput = screen.getByPlaceholderText('简要描述策略特点和适用场景');
      fireEvent.change(descInput, { target: { value: 'a'.repeat(201) } });

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.getByText('描述不能超过 200 个字符')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 5. 动态字段渲染测试
  // ============================================================

  describe('动态字段渲染', () => {
    it('默认显示 Pinbar 参数', () => {
      renderForm({ initialData: null });
      expect(screen.getByText('最小影线比例')).toBeInTheDocument();
    });

    it('显示过滤器组合逻辑选项', () => {
      renderForm({ initialData: null });
      expect(screen.getByText('全部满足 (AND)')).toBeInTheDocument();
    });

    it('切换过滤器组合逻辑为 OR', async () => {
      renderForm({ initialData: null });

      const logicSelect = screen.getByText('全部满足 (AND)');
      fireEvent.mouseDown(logicSelect);

      await waitFor(() => {
        expect(screen.getByText('任一满足 (OR)')).toBeInTheDocument();
      });
    });
  });

  // ============================================================
  // 6. 提交处理测试
  // ============================================================

  describe('提交处理', () => {
    const fillValidForm = () => {
      const nameInput = screen.getByPlaceholderText('例如：Pinbar EMA60 策略');
      fireEvent.change(nameInput, { target: { value: 'Test Strategy' } });
    };

    it('提交成功调用 onSubmit', async () => {
      renderForm({ initialData: null });
      fillValidForm();

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledTimes(1);
      });
    });

    it('提交数据包含策略名称', async () => {
      renderForm({ initialData: null });
      fillValidForm();

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => expect(mockOnSubmit).toHaveBeenCalled());

      const data = mockOnSubmit.mock.calls[0][0] as CreateStrategyRequest;
      expect(data.name).toBe('Test Strategy');
    });

    it('提交数据包含默认币种', async () => {
      renderForm({ initialData: null });
      fillValidForm();

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => expect(mockOnSubmit).toHaveBeenCalled());

      const data = mockOnSubmit.mock.calls[0][0] as CreateStrategyRequest;
      expect(data.symbols).toContain('BTC/USDT:USDT');
    });

    it('提交数据包含默认周期', async () => {
      renderForm({ initialData: null });
      fillValidForm();

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => expect(mockOnSubmit).toHaveBeenCalled());

      const data = mockOnSubmit.mock.calls[0][0] as CreateStrategyRequest;
      expect(data.timeframes).toContain('1h');
    });

    it('提交数据包含触发器类型', async () => {
      renderForm({ initialData: null });
      fillValidForm();

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => expect(mockOnSubmit).toHaveBeenCalled());

      const data = mockOnSubmit.mock.calls[0][0] as CreateStrategyRequest;
      expect(data.trigger_config.type).toBe('pinbar');
    });

    it('提交数据包含过滤器配置', async () => {
      renderForm({ initialData: null });
      fillValidForm();

      // 添加一个过滤器
      fireEvent.click(screen.getByText('添加第一个过滤器'));
      await waitFor(() => screen.getByText('过滤器 1'));

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => expect(mockOnSubmit).toHaveBeenCalled());

      const data = mockOnSubmit.mock.calls[0][0] as CreateStrategyRequest;
      expect(data.filter_configs).toHaveLength(1);
    });

    it('取消按钮调用 onCancel', () => {
      renderForm({ initialData: null });

      const cancelBtn = getCancelButton();
      if (cancelBtn) {
        fireEvent.click(cancelBtn);
        expect(mockOnCancel).toHaveBeenCalledTimes(1);
      }
    });

    it('loading 状态禁用提交按钮', () => {
      renderForm({ initialData: null, loading: true });

      const submitBtn = getSubmitButton();
      expect(submitBtn?.disabled).toBe(true);
    });
  });

  // ============================================================
  // 7. 边界情况测试
  // ============================================================

  describe('边界情况', () => {
    it('处理特殊字符', () => {
      renderForm({ initialData: null });

      const nameInput = screen.getByPlaceholderText('例如：Pinbar EMA60 策略');
      fireEvent.change(nameInput, { target: { value: 'Test<script>alert(1)</script>' } });

      expect(nameInput).toHaveValue('Test<script>alert(1)</script>');
    });

    it('空过滤器列表可提交', async () => {
      renderForm({ initialData: null });

      const nameInput = screen.getByPlaceholderText('例如：Pinbar EMA60 策略');
      fireEvent.change(nameInput, { target: { value: 'Test' } });

      const submitBtn = getSubmitButton();
      if (submitBtn) fireEvent.click(submitBtn);

      await waitFor(() => expect(mockOnSubmit).toHaveBeenCalled());

      const data = mockOnSubmit.mock.calls[0][0] as CreateStrategyRequest;
      expect(data.filter_configs).toEqual([]);
    });
  });

  // ============================================================
  // 8. 可见性控制测试
  // ============================================================

  describe('可见性控制', () => {
    it('visible=false 时不渲染模态框', () => {
      const { container } = render(
        <AdvancedStrategyForm
          visible={false}
          onCancel={mockOnCancel}
          onSubmit={mockOnSubmit}
        />
      );
      expect(container.querySelector('.ant-modal')).not.toBeInTheDocument();
    });

    it('visible=true 时渲染模态框', () => {
      const { container } = renderForm({ visible: true });
      expect(container.querySelector('.ant-modal')).toBeInTheDocument();
    });
  });
});
