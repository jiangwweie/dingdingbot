import useSWR from 'swr';
import { RefreshCw, Settings, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { cn } from '../lib/utils';
import { fetcher } from '../lib/api';

// Config response type
interface ExchangeConfig {
  name: string;
  testnet: boolean;
  api_key: string;
}

interface NotificationChannel {
  type: string;
  enabled: boolean;
  webhook_url?: string;
}

interface NotificationConfig {
  channels: NotificationChannel[];
}

interface StrategyFilter {
  type: string;
  enabled: boolean;
}

interface StrategyDefinition {
  name: string;
  enabled: boolean;
  filters: StrategyFilter[];
}

interface RiskConfig {
  max_loss_percent: number;
  max_leverage: number;
  max_total_exposure?: number;
}

interface ConfigData {
  exchange?: ExchangeConfig;
  active_strategies?: StrategyDefinition[];
  risk?: RiskConfig;
  timeframes?: string[];
  mtf_mapping?: Record<string, string>;
  notification?: NotificationConfig;
}

interface ConfigStatusCardProps {
  onOpenSettings?: () => void;
}

export default function ConfigStatusCard({ onOpenSettings }: ConfigStatusCardProps) {
  const [isRefreshing, setIsRefreshing] = useState(false);

  const { data, error, mutate } = useSWR<{ config: ConfigData; status: string }>(
    '/api/config',
    fetcher,
    {
      refreshInterval: 0,
      revalidateOnFocus: true,
      revalidateOnReconnect: true,
    }
  );

  const config = data?.config;
  const isLoading = !data && !error;

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await mutate();
    } finally {
      setIsRefreshing(false);
    }
  };

  // Format API key display (masked)
  const formatApiKey = (apiKey: string) => {
    if (!apiKey || apiKey.length < 8) return '***';
    return `${apiKey.slice(0, 4)}...${apiKey.slice(-4)}`;
  };

  // Get exchange display info
  const exchangeName = config?.exchange?.name || 'N/A';
  const isTestnet = config?.exchange?.testnet ?? false;
  const apiKeyMasked = config?.exchange?.api_key ? formatApiKey(config.exchange.api_key) : '未配置';

  // Get active strategies summary
  const activeStrategies = config?.active_strategies?.filter(s => s.enabled) || [];
  const strategyNames = activeStrategies.map(s => s.name).join(', ') || '无';
  const filtersCount = activeStrategies.reduce((acc, s) => acc + (s.filters?.filter(f => f.enabled).length || 0), 0);

  // Get risk config
  const risk = config?.risk;
  const lossPercent = risk?.max_loss_percent ? `${(risk.max_loss_percent * 100).toFixed(0)}%` : '-';
  const maxLeverage = risk?.max_leverage || '-';
  const maxExposure = risk?.max_total_exposure ? `${(risk.max_total_exposure * 100).toFixed(0)}%` : '-';

  // Get timeframes
  const timeframes = config?.timeframes?.join(', ') || '-';

  // Get MTF mapping display
  const mtfMapping = config?.mtf_mapping || {};
  const mtfDisplay = Object.entries(mtfMapping)
    .map(([k, v]) => `${k}→${v}`)
    .join(', ') || '-';

  // Get notification channels
  const channels = config?.notification?.channels || [];
  const enabledChannels = channels.filter(c => c.enabled);
  const channelNames = enabledChannels.map(c => {
    switch (c.type) {
      case 'feishu':
        return '飞书';
      case 'wechat':
        return '微信';
      case 'telegram':
        return 'Telegram';
      case 'dingtalk':
        return '钉钉';
      default:
        return c.type;
    }
  }).join(', ') || '未配置';

  // Card component
  const InfoCard = ({
    title,
    children,
    className
  }: {
    title: string;
    children: React.ReactNode;
    className?: string;
  }) => (
    <div className={cn(
      "bg-white p-4 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-between",
      className
    )}>
      <div className="flex items-center gap-2 text-gray-500 mb-2">
        <span className="text-xs font-medium uppercase tracking-wider">{title}</span>
      </div>
      <div className="text-sm text-gray-900 leading-relaxed">
        {children}
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 animate-pulse">
        <div className="flex justify-between items-center mb-4">
          <div className="h-5 w-32 bg-gray-200 rounded" />
          <div className="h-8 w-8 bg-gray-200 rounded-lg" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-24 bg-gray-100 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-gray-100 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <Settings className="w-5 h-5 text-gray-500" />
          <div>
            <h2 className="text-lg font-semibold tracking-tight">当前生效配置</h2>
            <p className="text-xs text-gray-400 mt-0.5">系统内存中正在使用的配置</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className={cn(
              "p-2 rounded-lg hover:bg-gray-100 transition-colors",
              isRefreshing && "animate-spin"
            )}
            title="刷新配置"
          >
            <RefreshCw className={cn("w-4 h-4 text-gray-500", isRefreshing && "text-apple-blue")} />
          </button>
          {onOpenSettings && (
            <button
              onClick={onOpenSettings}
              className="text-sm text-apple-blue hover:underline flex items-center gap-1"
            >
              查看详情 <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Cards Grid */}
      <div className="p-5">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Exchange Info */}
          <InfoCard title="交易所">
            <div className="font-semibold text-base">{exchangeName}</div>
            <div className="text-xs text-gray-500 mt-1">
              <span className={cn(
                "inline-flex items-center gap-1 px-2 py-0.5 rounded-full",
                isTestnet ? "bg-apple-orange/10 text-apple-orange" : "bg-apple-green/10 text-apple-green"
              )}>
                {isTestnet ? '测试网' : '实盘'}
              </span>
            </div>
            <div className="text-xs text-gray-400 mt-2 font-mono">{apiKeyMasked}</div>
          </InfoCard>

          {/* Strategy Info */}
          <InfoCard title="策略">
            <div className="font-semibold text-base">{strategyNames || '无激活策略'}</div>
            <div className="text-xs text-gray-500 mt-1">
              {filtersCount > 0 ? (
                <span className="inline-flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-apple-green" />
                  {filtersCount} 个过滤器生效
                </span>
              ) : (
                <span className="text-gray-400">无过滤器</span>
              )}
            </div>
          </InfoCard>

          {/* Risk Info */}
          <InfoCard title="风控">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="font-semibold text-base">{lossPercent}</span>
              <span className="text-gray-400">/</span>
              <span className="font-semibold text-base">{maxLeverage}x</span>
              <span className="text-gray-400">/</span>
              <span className="font-semibold text-base">{maxExposure}</span>
            </div>
            <div className="text-xs text-gray-500 mt-1">
              亏损 / 杠杆 / 总敞口
            </div>
          </InfoCard>

          {/* Timeframes */}
          <InfoCard title="时间周期">
            <div className="flex flex-wrap gap-1">
              {config?.timeframes?.map((tf) => (
                <span
                  key={tf}
                  className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-mono"
                >
                  {tf}
                </span>
              )) || <span className="text-gray-400">未配置</span>}
            </div>
          </InfoCard>

          {/* MTF Mapping */}
          <InfoCard title="MTF 映射">
            <div className="text-sm font-mono text-gray-700">{mtfDisplay}</div>
            <div className="text-xs text-gray-500 mt-1">
              低周期 → 高周期
            </div>
          </InfoCard>

          {/* Notification */}
          <InfoCard title="通知渠道">
            <div className="flex items-center gap-2 flex-wrap">
              {enabledChannels.length > 0 ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-apple-green" />
                  <span className="font-medium text-sm">{channelNames}</span>
                </>
              ) : (
                <span className="text-gray-400">未启用</span>
              )}
            </div>
          </InfoCard>
        </div>
      </div>
    </div>
  );
}
