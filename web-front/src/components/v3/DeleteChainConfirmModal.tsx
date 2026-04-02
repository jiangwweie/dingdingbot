import { FC, useEffect, useMemo } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { OrderTreeNode, OrderStatus } from '../../types/order';
import { cn } from '../../lib/utils';

interface DeleteChainConfirmModalProps {
  /** 选中的订单 ID 列表 */
  selectedOrderIds: string[];
  /** 树形数据（用于计算订单链详情） */
  treeData: OrderTreeNode[];
  /** 确认删除回调 */
  onConfirm: () => Promise<void>;
  /** 取消回调 */
  onCancel: () => void;
  /** 是否显示 */
  isOpen: boolean;
}

/**
 * 获取订单链的所有订单 ID
 */
function getOrderChainIds(node: OrderTreeNode): string[] {
  const ids = [node.order.order_id];
  for (const child of node.children) {
    ids.push(...getOrderChainIds(child));
  }
  return ids;
}

/**
 * 根据订单 ID 查找节点
 */
function findNodeById(nodes: OrderTreeNode[], orderId: string): OrderTreeNode | null {
  for (const node of nodes) {
    if (node.order.order_id === orderId) {
      return node;
    }
    const found = findNodeById(node.children, orderId);
    if (found) return found;
  }
  return null;
}

/**
 * 删除订单链确认弹窗
 */
export const DeleteChainConfirmModal: FC<DeleteChainConfirmModalProps> = ({
  selectedOrderIds,
  treeData,
  onConfirm,
  onCancel,
  isOpen,
}) => {
  // 计算订单链信息
  const chainInfo = useMemo(() => {
    if (!isOpen) return null;

    // 找出所有选中的根订单（ENTRY 订单）
    const rootOrderIds = new Set<string>();
    const allChainOrderIds = new Set<string>();

    // 遍历选中的订单 ID，找到它们所属的订单链
    selectedOrderIds.forEach((orderId) => {
      // 尝试找到这个订单所在的订单链的根节点
      const findRootOrder = (nodes: OrderTreeNode[], parentId: string | null = null): string | null => {
        for (const node of nodes) {
          if (node.order.order_id === orderId) {
            return parentId || orderId;
          }
          const found = findRootOrder(node.children, node.order.order_id);
          if (found) return found;
        }
        return null;
      };

      const rootId = findRootOrder(treeData);
      if (rootId) {
        rootOrderIds.add(rootId);
      }
    });

    // 收集所有订单链的订单
    rootOrderIds.forEach((rootId) => {
      const node = findNodeById(treeData, rootId);
      if (node) {
        const chainIds = getOrderChainIds(node);
        chainIds.forEach((id) => allChainOrderIds.add(id));
      }
    });

    // 统计挂单中的订单数量
    let openOrdersCount = 0;
    allChainOrderIds.forEach((orderId) => {
      const node = findNodeById(treeData, orderId);
      if (node && (node.order.status === OrderStatus.OPEN || node.order.status === OrderStatus.PARTIALLY_FILLED)) {
        openOrdersCount++;
      }
    });

    return {
      chainCount: rootOrderIds.size,
      totalOrders: allChainOrderIds.size,
      openOrdersCount,
    };
  }, [selectedOrderIds, treeData, isOpen]);

  // 处理确认
  const handleConfirm = async () => {
    try {
      await onConfirm();
    } catch (error) {
      console.error('Delete failed:', error);
    }
  };

  if (!isOpen || !chainInfo) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity"
        onClick={onCancel}
      />

      {/* 弹窗内容 */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden animate-in fade-in zoom-in duration-200">
        {/* 关闭按钮 */}
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* 头部 */}
        <div className="px-6 py-6 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-6 h-6 text-red-600" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900">
                删除订单链确认
              </h3>
              <p className="text-sm text-gray-500 mt-0.5">
                此操作不可逆，请谨慎操作
              </p>
            </div>
          </div>
        </div>

        {/* 内容 */}
        <div className="px-6 py-4">
          <div className="bg-gray-50 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">订单链数量</span>
              <span className="text-sm font-semibold text-gray-900">
                {chainInfo.chainCount} 个
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">预计删除订单总数</span>
              <span className="text-sm font-semibold text-gray-900">
                {chainInfo.totalOrders} 个
              </span>
            </div>
            {chainInfo.openOrdersCount > 0 && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">挂单中的订单</span>
                <span className="text-sm font-semibold text-orange-600">
                  {chainInfo.openOrdersCount} 个
                </span>
              </div>
            )}
          </div>

          <div className="mt-4 p-4 bg-amber-50 rounded-xl border border-amber-100">
            <p className="text-sm text-amber-800">
              <span className="font-medium">此操作将：</span>
            </p>
            <ul className="mt-2 space-y-1 text-sm text-amber-700">
              <li className="flex items-start gap-2">
                <span className="text-amber-600 mt-0.5">•</span>
                <span>取消 {chainInfo.openOrdersCount} 个挂单中的订单 (OPEN/PARTIALLY_FILLED 状态)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-amber-600 mt-0.5">•</span>
                <span>删除所有已终态的订单 (FILLED/CANCELED 等)</span>
              </li>
            </ul>
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex items-center justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleConfirm}
            className={cn(
              'px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors',
              'bg-red-600 hover:bg-red-700'
            )}
          >
            确认删除
          </button>
        </div>
      </div>
    </div>
  );
};
