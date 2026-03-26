import React from 'react';
import { TraceNode } from '../lib/api';
import { CheckCircle, XCircle, ChevronDown, ChevronRight, GitBranch } from 'lucide-react';
import { cn } from '../lib/utils';

interface TraceTreeViewerProps {
  traceTree: TraceNode;
  signalFired: boolean;
}

interface TraceNodeItemProps {
  node: TraceNode;
  depth?: number;
}

/**
 * Trace 树节点渲染组件
 */
function TraceNodeItem({ node, depth = 0 }: TraceNodeItemProps) {
  const [isExpanded, setIsExpanded] = React.useState(true);
  const hasChildren = node.children && node.children.length > 0;

  // 节点状态图标和颜色
  const statusIcon = node.passed ? (
    <CheckCircle className="w-4 h-4 text-green-600" />
  ) : (
    <XCircle className="w-4 h-4 text-red-600" />
  );

  const borderColor = node.passed ? 'border-green-200' : 'border-red-200';
  const bgColor = node.passed ? 'bg-green-50' : 'bg-red-50';

  // 节点类型标签
  const nodeTypeLabels: Record<string, string> = {
    gate: '逻辑门',
    trigger: '触发器',
    filter: '过滤器',
  };

  const gateTypeLabels: Record<string, string> = {
    AND: 'AND',
    OR: 'OR',
    NOT: 'NOT',
  };

  const triggerTypeLabels: Record<string, string> = {
    pinbar: 'Pinbar',
    engulfing: 'Engulfing',
    doji: 'Doji',
    hammer: 'Hammer',
  };

  const filterTypeLabels: Record<string, string> = {
    ema: 'EMA',
    ema_trend: 'EMA',
    mtf: 'MTF',
    atr: 'ATR',
    volume_surge: '成交量',
    volatility_filter: '波动率',
    time_filter: '时间',
    price_action: '价格',
  };

  const getNodeTypeLabel = () => {
    if (node.node_type === 'gate') {
      return node.gate_type ? gateTypeLabels[node.gate_type] || node.gate_type : '逻辑门';
    }
    if (node.node_type === 'trigger') {
      return triggerTypeLabels[node.trigger_type!] || node.trigger_type;
    }
    if (node.node_type === 'filter') {
      return filterTypeLabels[node.filter_type!] || node.filter_type;
    }
    return nodeTypeLabels[node.node_type] || node.node_type;
  };

  return (
    <div className={cn('border-l-2 pl-4 ml-2', borderColor)}>
      {/* Node Header */}
      <div
        className={cn(
          'flex items-center gap-2 p-2 rounded-lg mb-2 cursor-pointer transition-colors',
          bgColor,
          borderColor,
          'border'
        )}
        onClick={() => hasChildren && setIsExpanded(!isExpanded)}
      >
        {/* Expand/Collapse */}
        {hasChildren ? (
          <button className="p-1 hover:bg-white/50 rounded">
            {isExpanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
          </button>
        ) : (
          <GitBranch className="w-3 h-3 text-gray-400" />
        )}

        {/* Status Icon */}
        {statusIcon}

        {/* Node Info */}
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-900">
              {getNodeTypeLabel()}
            </span>
            <span
              className={cn(
                'px-1.5 py-0.5 rounded text-xs font-semibold',
                node.passed
                  ? 'bg-green-200 text-green-800'
                  : 'bg-red-200 text-red-800'
              )}
            >
              {node.passed ? '通过' : '失败'}
            </span>
          </div>

          {/* Node Details */}
          {node.reason && (
            <p className="text-xs text-gray-600 mt-1">{node.reason}</p>
          )}
        </div>

        {/* Depth indicator */}
        {depth > 0 && (
          <span className="text-xs text-gray-400">层级：{depth}</span>
        )}
      </div>

      {/* Children */}
      {isExpanded && hasChildren && (
        <div className="space-y-1">
          {node.children!.map((child, index) => (
            <TraceNodeItem key={child.node_id || `child-${index}`} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Trace 树可视化组件
 *
 * 显示策略预览的评估结果树，包含：
 * - 每个节点的通过/失败状态
 * - 递归展开/折叠
 * - 视觉层次清晰
 */
export default function TraceTreeViewer({ traceTree, signalFired }: TraceTreeViewerProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">评估结果追踪</h3>
        <div
          className={cn(
            'px-3 py-1.5 rounded-full text-sm font-semibold',
            signalFired
              ? 'bg-green-100 text-green-800'
              : 'bg-red-100 text-red-800'
          )}
        >
          {signalFired ? '信号触发' : '信号未触发'}
        </div>
      </div>

      {/* Trace Tree */}
      <div className="space-y-2">
        <TraceNodeItem node={traceTree} depth={0} />
      </div>

      {/* Legend */}
      <div className="mt-4 pt-4 border-t border-gray-200">
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <div className="flex items-center gap-1">
            <CheckCircle className="w-3 h-3 text-green-600" />
            <span>通过</span>
          </div>
          <div className="flex items-center gap-1">
            <XCircle className="w-3 h-3 text-red-600" />
            <span>失败</span>
          </div>
        </div>
      </div>
    </div>
  );
}
