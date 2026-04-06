/**
 * StrategyCard 组件单元测试
 *
 * 测试覆盖:
 * - 策略基本信息展示
 * - 启用/禁用切换功能
 * - 编辑/删除操作回调
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StrategyCard } from '../StrategyCard';
import type { Strategy } from '../../../api/config';

// ============================================================
// Mock Data
// ============================================================

const mockStrategy: Strategy = {
  id: 'test-strategy-1',
  name: 'BTC 15m Pinbar 策略',
  description: '这是一个基于 Pinbar 形态的 15 分钟策略',
  is_active: true,
  trigger_config: {
    type: 'pinbar',
    params: {
      min_wick_ratio: 0.6,
      max_body_ratio: 0.3,
      body_position_tolerance: 0.1,
    },
  },
  filter_configs: [
    { type: 'ema', enabled: true, params: { period: 60 } },
    { type: 'mtf', enabled: true, params: { mapping: '15m->1h' } },
  ],
  filter_logic: 'AND',
  symbols: ['BTC/USDT:USDT', 'ETH/USDT:USDT'],
  timeframes: ['15m', '1h'],
  created_at: '2026-04-01T10:00:00Z',
  updated_at: '2026-04-06T15:30:00Z',
};

const mockInactiveStrategy: Strategy = {
  ...mockStrategy,
  id: 'test-strategy-2',
  is_active: false,
  name: '已禁用策略',
};

const mockStrategyNoFilters: Strategy = {
  ...mockStrategy,
  id: 'test-strategy-3',
  filter_configs: [],
};

// ============================================================
// Tests
// ============================================================

describe('StrategyCard', () => {
  const mockHandlers = {
    onEdit: vi.fn(),
    onToggleEnable: vi.fn(),
    onDelete: vi.fn(),
    onDuplicate: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('基本信息展示', () => {
    it('应该正确显示策略名称', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      expect(screen.getByText('BTC 15m Pinbar 策略')).toBeInTheDocument();
    });

    it('应该正确显示策略描述', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      expect(
        screen.getByText('这是一个基于 Pinbar 形态的 15 分钟策略')
      ).toBeInTheDocument();
    });

    it('应该正确显示触发器类型标签', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      expect(screen.getByText('Pinbar')).toBeInTheDocument();
    });

    it('应该正确显示过滤器数量', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      expect(screen.getByText('2 过滤器')).toBeInTheDocument();
    });

    it('没有过滤器时不显示过滤器标签', () => {
      render(<StrategyCard strategy={mockStrategyNoFilters} {...mockHandlers} />);

      expect(screen.queryByText('过滤器')).not.toBeInTheDocument();
    });

    it('应该正确显示币种标签', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      expect(screen.getByText('BTC')).toBeInTheDocument();
      expect(screen.getByText('ETH')).toBeInTheDocument();
    });

    it('应该正确显示周期标签', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      expect(screen.getByText('15m')).toBeInTheDocument();
      expect(screen.getByText('1h')).toBeInTheDocument();
    });
  });

  describe('启用/禁用状态', () => {
    it('应该显示启用状态为"启用"当 is_active=true', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      const switchElement = screen.getByRole('switch');
      expect(switchElement).toHaveTextContent('启用');
      expect(switchElement).toBeChecked();
    });

    it('应该显示启用状态为"禁用"当 is_active=false', () => {
      render(<StrategyCard strategy={mockInactiveStrategy} {...mockHandlers} />);

      const switchElement = screen.getByRole('switch');
      expect(switchElement).toHaveTextContent('禁用');
      expect(switchElement).not.toBeChecked();
    });

    it('应该禁用已禁用策略的卡片样式', () => {
      const { container } = render(
        <StrategyCard strategy={mockInactiveStrategy} {...mockHandlers} />
      );

      const cardElement = container.querySelector('.strategy-card');
      expect(cardElement).toHaveClass('opacity-75');
    });

    it('点击 Switch 应该调用 onToggleEnable 回调', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      const switchElement = screen.getByRole('switch');
      fireEvent.click(switchElement);

      expect(mockHandlers.onToggleEnable).toHaveBeenCalledWith(
        'test-strategy-1',
        false
      );
    });
  });

  describe('操作按钮', () => {
    it('应该显示编辑按钮', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      const editButton = screen.getByRole('button', { name: /编辑/i });
      expect(editButton).toBeInTheDocument();
    });

    it('应该显示删除按钮', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      const deleteButton = screen.getByRole('button', { name: /删除/i });
      expect(deleteButton).toBeInTheDocument();
    });

    it('点击编辑按钮应该调用 onEdit 回调', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      const editButton = screen.getByRole('button', { name: /编辑/i });
      fireEvent.click(editButton);

      expect(mockHandlers.onEdit).toHaveBeenCalledWith(mockStrategy);
    });

    it('点击删除按钮应该调用 onDelete 回调', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      const deleteButton = screen.getByRole('button', { name: /删除/i });
      fireEvent.click(deleteButton);

      expect(mockHandlers.onDelete).toHaveBeenCalledWith('test-strategy-1');
    });

    it('应该显示复制按钮当 onDuplicate 回调提供时', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      const duplicateButton = screen.getByRole('button', { name: /复制/i });
      expect(duplicateButton).toBeInTheDocument();
    });

    it('点击复制按钮应该调用 onDuplicate 回调', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      const duplicateButton = screen.getByRole('button', { name: /复制/i });
      fireEvent.click(duplicateButton);

      expect(mockHandlers.onDuplicate).toHaveBeenCalledWith(mockStrategy);
    });
  });

  describe('触发器类型颜色', () => {
    it('应该为 pinbar 类型显示蓝色标签', () => {
      render(<StrategyCard strategy={mockStrategy} {...mockHandlers} />);

      const pinbarTag = screen.getByText('Pinbar');
      expect(pinbarTag).toHaveClass('ant-tag-blue');
    });

    it('应该为 engulfing 类型显示紫色标签', () => {
      const engulfingStrategy: Strategy = {
        ...mockStrategy,
        trigger_config: { type: 'engulfing', params: {} },
      };
      render(<StrategyCard strategy={engulfingStrategy} {...mockHandlers} />);

      const engulfingTag = screen.getByText('Engulfing');
      expect(engulfingTag).toHaveClass('ant-tag-purple');
    });

    it('应该为 doji 类型显示青色标签', () => {
      const dojiStrategy: Strategy = {
        ...mockStrategy,
        trigger_config: { type: 'doji', params: {} },
      };
      render(<StrategyCard strategy={dojiStrategy} {...mockHandlers} />);

      const dojiTag = screen.getByText('Doji');
      expect(dojiTag).toHaveClass('ant-tag-cyan');
    });

    it('应该为 hammer 类型显示绿色标签', () => {
      const hammerStrategy: Strategy = {
        ...mockStrategy,
        trigger_config: { type: 'hammer', params: {} },
      };
      render(<StrategyCard strategy={hammerStrategy} {...mockHandlers} />);

      const hammerTag = screen.getByText('Hammer');
      expect(hammerTag).toHaveClass('ant-tag-green');
    });
  });

  describe('边界情况', () => {
    it('应该处理缺少描述的astlgy', () => {
      const strategyNoDesc: Strategy = {
        ...mockStrategy,
        description: undefined,
      };
      render(<StrategyCard strategy={strategyNoDesc} {...mockHandlers} />);

      expect(screen.queryByText('策略描述')).not.toBeInTheDocument();
    });

    it('应该处理空币种列表', () => {
      const strategyNoSymbols: Strategy = {
        ...mockStrategy,
        symbols: [],
      };
      render(<StrategyCard strategy={strategyNoSymbols} {...mockHandlers} />);

      // 不应该崩溃
      expect(screen.getByText('Pinbar')).toBeInTheDocument();
    });

    it('应该处理空周期列表', () => {
      const strategyNoTimeframes: Strategy = {
        ...mockStrategy,
        timeframes: [],
      };
      render(<StrategyCard strategy={strategyNoTimeframes} {...mockHandlers} />);

      // 不应该崩溃
      expect(screen.getByText('Pinbar')).toBeInTheDocument();
    });

    it('应该处理未知触发器类型', () => {
      const strategyUnknownTrigger: Strategy = {
        ...mockStrategy,
        trigger_config: { type: 'unknown_trigger', params: {} },
      };
      render(<StrategyCard strategy={strategyUnknownTrigger} {...mockHandlers} />);

      expect(screen.getByText('unknown_trigger')).toBeInTheDocument();
    });
  });
});
