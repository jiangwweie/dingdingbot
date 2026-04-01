/**
 * SST - OrderDetailsDrawer Component Tests
 *
 * Component Under Test (CUT): OrderDetailsDrawer
 * Location: web-front/src/components/v3/OrderDetailsDrawer.tsx
 *
 * Test Scope:
 * - Component renders without crashing
 * - Order details display correctly
 * - K-line chart integration
 * - Order markers visualization
 * - Cancel order functionality
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OrderDetailsDrawer } from '../OrderDetailsDrawer';
import { OrderResponse, OrderStatus, OrderType, OrderRole, Direction } from '../../types/order';
import * as api from '../../lib/api';

// Mock fetchOrderKlineContext
vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual('../../lib/api');
  return {
    ...actual,
    fetchOrderKlineContext: vi.fn(),
  };
});

// Mock date-fns
vi.mock('date-fns', () => ({
  format: (date: Date, format: string) => {
    const d = new Date(date);
    if (format.includes('MM-dd')) return '01-15 10:30';
    if (format.includes('yyyy-MM-dd')) return '2024-01-15 10:30:00';
    return d.toISOString();
  },
}));

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  X: () => <svg data-testid="icon-x" />,
  Clock: () => <svg data-testid="icon-clock" />,
  CheckCircle: () => <svg data-testid="icon-check" />,
  AlertCircle: () => <svg data-testid="icon-alert" />,
  XCircle: () => <svg data-testid="icon-x-circle" />,
  Timer: () => <svg data-testid="icon-timer" />,
  TrendingUp: () => <svg data-testid="icon-trending-up" />,
  TrendingDown: () => <svg data-testid="icon-trending-down" />,
  Activity: () => <svg data-testid="icon-activity" />,
}));

// Mock recharts
vi.mock('recharts', () => ({
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  ReferenceLine: () => <div data-testid="reference-line" />,
  ReferenceDot: () => <div data-testid="reference-dot" />,
}));

// Mock child components
vi.mock('../DecimalDisplay', () => ({
  DecimalDisplay: ({ value }: any) => <span data-testid="decimal-display">{value}</span>,
}));

vi.mock('../OrderStatusBadge', () => ({
  OrderStatusBadge: ({ status }: any) => <span data-testid="order-status-badge">{status}</span>,
}));

vi.mock('../OrderRoleBadge', () => ({
  OrderRoleBadge: ({ role }: any) => <span data-testid="order-role-badge">{role}</span>,
}));

vi.mock('../DirectionBadge', () => ({
  DirectionBadge: ({ direction }: any) => <span data-testid="direction-badge">{direction}</span>,
}));

// Test fixtures
const createMockOrder = (overrides?: Partial<OrderResponse>): OrderResponse => ({
  order_id: 'order-123-456-789',
  exchange_order_id: 'BINANCE-123456',
  symbol: 'BTC/USDT:USDT',
  order_type: OrderType.LIMIT,
  order_role: OrderRole.ENTRY,
  direction: Direction.LONG,
  status: OrderStatus.FILLED,
  quantity: '0.1',
  filled_qty: '0.1',
  remaining_qty: '0',
  price: '45000.00',
  trigger_price: null,
  average_exec_price: '45000.00',
  reduce_only: false,
  client_order_id: 'client-order-123',
  strategy_name: 'Pinbar Strategy',
  signal_id: 'signal-123',
  stop_loss: '44000.00',
  take_profit: '47000.00',
  created_at: 1705315800000,
  updated_at: 1705316400000,
  filled_at: 1705316400000,
  fee_paid: '0.5',
  fee_currency: 'USDT',
  tags: [],
  ...overrides,
});

const mockKlineResponse = {
  order: createMockOrder(),
  klines: [
    [1705315800000, 44800, 44900, 44700, 44850, 100],
    [1705316400000, 44850, 45100, 44800, 45000, 150],
    [1705317000000, 45000, 45200, 44950, 45150, 120],
  ],
};

describe('OrderDetailsDrawer', () => {
  const mockOnClose = vi.fn();
  const mockOnCancelOrder = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should not render when isOpen is false', () => {
      render(
        <OrderDetailsDrawer
          order={createMockOrder()}
          isOpen={false}
          onClose={mockOnClose}
        />
      );

      // Drawer should not be in document when closed
      expect(screen.queryByText('订单详情')).not.toBeInTheDocument();
    });

    it('should render null when order is null', () => {
      render(
        <OrderDetailsDrawer
          order={null}
          isOpen={true}
          onClose={mockOnClose}
        />
      );

      expect(screen.queryByText('订单详情')).not.toBeInTheDocument();
    });

    it('should render order details when isOpen is true and order is provided', () => {
      const order = createMockOrder();
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      expect(screen.getByText('订单详情')).toBeInTheDocument();
      expect(screen.getByText('BTC/USDT:USDT'.replace(':USDT', ''))).toBeInTheDocument();
      expect(screen.getByTestId('order-status-badge')).toHaveTextContent(OrderStatus.FILLED);
      expect(screen.getByTestId('order-role-badge')).toHaveTextContent(OrderRole.ENTRY);
      expect(screen.getByTestId('direction-badge')).toHaveTextContent(Direction.LONG);
    });

    it('should display order ID truncated', () => {
      const order = createMockOrder({ order_id: 'abc123456789xyz' });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      // Should show first 8 and last 4 characters
      expect(screen.getByText('abc12345...9xyz')).toBeInTheDocument();
    });
  });

  describe('Order Type Display', () => {
    it.each([
      [OrderType.MARKET, '市价单'],
      [OrderType.LIMIT, '限价单'],
      [OrderType.STOP_MARKET, '止损市价单'],
      [OrderType.STOP_LIMIT, '止损限价单'],
    ])('should display %s as %s', (orderType, expectedLabel) => {
      const order = createMockOrder({ order_type: orderType });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      expect(screen.getByText(expectedLabel)).toBeInTheDocument();
    });
  });

  describe('Order Parameters', () => {
    it('should display order quantity and filled quantity', () => {
      const order = createMockOrder({ quantity: '0.5', filled_qty: '0.3' });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      expect(screen.getAllByTestId('decimal-display')).toHaveLength(4); // quantity, filled_qty, price, trigger_price
    });

    it('should display stop loss and take profit when set', () => {
      const order = createMockOrder({
        stop_loss: '44000.00',
        take_profit: '47000.00',
      });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      expect(screen.getByText('止损价格')).toBeInTheDocument();
      expect(screen.getByText('止盈价格')).toBeInTheDocument();
    });

    it('should not display stop loss/take profit sections when not set', () => {
      const order = createMockOrder({
        stop_loss: null,
        take_profit: null,
      });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      expect(screen.queryByText('止损价格')).not.toBeInTheDocument();
      expect(screen.queryByText('止盈价格')).not.toBeInTheDocument();
    });

    it('should display reduce only badge when reduce_only is true', () => {
      const order = createMockOrder({ reduce_only: true });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      expect(screen.getByText('仅减仓模式')).toBeInTheDocument();
    });

    it('should display strategy name when set', () => {
      const order = createMockOrder({ strategy_name: 'Test Strategy' });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      expect(screen.getByText('Test Strategy')).toBeInTheDocument();
    });
  });

  describe('Progress Bar', () => {
    it('should show 100% filled for fully filled order', () => {
      const order = createMockOrder({ quantity: '0.1', filled_qty: '0.1' });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      // Progress bar should be at 100%
      const progressBar = document.querySelector('.bg-green-500');
      expect(progressBar).toHaveStyle('width: 100%');
    });

    it('should show 50% filled for partially filled order', () => {
      const order = createMockOrder({ quantity: '0.2', filled_qty: '0.1' });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      const progressBar = document.querySelector('.bg-blue-500');
      expect(progressBar).toHaveStyle('width: 50%');
    });

    it('should show 0% filled for unfilled order', () => {
      const order = createMockOrder({ quantity: '0.1', filled_qty: '0' });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      const progressBar = document.querySelector('.bg-gray-300');
      expect(progressBar).toHaveStyle('width: 0%');
    });
  });

  describe('Cancel Order Functionality', () => {
    it('should show cancel button for OPEN orders', () => {
      const order = createMockOrder({ status: OrderStatus.OPEN });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          onCancelOrder={mockOnCancelOrder}
          showKlineChart={false}
        />
      );

      expect(screen.getByText('取消订单')).toBeInTheDocument();
    });

    it('should show cancel button for PENDING orders', () => {
      const order = createMockOrder({ status: OrderStatus.PENDING });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          onCancelOrder={mockOnCancelOrder}
          showKlineChart={false}
        />
      );

      expect(screen.getByText('取消订单')).toBeInTheDocument();
    });

    it('should show cancel button for PARTIALLY_FILLED orders', () => {
      const order = createMockOrder({ status: OrderStatus.PARTIALLY_FILLED });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          onCancelOrder={mockOnCancelOrder}
          showKlineChart={false}
        />
      );

      expect(screen.getByText('取消订单')).toBeInTheDocument();
    });

    it('should NOT show cancel button for FILLED orders', () => {
      const order = createMockOrder({ status: OrderStatus.FILLED });
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          onCancelOrder={mockOnCancelOrder}
          showKlineChart={false}
        />
      );

      expect(screen.queryByText('取消订单')).not.toBeInTheDocument();
    });

    it('should call onCancelOrder when cancel button is clicked', async () => {
      const order = createMockOrder({ status: OrderStatus.OPEN });
      mockOnCancelOrder.mockResolvedValue(undefined);

      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          onCancelOrder={mockOnCancelOrder}
          showKlineChart={false}
        />
      );

      await userEvent.click(screen.getByText('取消订单'));

      expect(mockOnCancelOrder).toHaveBeenCalledWith(order.order_id, order.symbol);
    });

    it('should close drawer after successful cancel', async () => {
      const order = createMockOrder({ status: OrderStatus.OPEN });
      mockOnCancelOrder.mockResolvedValue(undefined);

      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          onCancelOrder={mockOnCancelOrder}
          showKlineChart={false}
        />
      );

      await userEvent.click(screen.getByText('取消订单'));

      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  describe('K-line Chart Integration', () => {
    it('should not fetch kline data when showKlineChart is false', () => {
      const order = createMockOrder();
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      expect(api.fetchOrderKlineContext).not.toHaveBeenCalled();
    });

    it('should fetch kline data when drawer opens and showKlineChart is true', async () => {
      const order = createMockOrder();
      vi.mocked(api.fetchOrderKlineContext).mockResolvedValue(mockKlineResponse);

      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={true}
        />
      );

      await waitFor(() => {
        expect(api.fetchOrderKlineContext).toHaveBeenCalledWith(order.order_id, order.symbol);
      });
    });

    it('should display loading state while fetching kline data', () => {
      const order = createMockOrder();
      vi.mocked(api.fetchOrderKlineContext).mockImplementation(() => new Promise(() => {}));

      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={true}
        />
      );

      expect(screen.getByText('加载 K 线数据...')).toBeInTheDocument();
    });

    it('should display error message when kline fetch fails', async () => {
      const order = createMockOrder();
      vi.mocked(api.fetchOrderKlineContext).mockRejectedValue(new Error('Network error'));

      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={true}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });

    it('should render kline chart when data is loaded', async () => {
      const order = createMockOrder();
      vi.mocked(api.fetchOrderKlineContext).mockResolvedValue(mockKlineResponse);

      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={true}
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      });
    });

    it('should render order markers on chart', async () => {
      const order = createMockOrder();
      vi.mocked(api.fetchOrderKlineContext).mockResolvedValue(mockKlineResponse);

      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={true}
        />
      );

      await waitFor(() => {
        // Should have at least entry marker
        const markers = screen.getAllByTestId('reference-dot');
        expect(markers.length).toBeGreaterThan(0);
      });
    });

    it('should display K 线走势图 heading', async () => {
      const order = createMockOrder();
      vi.mocked(api.fetchOrderKlineContext).mockResolvedValue(mockKlineResponse);

      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={true}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('K 线走势图')).toBeInTheDocument();
      });
    });
  });

  describe('Close Functionality', () => {
    it('should call onClose when clicking close button', async () => {
      const order = createMockOrder();
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      const closeButton = screen.getByRole('button');
      await userEvent.click(closeButton);

      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should call onClose when clicking backdrop', async () => {
      const order = createMockOrder();
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      // Click on backdrop (fixed inset-0 element)
      const backdrop = document.querySelector('.fixed.inset-0');
      if (backdrop) {
        fireEvent.click(backdrop);
        expect(mockOnClose).toHaveBeenCalled();
      }
    });
  });

  describe('Timestamp Display', () => {
    it('should display created_at and updated_at timestamps', () => {
      const order = createMockOrder();
      render(
        <OrderDetailsDrawer
          order={order}
          isOpen={true}
          onClose={mockOnClose}
          showKlineChart={false}
        />
      );

      expect(screen.getByText('创建时间')).toBeInTheDocument();
      expect(screen.getByText('更新时间')).toBeInTheDocument();
    });
  });
});
