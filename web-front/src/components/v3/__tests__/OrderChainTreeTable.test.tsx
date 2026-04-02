import { describe, it, expect, vi } from 'vitest';
import { OrderTreeNode, OrderResponse, OrderStatus, OrderRole, OrderType, Direction } from '../../../types/order';

// 模拟测试数据
const createMockOrder = (overrides?: Partial<OrderResponse>): OrderResponse => ({
  order_id: overrides?.order_id || 'test-order-id-123',
  exchange_order_id: 'binance-123',
  symbol: 'BTC/USDT:USDT',
  order_type: OrderType.LIMIT,
  order_role: overrides?.order_role || OrderRole.ENTRY,
  direction: Direction.LONG,
  status: OrderStatus.FILLED,
  quantity: '0.1',
  filled_qty: '0.1',
  remaining_qty: '0',
  price: '50000',
  trigger_price: null,
  average_exec_price: '50000',
  reduce_only: false,
  client_order_id: 'client-123',
  strategy_name: 'test-strategy',
  signal_id: 'signal-123',
  stop_loss: '48000',
  take_profit: '55000',
  created_at: 1711785660000,
  updated_at: 1711785660000,
  filled_at: 1711785660000,
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
    ): Array<{ node: OrderTreeNode; orderId: string; level: number }> => {
      let result: Array<{ node: OrderTreeNode; orderId: string; level: number }> = [];

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
