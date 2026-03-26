/**
 * 递归逻辑树类型定义
 *
 * 用于定义动态策略引擎的递归逻辑结构，支持：
 * - AND/OR/NOT 逻辑门
 * - Trigger 和 Filter 叶子节点
 * - 嵌套深度限制 ≤ 3
 *
 * 与后端 src/domain/logic_tree.py 保持类型对齐
 */

// ============================================================
// Trigger and Filter Config Types
// ============================================================

export type FilterType =
  | "ema"
  | "ema_trend"
  | "mtf"
  | "atr"
  | "volume_surge"
  | "volatility_filter"
  | "time_filter"
  | "price_action";

export interface FilterConfig {
  id: string;
  type: FilterType;
  enabled?: boolean;
  params: Record<string, unknown>;
}

export type TriggerType = "pinbar" | "engulfing" | "doji" | "hammer";

export interface TriggerConfig {
  id: string;
  type: TriggerType;
  enabled?: boolean;
  params: Record<string, unknown>;
}

// ============================================================
// Leaf Node Types
// ============================================================

export interface TriggerLeaf {
  type: "trigger";
  id: string;
  config: TriggerConfig;
}

export interface FilterLeaf {
  type: "filter";
  id: string;
  config: FilterConfig;
}

/**
 * 叶子节点联合类型
 * 使用 discriminator field "type" 进行类型区分
 */
export type LeafNode = TriggerLeaf | FilterLeaf;

// ============================================================
// Recursive Logic Node Types
// ============================================================

/**
 * AND 逻辑门节点
 */
export interface AndNode {
  gate: "AND";
  children: LogicNodeChildren;
}

/**
 * OR 逻辑门节点
 */
export interface OrNode {
  gate: "OR";
  children: LogicNodeChildren;
}

/**
 * NOT 逻辑门节点
 */
export interface NotNode {
  gate: "NOT";
  children: LogicNodeChildren;
}

/**
 * 逻辑节点联合类型（内部节点）
 */
export type LogicNodeUnion = AndNode | OrNode | NotNode;

/**
 * 逻辑节点子节点类型
 * 支持递归：子节点可以是 LogicNode 或 LeafNode
 */
export type LogicNodeChildren = Array<LogicNode | LeafNode>;

/**
 * 递归逻辑节点类型
 *
 * 支持 AND/OR/NOT 逻辑门，子节点可以是：
 * - 其他 LogicNode（内部节点）
 * - LeafNode（TriggerLeaf 或 FilterLeaf）
 *
 * 嵌套深度限制为 ≤ 3
 */
export type LogicNode = AndNode | OrNode | NotNode;

// ============================================================
// Strategy Definition
// ============================================================

/**
 * 策略定义
 *
 * 使用递归逻辑树定义动态策略的触发器和过滤器组合
 */
export interface StrategyDefinition {
  id: string;
  name: string;
  /** 策略根节点（递归逻辑树） */
  root: LogicNode;
  /** 作用域，如 ["BTC/USDT:USDT:15m"] */
  apply_to: string[];
}

// ============================================================
// Type Guards
// ============================================================

/**
 * 判断是否为叶子节点
 */
export function isLeafNode(node: LogicNode | LeafNode): node is LeafNode {
  return node.type === "trigger" || node.type === "filter";
}

/**
 * 判断是否为 Trigger 叶子节点
 */
export function isTriggerLeaf(node: LogicNode | LeafNode): node is TriggerLeaf {
  return node.type === "trigger";
}

/**
 * 判断是否为 Filter 叶子节点
 */
export function isFilterLeaf(node: LogicNode | LeafNode): node is FilterLeaf {
  return node.type === "filter";
}

/**
 * 判断是否为 AND 节点
 */
export function isAndNode(node: LogicNode | LeafNode): node is AndNode {
  return !isLeafNode(node) && node.gate === "AND";
}

/**
 * 判断是否为 OR 节点
 */
export function isOrNode(node: LogicNode | LeafNode): node is OrNode {
  return !isLeafNode(node) && node.gate === "OR";
}

/**
 * 判断是否为 NOT 节点
 */
export function isNotNode(node: LogicNode | LeafNode): node is NotNode {
  return !isLeafNode(node) && node.gate === "NOT";
}

// ============================================================
// Helper Functions
// ============================================================

/**
 * 创建 Trigger 叶子节点
 */
export function createTriggerLeaf(config: TriggerConfig): TriggerLeaf {
  return {
    type: "trigger",
    id: config.id,
    config,
  };
}

/**
 * 创建 Filter 叶子节点
 */
export function createFilterLeaf(config: FilterConfig): FilterLeaf {
  return {
    type: "filter",
    id: config.id,
    config,
  };
}

/**
 * 创建 AND 逻辑节点
 */
export function createAndNode(...children: Array<LogicNode | LeafNode>): AndNode {
  return {
    gate: "AND",
    children,
  };
}

/**
 * 创建 OR 逻辑节点
 */
export function createOrNode(...children: Array<LogicNode | LeafNode>): OrNode {
  return {
    gate: "OR",
    children,
  };
}

/**
 * 创建 NOT 逻辑节点
 */
export function createNotNode(child: LogicNode | LeafNode): NotNode {
  return {
    gate: "NOT",
    children: [child],
  };
}

/**
 * 计算 LogicNode 的深度
 *
 * 深度计算规则：
 * - 根节点深度为 1
 * - 每增加一层子 LogicNode，深度 +1
 * - LeafNode 不增加深度
 */
export function calculateDepth(node: LogicNode | LeafNode): number {
  if (isLeafNode(node)) {
    return 0;
  }

  if (node.children.length === 0) {
    return 1;
  }

  let maxChildDepth = 0;
  for (const child of node.children) {
    const childDepth = calculateDepth(child);
    maxChildDepth = Math.max(maxChildDepth, childDepth);
  }

  return 1 + maxChildDepth;
}

/**
 * 验证 LogicNode 嵌套深度不超过限制
 *
 * @param node - 要验证的逻辑节点
 * @param maxDepth - 最大允许深度（默认 3）
 * @returns 验证结果
 */
export function validateDepth(
  node: LogicNode,
  maxDepth: number = 3
): { valid: boolean; depth: number } {
  const depth = calculateDepth(node);
  return {
    valid: depth <= maxDepth,
    depth,
  };
}
