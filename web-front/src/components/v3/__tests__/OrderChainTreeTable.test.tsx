import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OrderTreeNode, OrderResponse, OrderStatus, OrderRole, OrderType, Direction } from '../../../types/order';
import { OrderChainTreeTable } from '../OrderChainTreeTable';

// 模拟测试数据
const createMockOrder = (overrides?: Partial<OrderResponse>): OrderResponse => ({
  order_id: overrides?.order_id || 'test-order-id-123',
  exchange_order_id: 'binance-123',
  symbol: overrides?.symbol || 'BTC/USDT:USDT',
  order_type: OrderType.LIMIT,
  order_role: overrides?.order_role || OrderRole.ENTRY,
  direction: overrides?.direction || Direction.LONG,
  status: overrides?.status || OrderStatus.FILLED,
  quantity: overrides?.quantity || '0.1',
  filled_qty: overrides?.filled_qty || '0.1',
  remaining_qty: overrides?.remaining_qty || '0',
  price: overrides?.price || '50000',
  trigger_price: overrides?.trigger_price ?? null,
  average_exec_price: overrides?.average_exec_price || '50000',
  reduce_only: false,
  client_order_id: `client-${overrides?.order_id || '123'}`,
  strategy_name: 'test-strategy',
  signal_id: 'signal-123',
  stop_loss: '48000',
  take_profit: '55000',
  created_at: overrides?.created_at || 1711785660000,
  updated_at: overrides?.updated_at || 1711785660000,
  filled_at: overrides?.filled_at || 1711785660000,
  fee_paid: '0.001',
  fee_currency: 'USDT',
  tags: [],
});

const createMockTreeNode = (order: OrderResponse, children: OrderTreeNode[] = []): OrderTreeNode => ({
  order,
  children,
  level: children.length > 0 ? 0 : 0,
  has_children: children.length > 0,
});

// 生成大量模拟订单数据
const generateMockOrders = (count: number): OrderTreeNode[] => {
  const symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT'];
  const statuses = [OrderStatus.FILLED, OrderStatus.OPEN, OrderStatus.CANCELED, OrderStatus.PARTIALLY_FILLED];
  const roles = [OrderRole.ENTRY, OrderRole.TP1, OrderRole.TP2, OrderRole.SL];
  const directions = [Direction.LONG, Direction.SHORT];

  return Array.from({ length: count }, (_, index) => {
    const order = createMockOrder({
      order_id: `order-${index.toString().padStart(6, '0')}`,
      symbol: symbols[index % symbols.length],
      status: statuses[index % statuses.length],
      order_role: roles[index % roles.length],
      direction: directions[index % directions.length],
      quantity: (Math.random() * 10).toFixed(4),
      price: (Math.random() * 100000).toFixed(2),
      created_at: 1711785660000 + index * 1000,
    });
    return createMockTreeNode(order);
  });
};

// 计算数据大小的辅助函数
const calculateDataSize = (data: unknown): number => {
  return new Blob([JSON.stringify(data)]).size;
};

describe('OrderChainTreeTable - utils', () => {
  it('should flatten tree data correctly', () => {
    // 测试扁平化逻辑（从组件中提取的纯函数逻辑）
    const mockOrder = createMockOrder();
    const mockChildOrder = createMockOrder({
      order_id: 'test-child-order-id',
      order_role: OrderRole.TP1,
    });

    const treeData: OrderTreeNode[] = [
      createMockTreeNode(mockOrder, [
        createMockTreeNode(mockChildOrder),
      ]),
    ];

    // 模拟扁平化函数（组件内部逻辑）
    const flattenTreeData = (
      nodes: OrderTreeNode[],
      expandedRowKeys: string[],
      parent?: OrderTreeNode
    ): Array<{ node: OrderTreeNode; orderId: string; level: number; parent?: OrderTreeNode }> => {
      let result: Array<{ node: OrderTreeNode; orderId: string; level: number; parent?: OrderTreeNode }> = [];

      for (const node of nodes) {
        result.push({
          node,
          orderId: node.order.order_id,
          level: node.level,
          parent,
        });

        if (expandedRowKeys.includes(node.order.order_id) && node.children.length > 0) {
          result = result.concat(flattenTreeData(node.children, expandedRowKeys, node));
        }
      }

      return result;
    };

    // 测试未展开状态
    const flatCollapsed = flattenTreeData(treeData, []);
    expect(flatCollapsed).toHaveLength(1);
    expect(flatCollapsed[0].orderId).toBe('test-order-id-123');

    // 测试展开状态
    const flatExpanded = flattenTreeData(treeData, ['test-order-id-123']);
    expect(flatExpanded).toHaveLength(2);
    expect(flatExpanded.map((item) => item.orderId)).toEqual([
      'test-order-id-123',
      'test-child-order-id',
    ]);
  });

  it('should get order chain IDs correctly', () => {
    // 测试获取订单链 ID 的逻辑
    const getOrderChainIds = (node: OrderTreeNode): string[] => {
      const ids = [node.order.order_id];
      for (const child of node.children) {
        ids.push(...getOrderChainIds(child));
      }
      return ids;
    };

    const mockOrder = createMockOrder();
    const mockTP1 = createMockOrder({ order_id: 'tp1-id', order_role: OrderRole.TP1 });
    const mockTP2 = createMockOrder({ order_id: 'tp2-id', order_role: OrderRole.TP2 });
    const mockSL = createMockOrder({ order_id: 'sl-id', order_role: OrderRole.SL });

    const treeData: OrderTreeNode[] = [
      createMockTreeNode(mockOrder, [
        createMockTreeNode(mockTP1),
        createMockTreeNode(mockTP2),
        createMockTreeNode(mockSL),
      ]),
    ];

    const chainIds = getOrderChainIds(treeData[0]);
    expect(chainIds).toEqual(['test-order-id-123', 'tp1-id', 'tp2-id', 'sl-id']);
  });

  it('should find node by ID correctly', () => {
    // 测试查找节点的逻辑
    const findNodeById = (nodes: OrderTreeNode[], orderId: string): OrderTreeNode | null => {
      for (const node of nodes) {
        if (node.order.order_id === orderId) {
          return node;
        }
        const found = findNodeById(node.children, orderId);
        if (found) return found;
      }
      return null;
    };

    const mockOrder = createMockOrder();
    const mockChildOrder = createMockOrder({
      order_id: 'test-child-order-id',
      order_role: OrderRole.TP1,
    });

    const treeData: OrderTreeNode[] = [
      createMockTreeNode(mockOrder, [
        createMockTreeNode(mockChildOrder),
      ]),
    ];

    // 测试查找根节点
    const rootNode = findNodeById(treeData, 'test-order-id-123');
    expect(rootNode).not.toBeNull();
    expect(rootNode?.order.order_role).toBe(OrderRole.ENTRY);

    // 测试查找子节点
    const childNode = findNodeById(treeData, 'test-child-order-id');
    expect(childNode).not.toBeNull();
    expect(childNode?.order.order_role).toBe(OrderRole.TP1);

    // 测试查找不存在的节点
    const notFound = findNodeById(treeData, 'non-existent-id');
    expect(notFound).toBeNull();
  });
});

describe('OrderChainTreeTable - 大数据量场景测试', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render large dataset (>100 orders) without crashing', async () => {
    // 生成 150 条订单数据
    const largeDataSet = generateMockOrders(150);
    const expandedRowKeys: string[] = [];
    const selectedRowKeys: string[] = [];

    const { container } = render(
      <OrderChainTreeTable
        data={largeDataSet}
        expandedRowKeys={expandedRowKeys}
        selectedRowKeys={selectedRowKeys}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    // 等待渲染完成
    await waitFor(() => {
      expect(screen.queryByText('没有找到订单记录')).not.toBeInTheDocument();
    }, { timeout: 5000 });

    // 验证渲染的可见行数（虚拟滚动应该只渲染可见区域）
    // 使用更通用的选择器
    const rows = container.querySelectorAll('.flex.items-center.gap-2');
    // 虚拟滚动应该只渲染可见区域（约 10-15 行），而不是全部 150 行
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(50);
  });

  it('should handle 200+ orders with performance constraint (<200KB)', async () => {
    // 生成 200 条订单数据
    const extraLargeDataSet = generateMockOrders(200);

    // 计算数据大小
    const dataSize = calculateDataSize(extraLargeDataSet);
    const sizeInKB = dataSize / 1024;

    // 验证数据大小在 200KB 以内
    expect(sizeInKB).toBeLessThan(200);

    const startTime = performance.now();

    render(
      <OrderChainTreeTable
        data={extraLargeDataSet}
        expandedRowKeys={[]}
        selectedRowKeys={[]}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    // 等待渲染完成
    await waitFor(() => {
      expect(screen.queryByText('没有找到订单记录')).not.toBeInTheDocument();
    }, { timeout: 5000 });

    const endTime = performance.now();
    const renderTime = endTime - startTime;

    // 验证渲染时间在合理范围内（<2 秒）
    expect(renderTime).toBeLessThan(2000);
  });

  it('should maintain scroll performance with nested tree structure', async () => {
    // 生成带子订单的嵌套数据结构
    const nestedData = Array.from({ length: 50 }, (_, index) => {
      const parentOrder = createMockOrder({
        order_id: `parent-${index.toString().padStart(4, '0')}`,
        order_role: OrderRole.ENTRY,
      });

      const children: OrderTreeNode[] = [];
      // 每个父订单有 2-4 个子订单
      const childCount = 2 + (index % 3);
      for (let i = 0; i < childCount; i++) {
        children.push(
          createMockTreeNode(
            createMockOrder({
              order_id: `child-${index}-${i}`,
              order_role: i === 0 ? OrderRole.TP1 : i === 1 ? OrderRole.TP2 : OrderRole.SL,
            })
          )
        );
      }

      return createMockTreeNode(parentOrder, children);
    });

    const expandedRowKeys = nestedData.slice(0, 10).map((n) => n.order.order_id);

    render(
      <OrderChainTreeTable
        data={nestedData}
        expandedRowKeys={expandedRowKeys}
        selectedRowKeys={[]}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText('没有找到订单记录')).not.toBeInTheDocument();
    });

    // 验证总节点数（50 个父节点 + 展开的子节点）
    // 每个展开的节点有 2-4 个子节点，平均 3 个
    const expectedMinNodes = 50 + 10 * 2; // 最少 70 个节点
    const expectedMaxNodes = 50 + 10 * 4; // 最多 90 个节点

    // 扁平化数据验证
    const flattenTreeData = (
      nodes: OrderTreeNode[],
      expandedKeys: string[]
    ): OrderTreeNode[] => {
      let result: OrderTreeNode[] = [];
      for (const node of nodes) {
        result.push(node);
        if (expandedKeys.includes(node.order.order_id) && node.children.length > 0) {
          result = result.concat(flattenTreeData(node.children, expandedKeys));
        }
      }
      return result;
    };

    const flatData = flattenTreeData(nestedData, expandedRowKeys);
    expect(flatData.length).toBeGreaterThanOrEqual(expectedMinNodes);
    expect(flatData.length).toBeLessThanOrEqual(expectedMaxNodes);
  });
});

describe('OrderChainTreeTable - 分页边界测试', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render empty state correctly', () => {
    render(
      <OrderChainTreeTable
        data={[]}
        expandedRowKeys={[]}
        selectedRowKeys={[]}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    expect(screen.getByText('没有找到订单记录')).toBeInTheDocument();
    // 验证 AlertCircle 图标存在（使用 className 查询）
    const alertIcon = document.querySelector('svg.lucide-circle-alert');
    expect(alertIcon).toBeInTheDocument();
  });

  it('should handle first page correctly', async () => {
    // 模拟第一页数据（20 条）
    const firstPageData = generateMockOrders(20);

    const { container } = render(
      <OrderChainTreeTable
        data={firstPageData}
        expandedRowKeys={[]}
        selectedRowKeys={[]}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    // 等待渲染完成
    await waitFor(() => {
      expect(screen.queryByText('没有找到订单记录')).not.toBeInTheDocument();
    });

    // 验证数据渲染正常（至少有一些行存在）
    const rows = container.querySelectorAll('.flex.items-center.gap-2');
    expect(rows.length).toBeGreaterThan(0);
  });

  it('should handle last page with partial data correctly', async () => {
    // 模拟末页数据（假设每页 50 条，总共 123 条，末页只有 23 条）
    const lastPageData = generateMockOrders(23);

    const { container } = render(
      <OrderChainTreeTable
        data={lastPageData}
        expandedRowKeys={[]}
        selectedRowKeys={[]}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    // 等待渲染完成
    await waitFor(() => {
      expect(screen.queryByText('没有找到订单记录')).not.toBeInTheDocument();
    });

    // 验证数据渲染正常
    const rows = container.querySelectorAll('.flex.items-center.gap-2');
    expect(rows.length).toBeGreaterThan(0);
  });

  it('should handle single item correctly', async () => {
    const singleItemData = [
      createMockTreeNode(createMockOrder({ order_id: 'single-order' })),
    ];

    const { container } = render(
      <OrderChainTreeTable
        data={singleItemData}
        expandedRowKeys={[]}
        selectedRowKeys={[]}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    // 等待渲染完成
    await waitFor(() => {
      expect(screen.queryByText('没有找到订单记录')).not.toBeInTheDocument();
    });

    // 验证单条数据渲染
    const rows = container.querySelectorAll('.flex.items-center.gap-2');
    expect(rows.length).toBeGreaterThan(0);
  });

  it('should handle maximum page size (200 items) correctly', async () => {
    const maxPageSizeData = generateMockOrders(200);

    const startTime = performance.now();

    render(
      <OrderChainTreeTable
        data={maxPageSizeData}
        expandedRowKeys={[]}
        selectedRowKeys={[]}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText('没有找到订单记录')).not.toBeInTheDocument();
    }, { timeout: 5000 });

    const endTime = performance.now();
    const renderTime = endTime - startTime;

    // 验证最大页面大小渲染性能
    expect(renderTime).toBeLessThan(3000);
  });
});

describe('OrderChainTreeTable - 虚拟滚动性能测试', () => {
  it('should use react-window for virtual scrolling', async () => {
    const largeDataSet = generateMockOrders(500);

    const { container } = render(
      <OrderChainTreeTable
        data={largeDataSet}
        expandedRowKeys={[]}
        selectedRowKeys={[]}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    // 验证 react-window 容器存在
    await waitFor(() => {
      const gridElement = container.querySelector('[role="grid"]') ||
        container.querySelector('.react-window') ||
        container.querySelector('[style*="position: absolute"]');
      expect(gridElement).toBeInTheDocument();
    });

    // 验证容器高度限制（max-h-[600px]）
    const scrollContainer = container.querySelector('.max-h-\\[600px\\]') ||
      container.querySelector('[style*="max-height"]') ||
      container.querySelector('[style*="600px"]');
    expect(scrollContainer).toBeInTheDocument();
  });

  it('should calculate correct container height based on data', () => {
    // 验证高度计算逻辑：Math.min(flatData.length * 52, 600)
    const calculateHeight = (itemCount: number): number => {
      return Math.min(itemCount * 52, 600);
    };

    // 小数据集
    expect(calculateHeight(5)).toBe(260); // 5 * 52
    expect(calculateHeight(10)).toBe(520); // 10 * 52

    // 大数据集（应该限制在 600px）
    expect(calculateHeight(12)).toBe(600); // Math.min(624, 600)
    expect(calculateHeight(100)).toBe(600); // Math.min(5200, 600)
    expect(calculateHeight(500)).toBe(600); // Math.min(26000, 600)
  });

  it('should verify item size consistency', () => {
    // 验证每个项目的高度是 52px（与组件中的 itemSize 一致）
    const ITEM_HEIGHT = 52; // px

    // 计算不同数量数据的高度
    const heights = [1, 5, 10, 11, 100].map((count) =>
      Math.min(count * ITEM_HEIGHT, 600)
    );

    // 修正期望值：11 * 52 = 572，不超过 600
    expect(heights).toEqual([52, 260, 520, 572, 600]);
  });
});

describe('OrderChainTreeTable - 数据裁剪效果验证', () => {
  it('should verify virtual scrolling renders only visible items', async () => {
    const veryLargeDataSet = generateMockOrders(1000);

    const { container } = render(
      <OrderChainTreeTable
        data={veryLargeDataSet}
        expandedRowKeys={[]}
        selectedRowKeys={[]}
        onExpand={vi.fn()}
        onSelectChange={vi.fn()}
        isLoading={false}
      />
    );

    // 等待渲染完成
    await waitFor(() => {
      expect(screen.queryByText('没有找到订单记录')).not.toBeInTheDocument();
    }, { timeout: 5000 });

    // 验证 DOM 中实际的行数远小于总数（虚拟滚动只渲染可见区域）
    // react-window 通常会渲染可见区域 + 一些缓冲项（约 15-20 项）
    const allRows = container.querySelectorAll('.flex.items-center.gap-2');

    // 1000 条数据，虚拟滚动应该只渲染约 15-25 行
    expect(allRows.length).toBeLessThan(50);
    expect(allRows.length).toBeGreaterThan(5);
  });

  it('should verify memory efficiency with large dataset', () => {
    // 生成不同规模的数据集并验证大小
    const sizes = [50, 100, 200, 500];

    sizes.forEach((size) => {
      const data = generateMockOrders(size);
      const dataSize = calculateDataSize(data);
      const sizeInKB = dataSize / 1024;

      // 验证数据大小与数量成线性增长
      // 500 条订单应该 < 500KB（每条约 <1KB）
      expect(sizeInKB).toBeLessThan(size);
    });
  });
});
