/**
 * 配置 Profile（配置档案）类型定义
 *
 * 用于配置 Profile 管理功能，支持多套配置档案的创建、切换、删除等操作
 * 与后端 /api/config-profiles 接口保持类型对齐
 */

// ============================================================
// Core Profile Types
// ============================================================

/**
 * 配置 Profile 信息
 */
export interface ConfigProfile {
  /** Profile 名称（唯一标识） */
  name: string;
  /** Profile 描述 */
  description: string;
  /** 创建时间（ISO 8601 格式） */
  created_at: string;
  /** 最近更新时间（ISO 8601 格式） */
  updated_at: string;
  /** 配置项数量 */
  config_count: number;
  /** 是否为当前激活的 Profile */
  is_active: boolean;
  /** 是否为 default Profile（不可删除） */
  is_default?: boolean;
}

/**
 * Profile 列表响应
 */
export interface ProfileListResponse {
  /** Profile 列表 */
  profiles: ConfigProfile[];
  /** 当前激活的 Profile 名称 */
  active_profile: string;
  /** Profile 总数 */
  total: number;
}

/**
 * 创建 Profile 请求
 */
export interface CreateProfileRequest {
  /** 新 Profile 名称 */
  name: string;
  /** Profile 描述（可选） */
  description?: string;
  /** 创建后是否立即切换（可选，默认 false） */
  switch_after_create?: boolean;
}

/**
 * 复制 Profile 请求
 */
export interface CopyProfileRequest {
  /** 源 Profile 名称 */
  from_profile: string;
  /** 新 Profile 名称 */
  name: string;
  /** 新 Profile 描述（可选） */
  description?: string;
}

/**
 * 重命名 Profile 请求
 */
export interface RenameProfileRequest {
  /** 新名称 */
  new_name: string;
  /** 新描述（可选） */
  new_description?: string;
}

/**
 * Profile 差异项
 */
export interface ProfileDiffItem {
  /** 配置项路径（如 "strategy.pinbar.min_wick_ratio"） */
  path: string;
  /** 模块分类 */
  module: 'strategy' | 'risk' | 'exchange' | 'system';
  /** 源值（字符串表示） */
  from_value: string;
  /** 目标值（字符串表示） */
  to_value: string;
}

/**
 * Profile 差异预览响应
 */
export interface ProfileDiff {
  /** 源 Profile 名称 */
  from_profile: string;
  /** 目标 Profile 名称 */
  to_profile: string;
  /** 差异项列表（按模块分组） */
  diffs: ProfileDiffItem[];
  /** 差异项总数 */
  total_diffs: number;
  /** 按模块分组的差异统计 */
  module_stats: {
    strategy: number;
    risk: number;
    exchange: number;
    system: number;
  };
}

/**
 * 导入 Profile 模式
 */
export type ImportMode = 'create' | 'overwrite';

/**
 * 导入 Profile 请求
 */
export interface ImportProfileRequest {
  /** YAML 文件内容 */
  yaml_content: string;
  /** 导入模式 */
  mode: ImportMode;
  /** 目标 Profile 名称（仅在 overwrite 模式下需要） */
  target_profile?: string;
  /** 新 Profile 描述（仅在 create 模式下需要） */
  description?: string;
}

/**
 * 导入 Profile 预览响应
 */
export interface ImportPreviewResponse {
  /** Profile 名称 */
  profile_name: string;
  /** Profile 描述 */
  description: string;
  /** 配置项数量 */
  config_count: number;
  /** 配置详情（扁平化键值对） */
  configs: Record<string, any>;
  /** 是否存在（用于判断是创建还是覆盖） */
  exists: boolean;
}

/**
 * 导出 Profile 响应（YAML 字符串）
 */
export interface ProfileExportResponse {
  /** YAML 格式的配置内容 */
  yaml_content: string;
  /** 文件名建议 */
  filename: string;
}

// ============================================================
// API Response Types
// ============================================================

/**
 * 切换 Profile 响应
 */
export interface SwitchProfileResponse {
  /** 切换后的 Profile 名称 */
  active_profile: string;
  /** 切换是否成功 */
  success: boolean;
  /** 消息 */
  message: string;
}

/**
 * 删除 Profile 响应
 */
export interface DeleteProfileResponse {
  /** 删除的 Profile 名称 */
  deleted_profile: string;
  /** 删除是否成功 */
  success: boolean;
  /** 消息 */
  message: string;
}

/**
 * 通用操作响应
 */
export interface ProfileOperationResponse {
  /** 操作是否成功 */
  success: boolean;
  /** 消息 */
  message: string;
}
