import { useRef, ReactNode, CSSProperties } from 'react';
import { List, ListProps, ListImperativeAPI } from 'react-window';
import { ChevronRight, ChevronDown, Trash2, AlertCircle } from 'lucide-react';
import { OrderTreeNode, OrderResponse, OrderStatus, OrderRole } from '../../types/order';
import { OrderStatusBadge } from './OrderStatusBadge';
import { OrderRoleBadge } from './OrderRoleBadge';
import { DirectionBadge } from './DirectionBadge';
import { DecimalDisplay } from './DecimalDisplay';
import { format } from 'date-fns';
import { cn } from '../../lib/utils';

interface OrderChainTreeTableProps {
  /** 树形数据 */
  data: OrderTreeNode[];
  /** 展开的行 keys */
  expandedRowKeys: string[];
  /** 展开/折叠回调 */
  onExpand: (keys: string[]) => void;
  /** 选中的行 keys */
  selectedRowKeys: string[];
  /** 选择变化回调 */
  onSelectChange: (keys: string[]) => void;
  /** 取消订单回调 */
  onCancelOrder?: (orderId: string, symbol: string) => Promise<void>;
  /** 删除订单链回调 */
  onDeleteChain?: (orderIds: string[]) => Promise<void>;
  /** 查看详情回调 */
  onViewDetails?: (orderId: string) => void;
  /** 加载状态 */
  isLoading?: boolean;
}

interface FlatOrderTreeNode {
  node: OrderTreeNode;
  orderId: string;
  level: number;
  parent?: OrderTreeNode;
}

/**
 * 将树形数据扁平化为列表（用于虚拟滚动）
 */
function flattenTreeData(
  nodes: OrderTreeNode[],
  expandedRowKeys: string[],
  parent?: OrderTreeNode
): FlatOrderTreeNode[] {
  let result: FlatOrderTreeNode[] = [];

  for (const node of nodes) {
    result.push({
      node,
      orderId: node.order.order_id,
      level: node.level,
      parent,
    });

    // 如果展开且有子节点，递归添加子节点
    if (expandedRowKeys.includes(node.order.order_id) && node.children.length > 0) {
      result = result.concat(flattenTreeData(node.children, expandedRowKeys, node));
    }
  }

  return result;
}

/**
 * 获取订单链的所有订单 ID（包括子订单）
 */
function getOrderChainIds(node: OrderTreeNode): string[] {
  const ids = [node.order.order_id];
  for (const child of node.children) {
    ids.push(...getOrderChainIds(child));
  }
  return ids;
}

/**
 * 订单链树形表格组件
 */
export const OrderChainTreeTable = ({
  data,
  expandedRowKeys,
  selectedRowKeys,
  onExpand,
  onSelectChange,
  onCancelOrder,
  onDeleteChain,
  onViewDetails,  // 新增：查看详情回调
  isLoading = false,
}: OrderChainTreeTableProps) => {
  const listRef = useRef<ListImperativeAPI>(null);

  // 扁平化树形数据
  const flatData = flattenTreeData(data, expandedRowKeys);

  // 处理展开/折叠
  const handleToggleExpand = (orderId: string) => {
    const newKeys = expandedRowKeys.includes(orderId)
      ? expandedRowKeys.filter((key) => key !== orderId)
      : [...expandedRowKeys, orderId];
    onExpand(newKeys);
  };

  // 处理选择变化（选中整个订单链）
  const handleSelectChange = (orderId: string) => {
    // 找到对应的节点
    const findNode = (nodes: OrderTreeNode[]): OrderTreeNode | undefined => {
      for (const node of nodes) {
        if (node.order.order_id === orderId) {
          return node;
        }
        const found = findNode(node.children);
        if (found) return found;
      }
      return undefined;
    };

    const node = findNode(data);
    if (!node) return;

    // 获取整个订单链的所有 ID
    const chainIds = getOrderChainIds(node);
    const isSelected = selectedRowKeys.includes(orderId);

    if (isSelected) {
      // 取消选择：移除整个订单链
      const newKeys = selectedRowKeys.filter((key) => !chainIds.includes(key));
      onSelectChange(newKeys);
    } else {
      // 选择：添加整个订单链（去重）
      const newKeys = [...new Set([...selectedRowKeys, ...chainIds])];
      onSelectChange(newKeys);
    }
  };

  // 处理取消订单
  const handleCancelOrder = async (orderId: string, symbol: string) => {
    if (!onCancelOrder) return;
    try {
      await onCancelOrder(orderId, symbol);
    } catch (error) {
      console.error('Failed to cancel order:', error);
    }
  };

  // 处理删除订单链
  const handleDeleteChain = async (orderId: string) => {
    if (!onDeleteChain) return;
    const findNode = (nodes: OrderTreeNode[]): OrderTreeNode | undefined => {
      for (const node of nodes) {
        if (node.order.order_id === orderId) {
          return node;
        }
        const found = findNode(node.children);
        if (found) return found;
      }
      return undefined;
    };

    const node = findNode(data);
    if (!node) return;

    const chainIds = getOrderChainIds(node);
    try {
      await onDeleteChain(chainIds);
    } catch (error) {
      console.error('Failed to delete order chain:', error);
    }
  };

  // 行组件
  const Row = ({ index, style, data }: { index: number; style: CSSProperties; data: FlatOrderTreeNode[]; "aria-posinset": number; "aria-setsize": number; role: "listitem" }): ReactNode => {
    const item = data[index];
    if (!item) return null;

    const { node, orderId, level } = item;
    const order = node.order;
    const hasChildren = node.children.length > 0;
    const isExpanded = expandedRowKeys.includes(orderId);
    const isSelected = selectedRowKeys.includes(orderId);

    // 处理行点击 - 打开详情
    const handleRowClick = () => {
      if (onViewDetails) {
        onViewDetails(orderId);
      }
    };

    return (
      <div
        style={style}
        onClick={handleRowClick}
        className={cn(
          'flex items-center gap-2 px-4 py-3 border-b border-gray-100 hover:bg-gray-50/50 transition-colors cursor-pointer',
          isSelected && 'bg-blue-50/50'
        )}
      >
        {/* 展开/折叠图标 + 缩进 */}
        <div className="flex items-center gap-1" style={{ paddingLeft: `${level * 24}px` }}>
          {hasChildren ? (
            <button
              onClick={() => handleToggleExpand(orderId)}
              className="p-1 hover:bg-gray-200 rounded transition-colors"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-gray-500" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-500" />
              )}
            </button>
          ) : (
            <div className="w-6" />
          )}
        </div>

        {/* 复选框 */}
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => handleSelectChange(orderId)}
          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          onClick={(e) => e.stopPropagation()}
        />

        {/* 订单 ID */}
        <div className="flex-1 min-w-0">
          <span className="font-mono text-xs text-gray-600">
            {orderId.slice(0, 8)}...{orderId.slice(-4)}
          </span>
        </div>

        {/* 币种 */}
        <div className="w-24">
          <span className="font-semibold text-gray-900">
            {order.symbol.replace(':USDT', '')}
          </span>
        </div>

        {/* 角色 */}
        <div className="w-20">
          <OrderRoleBadge role={order.order_role} />
        </div>

        {/* 方向 */}
        <div className="w-16">
          <DirectionBadge direction={order.direction} />
        </div>

        {/* 数量 */}
        <div className="w-24 text-right">
          <DecimalDisplay value={order.quantity} decimals={4} />
        </div>

        {/* 价格 */}
        <div className="w-28 text-right">
          <DecimalDisplay
            value={order.average_exec_price || order.price || order.trigger_price}
            decimals={2}
          />
        </div>

        {/* 状态 */}
        <div className="w-24">
          <OrderStatusBadge status={order.status} />
        </div>

        {/* 创建时间 */}
        <div className="w-36 text-gray-500 text-xs">
          {format(new Date(order.created_at), 'MM-dd HH:mm:ss')}
        </div>

        {/* 操作 */}
        <div className="w-24 flex items-center gap-2">
          {order.status === OrderStatus.OPEN || order.status === OrderStatus.PARTIALLY_FILLED ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleCancelOrder(orderId, order.symbol);
              }}
              className="text-xs text-orange-600 hover:text-orange-700 hover:underline"
            >
              取消
            </button>
          ) : null}
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleDeleteChain(orderId);
            }}
            className="text-xs text-red-600 hover:text-red-700 hover:underline flex items-center gap-1"
          >
            <Trash2 className="w-3 h-3" />
            删除
          </button>
        </div>
      </div>
    );
  };

  // 加载状态
  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50/50">
          <div className="flex items-center gap-2">
            <div className="w-6" />
            <div className="w-4 h-4 bg-gray-200 rounded" />
            <div className="flex-1 h-4 bg-gray-200 rounded w-20" />
            <div className="w-24 h-4 bg-gray-200 rounded" />
            <div className="w-20 h-4 bg-gray-200 rounded" />
            <div className="w-16 h-4 bg-gray-200 rounded" />
            <div className="w-24 h-4 bg-gray-200 rounded" />
            <div className="w-28 h-4 bg-gray-200 rounded" />
            <div className="w-24 h-4 bg-gray-200 rounded" />
            <div className="w-36 h-4 bg-gray-200 rounded" />
            <div className="w-24 h-4 bg-gray-200 rounded" />
          </div>
        </div>
        {[...Array(10)].map((_, i) => (
          <div key={i} className="px-4 py-3 border-b border-gray-100 animate-pulse">
            <div className="flex items-center gap-2">
              <div className="w-6" />
              <div className="w-4 h-4 bg-gray-200 rounded" />
              <div className="flex-1 h-4 bg-gray-100 rounded w-20" />
              <div className="w-24 h-4 bg-gray-100 rounded" />
              <div className="w-20 h-4 bg-gray-100 rounded" />
              <div className="w-16 h-4 bg-gray-100 rounded" />
              <div className="w-24 h-4 bg-gray-100 rounded" />
              <div className="w-28 h-4 bg-gray-100 rounded" />
              <div className="w-24 h-4 bg-gray-100 rounded" />
              <div className="w-36 h-4 bg-gray-100 rounded" />
              <div className="w-24 h-4 bg-gray-100 rounded" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  // 空状态
  if (data.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-20 text-center text-gray-400">
          <AlertCircle className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>没有找到订单记录</p>
        </div>
      </div>
    );
  }

  // 表头
  const renderHeader = () => (
    <div className="px-4 py-3 border-b border-gray-100 bg-gray-50/50 text-xs text-gray-500 uppercase tracking-wide">
      <div className="flex items-center gap-2">
        <div className="w-6" />
        <div className="w-4" />
        <div className="flex-1 font-medium">订单 ID</div>
        <div className="w-24 font-medium">币种</div>
        <div className="w-20 font-medium">角色</div>
        <div className="w-16 font-medium">方向</div>
        <div className="w-24 font-medium text-right">数量</div>
        <div className="w-28 font-medium text-right">价格</div>
        <div className="w-24 font-medium">状态</div>
        <div className="w-36 font-medium">创建时间</div>
        <div className="w-24 font-medium">操作</div>
      </div>
    </div>
  );

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      {renderHeader()}
      <div className="max-h-[600px] overflow-auto">
        <List
          rowComponent={Row}
          rowProps={{ data: flatData }}
          rowCount={flatData.length}
          rowHeight={52}
          listRef={listRef}
        >
          {null}
        </List>
      </div>
    </div>
  );
};
