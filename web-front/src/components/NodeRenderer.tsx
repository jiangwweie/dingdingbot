import React from 'react';
import {
  LogicNode,
  LogicNodeChildren,
  LeafNode,
  isAndNode,
  isOrNode,
  isNotNode,
  isLeafNode,
  isTriggerLeaf,
  isFilterLeaf,
} from '../types/strategy';
import { TriggerConfig, FilterConfig } from '../lib/api';
import LogicGateControl from './LogicGateControl';
import LeafNodeForm from './LeafNodeForm';

interface NodeRendererProps {
  node: LogicNode | LeafNode;
  onChange?: (node: LogicNode | LeafNode) => void;
  readOnly?: boolean;
  depth?: number;
  onAddChild?: (gateType: 'AND' | 'OR' | 'NOT') => void;
  onRemoveChild?: (index: number) => void;
  onUpdateTrigger?: (config: TriggerConfig) => void;
  onUpdateFilter?: (config: FilterConfig) => void;
}

/**
 * 递归渲染逻辑节点
 *
 * 支持：
 * - AND/OR/NOT 逻辑门节点
 * - Trigger/Filter 叶子节点
 * - 递归子节点渲染
 */
export default function NodeRenderer({
  node,
  onChange,
  readOnly = false,
  depth = 0,
  onAddChild,
  onRemoveChild,
  onUpdateTrigger,
  onUpdateFilter,
}: NodeRendererProps) {
  // 渲染叶子节点
  if (isLeafNode(node)) {
    return (
      <LeafNodeForm
        node={node}
        onChange={onChange}
        readOnly={readOnly}
        onUpdateTrigger={onUpdateTrigger}
        onUpdateFilter={onUpdateFilter}
      />
    );
  }

  // 渲染逻辑门节点
  if (isAndNode(node) || isOrNode(node) || isNotNode(node)) {
    return (
      <LogicGateControl
        node={node}
        onChange={onChange}
        readOnly={readOnly}
        depth={depth}
        onAddChild={onAddChild}
        onRemoveChild={onRemoveChild}
      >
        {node.children.map((child, index) => (
          <div key={('id' in child ? child.id : undefined) || `child-${index}`} className="ml-4 border-l-2 border-gray-200 pl-4">
            <NodeRenderer
              node={child}
              onChange={(newNode) => {
                if (!onChange) return;
                const newChildren = [...node.children];
                newChildren[index] = newNode;
                onChange({ ...node, children: newChildren });
              }}
              readOnly={readOnly}
              depth={depth + 1}
              onAddChild={onAddChild}
              onRemoveChild={onRemoveChild}
              onUpdateTrigger={onUpdateTrigger}
              onUpdateFilter={onUpdateFilter}
            />
          </div>
        ))}
      </LogicGateControl>
    );
  }

  return null;
}
