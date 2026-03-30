import { useApi } from '../lib/api';
import { formatBeijingTime } from '../lib/utils';
import { Wallet, TrendingUp, TrendingDown, Clock, AlertCircle } from 'lucide-react';
import { cn } from '../lib/utils';

export default function Account() {
  const { data, error } = useApi<any>('/api/account');

  const isLoading = !data && !error;

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-28 bg-white rounded-2xl shadow-sm border border-gray-100" />
          ))}
        </div>
        <div className="h-96 bg-white rounded-2xl shadow-sm border border-gray-100" />
      </div>
    );
  }

  if (data?.status === 'unavailable') {
    return (
      <div className="h-[60vh] flex flex-col items-center justify-center text-gray-400 bg-white rounded-2xl shadow-sm border border-gray-100">
        <AlertCircle className="w-12 h-12 mb-4 opacity-20" />
        <p className="text-lg font-medium text-gray-600">账户数据尚未就绪</p>
        <p className="text-sm mt-2">请稍候，系统正在拉取最新数据...</p>
      </div>
    );
  }

  const positions = data?.positions || [];
  const unPnl = parseFloat(data?.unrealized_pnl || '0');

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">账户概览</h1>
          <p className="text-sm text-gray-500 mt-1">资金状态与当前持仓</p>
        </div>
        {data?.timestamp && (
          <div className="flex items-center gap-1.5 text-xs text-gray-400 bg-white px-3 py-1.5 rounded-full shadow-sm border border-gray-100">
            <Clock className="w-3.5 h-3.5" />
            <span>快照时间：{formatBeijingTime(data.timestamp, 'time')}</span>
          </div>
        )}
      </div>

      {/* Section 1: Account Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 text-gray-500 mb-4">
            <Wallet className="w-4 h-4" />
            <h3 className="text-sm font-medium">总权益 (USDT)</h3>
          </div>
          <div className="text-4xl font-semibold tracking-tight font-mono">
            {parseFloat(data?.total_balance || '0').toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 text-gray-500 mb-4">
            <div className="w-4 h-4 rounded-full border-2 border-gray-400" />
            <h3 className="text-sm font-medium">可用余额 (USDT)</h3>
          </div>
          <div className="text-4xl font-semibold tracking-tight font-mono">
            {parseFloat(data?.available_balance || '0').toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 text-gray-500 mb-4">
            {unPnl >= 0 ? <TrendingUp className="w-4 h-4 text-apple-green" /> : <TrendingDown className="w-4 h-4 text-apple-red" />}
            <h3 className="text-sm font-medium">未实现盈亏 (USDT)</h3>
          </div>
          <div className={cn(
            "text-4xl font-semibold tracking-tight font-mono",
            unPnl > 0 ? "text-apple-green" : unPnl < 0 ? "text-apple-red" : "text-gray-900"
          )}>
            {unPnl > 0 ? '+' : ''}{unPnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {/* Section 2: Positions List */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-5 border-b border-gray-100">
          <h2 className="text-lg font-semibold tracking-tight">当前持仓</h2>
        </div>
        
        {positions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400">
            <Wallet className="w-12 h-12 mb-4 opacity-20" />
            <p>当前无持仓</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-500 bg-gray-50/50 uppercase">
                <tr>
                  <th className="px-6 py-4 font-medium">币种</th>
                  <th className="px-6 py-4 font-medium">方向</th>
                  <th className="px-6 py-4 font-medium text-right">持仓数量</th>
                  <th className="px-6 py-4 font-medium text-right">开仓均价</th>
                  <th className="px-6 py-4 font-medium text-right">未实现盈亏</th>
                  <th className="px-6 py-4 font-medium text-right">杠杆</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {positions.map((pos: any, idx: number) => {
                  const isLong = pos.side === 'long';
                  const symbol = pos.symbol.replace(':USDT', '');
                  const pnl = parseFloat(pos.unrealized_pnl || '0');
                  
                  return (
                    <tr key={idx} className="hover:bg-gray-50/50 transition-colors">
                      <td className="px-6 py-4 font-semibold text-gray-900">{symbol}</td>
                      <td className="px-6 py-4">
                        <span className={cn(
                          "px-2 py-1 rounded text-xs font-medium",
                          isLong ? "bg-apple-green/10 text-apple-green" : "bg-apple-red/10 text-apple-red"
                        )}>
                          {isLong ? '做多' : '做空'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right font-mono text-gray-900">{pos.size}</td>
                      <td className="px-6 py-4 text-right font-mono text-gray-900">{pos.entry_price}</td>
                      <td className={cn(
                        "px-6 py-4 text-right font-mono font-medium",
                        pnl > 0 ? "text-apple-green" : pnl < 0 ? "text-apple-red" : "text-gray-900"
                      )}>
                        {pnl > 0 ? '+' : ''}{pnl.toFixed(2)}
                      </td>
                      <td className="px-6 py-4 text-right text-gray-500">{pos.leverage}x</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
