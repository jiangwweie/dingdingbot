import React from 'react';
import { LogicNode, AndNode, OrNode, NotNode, LeafNode } from '../types/strategy';
import { ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils';

interface LogicGateControlProps {
  node: AndNode | OrNode | NotNode;
  onChange?: (node: LogicNode) => void;
  readOnly?: boolean;
  depth?: number;
  onAddChild?: (gateType: 'AND' | 'OR' | 'NOT') => void;
  onRemoveChild?: (index: number) => void;
  children?: React.ReactNode;
}

/**
 * 逻辑门控制组件
 *
 * 显示 AND/OR/NOT 逻辑门容器，支持：
 * - 展开/折叠子节点
 * - 添加子节点菜单
 * - 删除子节点
 * - 视觉层次（虚线边框、缩进）
 */
export default function LogicGateControl({
  node,
  onChange,
  readOnly = false,
  depth = 0,
  onAddChild,
  onRemoveChild,
  children,
}: LogicGateControlProps) {
  const [isExpanded, setIsExpanded] = React.useState(true);

  const gateColors = {
    AND: 'bg-blue-50 border-blue-200 text-blue-700',
    OR: 'bg-green-50 border-green-200 text-green-700',
    NOT: 'bg-red-50 border-red-200 text-red-700',
  };

  const gateLabels = {
    AND: 'AND (与)',
    OR: 'OR (或)',
    NOT: 'NOT (非)',
  };

  const borderColor = {
    AND: 'border-blue-300',
    OR: 'border-green-300',
    NOT: 'border-red-300',
  };

  return (
    <div
      className={cn(
        'rounded-lg border-2 p-3 mb-3 transition-all',
        borderColor[node.gate],
        depth > 0 && 'ml-4'
      )}
      style={{
        borderStyle: 'dashed',
      }}
    >
      {/* Gate Header */}
      <div className="flex items-center gap-2 mb-2">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1 hover:bg-gray-100 rounded transition-colors"
          disabled={readOnly}
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </button>

        <span
          className={cn(
            'px-2 py-1 rounded text-xs font-semibold',
            gateColors[node.gate]
          )}
        >
          {gateLabels[node.gate]}
        </span>

        <span className="text-xs text-gray-500">
          {node.children.length} 个子节点
        </span>

        {/* Depth indicator */}
        {depth > 0 && (
          <span className="text-xs text-gray-400 ml-auto">
            深度：{depth}
          </span>
        )}
      </div>

      {/* Children Container */}
      {isExpanded && (
        <div className="space-y-2">
          {children}

          {/* Add Child Button */}
          {!readOnly && onAddChild && (
            <div className="mt-2 flex gap-2">
              <button
                onClick={() => onAddChild('AND')}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors"
              >
                <Plus className="w-3 h-3" />
                AND
              </button>
              <button
                onClick={() => onAddChild('OR')}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200 transition-colors"
              >
                <Plus className="w-3 h-3" />
                OR
              </button>
              <button
                onClick={() => onAddChild('NOT')}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors"
              >
                <Plus className="w-3 h-3" />
                NOT
              </button>
            </div>
          )}
        </div>
      )}

      {!isExpanded && (
        <div className="text-xs text-gray-400 italic pl-8">
          已折叠 {node.children.length} 个子节点
        </div>
      )}
    </div>
  );
}
