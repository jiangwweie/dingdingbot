/**
 * StrategyEditorDrawer 组件单元测试
 *
 * 测试覆盖:
 * - 表单初始化和数据填充
 * - 表单验证
 * - 自动保存机制
 * - 创建/编辑模式
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { StrategyEditorDrawer } from '../StrategyEditor';
import type { Strategy } from '../../../api/config';

// ============================================================
// Mock Data
// ============================================================

const mockStrategy: Strategy = {
  id: 'test-strategy-1',
  name: 'BTC 15m Pinbar 策略',
  description: '测试策略描述',
  is_active: true,
  trigger_config: {
    type: 'pinbar',
    params: {
      min_wick_ratio: 0.6,
      max_body_ratio: 0.3,
      body_position_tolerance: 0.1,
    },
  },
  filter_configs: [],
  filter_logic: 'AND',
  symbols: ['BTC/USDT:USDT'],
  timeframes: ['15m'],
  created_at: '2026-04-01T10:00:00Z',
  updated_at: '2026-04-06T15:30:00Z',
};

const mockHandlers = {
  visible: true,
  onClose: vi.fn(),
  onSave: vi.fn(),
};

// ============================================================
// Tests
// ============================================================

describe('StrategyEditorDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // 模拟 window.confirm
    vi.spyOn(window, 'confirm').mockImplementation(() => true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('创建模式', () => {
    it('应该显示创建策略标题', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      expect(screen.getByText('创建策略')).toBeInTheDocument();
    });

    it('应该使用默认值初始化表单', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 检查默认值
      expect(screen.getByPlaceholderText('例如：Pinbar 15m 保守策略')).toBeInTheDocument();
      expect(screen.getByText('启用')).toBeInTheDocument();
    });

    it('应该默认选择 pinbar 触发器类型', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 触发器类型选择器应该显示 Pinbar
      const triggerSelect = screen.getByLabelText(/触发器类型/);
      expect(triggerSelect).toBeInTheDocument();
    });
  });

  describe('编辑模式', () => {
    it('应该显示编辑策略标题', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={mockStrategy}
          loading={false}
        />
      );

      expect(screen.getByText('编辑策略')).toBeInTheDocument();
    });

    it('应该用策略数据填充表单', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={mockStrategy}
          loading={false}
        />
      );

      // 检查表单字段是否正确填充
      expect(screen.getByDisplayValue('BTC 15m Pinbar 策略')).toBeInTheDocument();
      expect(screen.getByDisplayValue('测试策略描述')).toBeInTheDocument();
    });

    it('应该正确显示启用状态', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={mockStrategy}
          loading={false}
        />
      );

      const switchElement = screen.getByRole('switch', { checked: true });
      expect(switchElement).toBeChecked();
    });

    it('应该正确显示禁用状态', () => {
      const inactiveStrategy: Strategy = {
        ...mockStrategy,
        is_active: false,
      };

      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={inactiveStrategy}
          loading={false}
        />
      );

      const switchElement = screen.getByRole('switch', { checked: false });
      expect(switchElement).not.toBeChecked();
    });
  });

  describe('表单验证', () => {
    it('策略名称为必填项', async () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 清空名称并提交
      const nameInput = screen.getByPlaceholderText('例如：Pinbar 15m 保守策略');
      fireEvent.change(nameInput, { target: { value: '' } });

      const saveButton = screen.getByText('保存');
      fireEvent.click(saveButton);

      // 等待验证
      await waitFor(() => {
        expect(screen.getByText(/请输入策略名称/i)).toBeInTheDocument();
      });
    });

    it('策略名称不能超过 50 个字符', async () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      const longName = 'a'.repeat(60);
      const nameInput = screen.getByPlaceholderText('例如：Pinbar 15m 保守策略');
      fireEvent.change(nameInput, { target: { value: longName } });

      // 应该显示验证错误
      await waitFor(() => {
        expect(screen.getByText(/策略名称不能超过 50 个字符/i)).toBeInTheDocument();
      });
    });

    it('交易币种为必选项', async () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 清空币种选择
      const saveButton = screen.getByText('保存');
      fireEvent.click(saveButton);

      // 等待验证
      await waitFor(() => {
        expect(screen.getByText(/请至少选择一个币种/i)).toBeInTheDocument();
      });
    });

    it('时间周期为必选项', async () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 清空周期选择
      const saveButton = screen.getByText('保存');
      fireEvent.click(saveButton);

      // 等待验证
      await waitFor(() => {
        expect(screen.getByText(/请至少选择一个周期/i)).toBeInTheDocument();
      });
    });
  });

  describe('保存功能', () => {
    it('点击保存按钮应该调用 onSave 回调', async () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 填充表单
      fireEvent.change(screen.getByPlaceholderText('例如：Pinbar 15m 保守策略'), {
        target: { value: '新策略名称' },
      });

      // 点击保存
      const saveButton = screen.getByText('保存');
      fireEvent.click(saveButton);

      // 等待 onSave 被调用
      await waitFor(() => {
        expect(mockHandlers.onSave).toHaveBeenCalled();
      });
    });

    it('保存时应该禁用表单', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={true}
        />
      );

      const nameInput = screen.getByPlaceholderText('例如：Pinbar 15m 保守策略');
      expect(nameInput).toBeDisabled();
    });

    it('保存按钮在 loading 状态显示保存中', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={true}
        />
      );

      expect(screen.getByText('保存中...')).toBeInTheDocument();
    });
  });

  describe('取消功能', () => {
    it('点击取消按钮应该调用 onClose 回调', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      const cancelButton = screen.getByText('取消');
      fireEvent.click(cancelButton);

      expect(mockHandlers.onClose).toHaveBeenCalled();
    });

    it('有未保存更改时取消应该显示确认对话框', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 修改表单
      const nameInput = screen.getByPlaceholderText('例如：Pinbar 15m 保守策略');
      fireEvent.change(nameInput, { target: { value: '修改后的名称' } });

      // 点击取消
      const cancelButton = screen.getByText('取消');
      fireEvent.click(cancelButton);

      // 应该调用 window.confirm
      expect(window.confirm).toHaveBeenCalled();
    });
  });

  describe('触发器参数配置', () => {
    it('应该显示 Pinbar 参数配置表单', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={mockStrategy}
          loading={false}
        />
      );

      expect(screen.getByText('最小影线比例')).toBeInTheDocument();
      expect(screen.getByText('最大实体比例')).toBeInTheDocument();
      expect(screen.getByText('实体位置容差')).toBeInTheDocument();
    });

    it('切换到 Engulfing 触发器应该显示不同的参数', async () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 切换到 Engulfing
      const triggerSelect = screen.getByLabelText(/触发器类型/);
      fireEvent.mouseDown(triggerSelect);

      const engulfingOption = screen.getByText('Engulfing (吞没)');
      fireEvent.click(engulfingOption);

      // 应该显示 Engulfing 参数
      await waitFor(() => {
        expect(screen.getByText('最小实体比例')).toBeInTheDocument();
      });
    });
  });

  describe('风控参数配置', () => {
    it('应该显示最大亏损比例输入', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      expect(screen.getByText('最大亏损比例')).toBeInTheDocument();
    });

    it('应该显示最大杠杆倍数输入', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      expect(screen.getByText('最大杠杆倍数')).toBeInTheDocument();
    });

    it('最大亏损比例应该在有效范围内', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      const lossInput = screen.getByLabelText(/最大亏损比例/);
      expect(lossInput).toHaveAttribute('min', '0.001');
      expect(lossInput).toHaveAttribute('max', '0.1');
    });

    it('最大杠杆倍数应该在有效范围内', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      const leverageInput = screen.getByLabelText(/最大杠杆倍数/);
      expect(leverageInput).toHaveAttribute('min', '1');
      expect(leverageInput).toHaveAttribute('max', '125');
    });
  });

  describe('自动保存机制', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('应该在表单变化后 1 秒自动保存', async () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 修改表单
      const nameInput = screen.getByPlaceholderText('例如：Pinbar 15m 保守策略');
      fireEvent.change(nameInput, { target: { value: '自动保存测试' } });

      // 快进 1 秒
      vi.advanceTimersByTime(1000);

      // 应该触发保存
      await waitFor(() => {
        expect(mockHandlers.onSave).toHaveBeenCalled();
      });
    });
  });

  describe('未保存更改提示', () => {
    it('应该显示未保存更改警告', () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 修改表单
      const nameInput = screen.getByPlaceholderText('例如：Pinbar 15m 保守策略');
      fireEvent.change(nameInput, { target: { value: '修改后的名称' } });

      // 应该显示警告
      expect(screen.getByText('有未保存的更改')).toBeInTheDocument();
    });

    it('保存后应该隐藏未保存更改警告', async () => {
      render(
        <StrategyEditorDrawer
          {...mockHandlers}
          strategy={null}
          loading={false}
        />
      );

      // 修改表单
      const nameInput = screen.getByPlaceholderText('例如：Pinbar 15m 保守策略');
      fireEvent.change(nameInput, { target: { value: '修改后的名称' } });

      // 点击保存
      const saveButton = screen.getByText('保存');
      fireEvent.click(saveButton);

      // 等待保存完成
      await waitFor(() => {
        expect(mockHandlers.onSave).toHaveBeenCalled();
      });

      // 警告应该消失
      expect(screen.queryByText('有未保存的更改')).not.toBeInTheDocument();
    });
  });
});
