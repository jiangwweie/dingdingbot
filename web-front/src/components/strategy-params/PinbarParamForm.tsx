import React from 'react';
import { Info } from 'lucide-react';

interface PinbarParams {
  min_wick_ratio: number;
  max_body_ratio: number;
  body_position_tolerance: number;
}

interface PinbarParamFormProps {
  params: PinbarParams;
  onChange: (params: PinbarParams) => void;
  disabled?: boolean;
}

/**
 * Pinbar 形态参数配置表单
 *
 * Pinbar（针 bar）是一种重要的价格形态，特征是长影线和小实体。
 * - 看涨 Pinbar：长下影线，实体在顶部
 * - 看跌 Pinbar：长上影线，实体在底部
 */
export default function PinbarParamForm({ params, onChange, disabled = false }: PinbarParamFormProps) {
  const handleChange = (field: keyof PinbarParams, value: number) => {
    onChange({
      ...params,
      [field]: value,
    });
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-2 h-2 bg-green-500 rounded-full" />
        <h3 className="text-sm font-semibold text-gray-900">Pinbar 形态参数</h3>
        <div className="group relative">
          <Info className="w-4 h-4 text-gray-400 hover:text-gray-600 cursor-help" />
          <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-64 p-3 bg-gray-900 text-white text-xs rounded-lg z-10">
            <p>Pinbar 是一种单 K 线形态，特征是长影线和小实体。</p>
            <p className="mt-1">看涨 Pinbar：长下影线，实体在顶部</p>
            <p>看跌 Pinbar：长上影线，实体在底部</p>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {/* 最小影线比 */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm font-medium text-gray-700">
              最小影线占比
            </label>
            <span className="text-sm text-gray-500">{params.min_wick_ratio.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min="0.3"
            max="0.9"
            step="0.05"
            value={params.min_wick_ratio}
            onChange={(e) => handleChange('min_wick_ratio', parseFloat(e.target.value))}
            disabled={disabled}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>0.3</span>
            <span>0.9</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            影线长度占整个 K 线范围的比例下限
          </p>
        </div>

        {/* 最大实体比 */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm font-medium text-gray-700">
              最大实体占比
            </label>
            <span className="text-sm text-gray-500">{params.max_body_ratio.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min="0.1"
            max="0.5"
            step="0.05"
            value={params.max_body_ratio}
            onChange={(e) => handleChange('max_body_ratio', parseFloat(e.target.value))}
            disabled={disabled}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>0.1</span>
            <span>0.5</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            实体长度占整个 K 线范围的比例上限
          </p>
        </div>

        {/* 实体位置容差 */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm font-medium text-gray-700">
              实体位置容差
            </label>
            <span className="text-sm text-gray-500">{params.body_position_tolerance.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min="0.05"
            max="0.3"
            step="0.05"
            value={params.body_position_tolerance}
            onChange={(e) => handleChange('body_position_tolerance', parseFloat(e.target.value))}
            disabled={disabled}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>0.05</span>
            <span>0.3</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            实体偏离顶部/底部的最大允许距离
          </p>
        </div>
      </div>

      {/* 参数校验提示 */}
      {params.min_wick_ratio + params.max_body_ratio > 1 && (
        <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
          <p className="text-xs text-yellow-700">
            警告：影线比 + 实体比 {'>'} 1，这可能导致检测条件过于宽松
          </p>
        </div>
      )}
    </div>
  );
}
