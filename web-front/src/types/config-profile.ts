/**
 * 配置 Profile（配置档案）类型定义
 *
 * 用于配置 Profile 管理功能，支持多套配置档案的创建、切换、删除等操作
 * 与后端 /api/config/profiles 接口保持类型对齐
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
  description: string | null;
  /** 创建时间（ISO 8601 格式） */
  created_at: string;
  /** 最近更新时间（ISO 8601 格式） */
  updated_at: string;
  /** 配置项数量 */
  config_count: number;
  /** 是否为当前激活的 Profile */
  is_active: boolean;
  /** 创建来源（从哪个 Profile 复制） */
  created_from?: string | null;
}

/**
 * Profile 列表响应
 */
export interface ProfileListResponse {
  /** Profile 列表 */
  profiles: ConfigProfile[];
  /** 当前激活的 Profile 名称 */
  active_profile: string | null;
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
  description?: string | null;
  /** 从中复制配置的源 Profile（可选） */
  copy_from?: string | null;
  /** 创建后是否立即切换 */
  switch_immediately?: boolean;
}

/**
 * 创建 Profile 响应
 */
export interface CreateProfileResponse {
  /** 操作状态 */
  status: string;
  /** 创建的 Profile 信息 */
  profile: ConfigProfile;
  /** 消息 */
  message: string;
}

/**
 * 切换 Profile 响应
 */
export interface SwitchProfileResponse {
  /** 操作状态 */
  status: string;
  /** 切换后的 Profile 信息 */
  profile: ConfigProfile;
  /** 配置差异信息 */
  diff: ProfileDiffResponse;
  /** 消息 */
  message: string;
}

/**
 * Profile 差异对比响应
 */
export interface ProfileDiffResponse {
  /** 源 Profile 名称 */
  from_profile: string;
  /** 目标 Profile 名称 */
  to_profile: string;
  /** 差异详情（按模块分组） */
  diff: {
    [module: string]: {
      [key: string]: {
        old: string;
        new: string;
      };
    };
  };
  /** 差异总数 */
  total_changes: number;
}

/**
 * 删除 Profile 响应
 */
export interface DeleteProfileResponse {
  /** 操作状态 */
  status: string;
  /** 消息 */
  message: string;
}

/**
 * 导出 Profile 响应
 */
export interface ExportProfileResponse {
  /** 操作状态 */
  status: string;
  /** Profile 名称 */
  profile_name: string;
  /** YAML 格式的配置内容 */
  yaml_content: string;
}

/**
 * 导入 Profile 请求
 */
export interface ImportProfileRequest {
  /** YAML 文件内容 */
  yaml_content: string;
  /** 指定 Profile 名称（可选） */
  profile_name?: string | null;
  /** 导入模式：create | overwrite */
  mode: 'create' | 'overwrite';
}

/**
 * 导入 Profile 响应
 */
export interface ImportProfileResponse {
  /** 操作状态 */
  status: string;
  /** 导入的 Profile 信息 */
  profile: ConfigProfile;
  /** 导入的配置项数量 */
  imported_count: number;
  /** 消息 */
  message: string;
}

/**
 * 对比 Profile 响应
 */
export interface CompareProfilesResponse {
  /** 操作状态 */
  status: string;
  /** 源 Profile 名称 */
  from_profile: string;
  /** 目标 Profile 名称 */
  to_profile: string;
  /** 差异详情 */
  diff: ProfileDiffResponse;
}

/**
 * 重命名 Profile 请求
 */
export interface RenameProfileRequest {
  /** 新 Profile 名称 */
  name: string;
  /** 新描述（可选） */
  description?: string | null;
}

/**
 * 重命名 Profile 响应
 */
export interface RenameProfileResponse {
  /** 操作状态 */
  status: string;
  /** 重命名后的 Profile 信息 */
  profile: ConfigProfile;
  /** 消息 */
  message: string;
}
