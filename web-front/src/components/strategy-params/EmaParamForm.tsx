import React from 'react';
import { Info, TrendingUp, TrendingDown } from 'lucide-react';

interface EmaParams {
  period: number;
  trend_direction?: 'bullish' | 'bearish' | 'either';
}

interface MtfParams {
  require_confirmation: boolean;
}

interface EmaParamFormProps {
  emaParams: EmaParams;
  mtfParams: MtfParams;
  onChange: (params: { ema?: EmaParams; mtf?: MtfParams }) => void;
  disabled?: boolean;
}

/**
 * EMA 趋势过滤器参数配置
 */
export default function EmaParamForm({ emaParams, mtfParams, onChange, disabled = false }: EmaParamFormProps) {
  // 类型转换：确保参数为 number 类型（后端可能返回字符串）
  const safeEmaParams = {
    period: Number(emaParams.period) || 60,
    trend_direction: emaParams.trend_direction as 'bullish' | 'bearish' | 'either' | undefined,
  };

  const safeMtfParams = {
    require_confirmation: Boolean(mtfParams.require_confirmation),
  };

  const handleEmaChange = (field: keyof EmaParams, value: number | 'bullish' | 'bearish' | 'either') => {
    onChange({
      ema: {
        ...emaParams,
        [field]: value,
      },
    });
  };

  const handleMtfChange = (field: keyof MtfParams, value: boolean) => {
    onChange({
      mtf: {
        ...mtfParams,
        [field]: value,
      },
    });
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-2 h-2 bg-blue-500 rounded-full" />
        <h3 className="text-sm font-semibold text-gray-900">EMA 趋势过滤器</h3>
        <div className="group relative">
          <Info className="w-4 h-4 text-gray-400 hover:text-gray-600 cursor-help" />
          <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-72 p-3 bg-gray-900 text-white text-xs rounded-lg z-10">
            <p>EMA（指数移动平均线）用于识别趋势方向。</p>
            <p className="mt-1">价格 &gt; EMA 为上升趋势，价格 &lt; EMA 为下降趋势。</p>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {/* EMA 周期 */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm font-medium text-gray-700">
              EMA 周期
            </label>
            <span className="text-sm font-mono text-gray-600">{safeEmaParams.period}</span>
          </div>
          <input
            type="range"
            min="10"
            max="200"
            step="5"
            value={safeEmaParams.period}
            onChange={(e) => handleEmaChange('period', parseInt(e.target.value))}
            disabled={disabled}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>10</span>
            <span>100</span>
            <span>200</span>
          </div>
          <div className="flex gap-2 mt-2">
            {[20, 50, 60, 100, 200].map((p) => (
              <button
                key={p}
                onClick={() => handleEmaChange('period', p)}
                disabled={disabled}
                className={`px-2 py-1 text-xs rounded transition ${
                  safeEmaParams.period === p
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                } disabled:opacity-50`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* 趋势方向要求 */}
        <div>
          <label className="text-sm font-medium text-gray-700 block mb-2">
            趋势方向要求
          </label>
          <div className="grid grid-cols-3 gap-2">
            <button
              onClick={() => handleEmaChange('trend_direction', 'either')}
              disabled={disabled}
              className={`px-3 py-2 text-sm rounded-lg border transition flex items-center justify-center gap-2 ${
                safeEmaParams.trend_direction === 'either'
                  ? 'bg-gray-100 border-gray-300 text-gray-900'
                  : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'
              } disabled:opacity-50`}
            >
              <span>任意方向</span>
            </button>
            <button
              onClick={() => handleEmaChange('trend_direction', 'bullish')}
              disabled={disabled}
              className={`px-3 py-2 text-sm rounded-lg border transition flex items-center justify-center gap-2 ${
                safeEmaParams.trend_direction === 'bullish'
                  ? 'bg-green-50 border-green-300 text-green-700'
                  : 'bg-white border-gray-200 text-gray-600 hover:border-green-300'
              } disabled:opacity-50`}
            >
              <TrendingUp className="w-4 h-4" />
              <span>仅做多</span>
            </button>
            <button
              onClick={() => handleEmaChange('trend_direction', 'bearish')}
              disabled={disabled}
              className={`px-3 py-2 text-sm rounded-lg border transition flex items-center justify-center gap-2 ${
                safeEmaParams.trend_direction === 'bearish'
                  ? 'bg-red-50 border-red-300 text-red-700'
                  : 'bg-white border-gray-200 text-gray-600 hover:border-red-300'
              } disabled:opacity-50`}
            >
              <TrendingDown className="w-4 h-4" />
              <span>仅做空</span>
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            选择是否要求特定趋势方向才允许开仓
          </p>
        </div>

        {/* MTF 多周期验证 */}
        <div className="border-t border-gray-100 pt-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-purple-500 rounded-full" />
              <label className="text-sm font-medium text-gray-700">
                MTF 多周期验证
              </label>
            </div>
            <button
              onClick={() => handleMtfChange('require_confirmation', !safeMtfParams.require_confirmation)}
              disabled={disabled}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                safeMtfParams.require_confirmation ? 'bg-purple-500' : 'bg-gray-200'
              } disabled:opacity-50`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  safeMtfParams.require_confirmation ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
          <p className="text-xs text-gray-500">
            {safeMtfParams.require_confirmation
              ? '启用：需要更高时间周期确认（15m→1h, 1h→4h, 4h→1d）'
              : '禁用：仅当前周期信号即可触发'}
          </p>
        </div>
      </div>
    </div>
  );
}
