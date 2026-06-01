import { ChevronDown, ChevronRight, Info } from "lucide-react";
import { useState } from "react";

export default function AccountOrders() {
  const [showDataSource, setShowDataSource] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      <div className="bg-slate-900 border border-slate-800 text-white rounded-xl p-5 shadow-sm">
        <h2 className="text-lg font-bold mb-1">账户订单</h2>
        <p className="text-sm text-slate-400">当前只读取账户信息，不提供交易操作，禁止下单。</p>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm p-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 md:gap-8 overflow-hidden">
          <div className="space-y-1 relative md:after:content-[''] md:after:absolute md:after:right-[-16px] md:after:top-2 md:after:bottom-2 md:after:w-px md:after:bg-slate-100 dark:md:after:bg-slate-800">
            <p className="text-[13px] text-slate-500 dark:text-slate-400 font-medium">总权益</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-slate-50">-- <span className="text-sm font-normal text-slate-500 dark:text-slate-400">USDT</span></p>
          </div>
          <div className="space-y-1 relative md:after:content-[''] md:after:absolute md:after:right-[-16px] md:after:top-2 md:after:bottom-2 md:after:w-px md:after:bg-slate-100 dark:md:after:bg-slate-800">
            <p className="text-[13px] text-slate-500 dark:text-slate-400 font-medium">可用余额</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-slate-50">-- <span className="text-sm font-normal text-slate-500 dark:text-slate-400">USDT</span></p>
          </div>
          <div className="space-y-1 relative md:after:content-[''] md:after:absolute md:after:right-[-16px] md:after:top-2 md:after:bottom-2 md:after:w-px md:after:bg-slate-100 dark:md:after:bg-slate-800">
            <p className="text-[13px] text-slate-500 dark:text-slate-400 font-medium">保证金占用</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-slate-50">-- <span className="text-sm font-normal text-slate-500 dark:text-slate-400">USDT</span></p>
          </div>
          <div className="space-y-1 flex flex-col">
            <p className="text-[13px] text-slate-500 dark:text-slate-400 font-medium">未实现盈亏</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-slate-50">-- <span className="text-sm font-normal text-slate-500 dark:text-slate-400">USDT</span></p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[160px]">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/20">
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">持仓</h3>
          </div>
          <div className="p-6 flex flex-col items-center justify-center flex-grow text-slate-500 dark:text-slate-400 text-sm">
            <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-2">
              <Info size={16} />
            </div>
            暂无持仓
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[160px]">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/20">
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">挂单</h3>
          </div>
          <div className="p-6 flex flex-col items-center justify-center flex-grow text-slate-500 dark:text-slate-400 text-sm">
            <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-2">
              <Info size={16} />
            </div>
            暂无挂单
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm p-6 overflow-hidden">
        <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 mb-2">异常敞口</h3>
        <div className="flex items-center gap-2 text-sm text-teal-600 dark:text-teal-400 bg-teal-50 dark:bg-teal-500/10 px-4 py-3 rounded-md border border-teal-100 dark:border-teal-900/50">
          <div className="w-2 h-2 rounded-full bg-teal-500 flex-shrink-0"></div>
          未发现异常敞口。
        </div>
      </div>

      {/* Tech Details Fold */}
      <div className="mt-2 text-sm">
        <button
          onClick={() => setShowDataSource(!showDataSource)}
          className="flex items-center gap-1.5 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors py-2 px-3 rounded-md hover:bg-slate-200/50 dark:hover:bg-slate-800/50"
        >
          {showDataSource ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          数据来源详情
        </button>

        {showDataSource && (
          <div className="mt-2 bg-slate-900 text-slate-300 p-5 rounded-lg text-[13px] font-mono overflow-x-auto shadow-inner border border-slate-800">
            <div className="flex flex-col gap-2">
              <div><span className="text-slate-500">source:</span> <span className="text-slate-200">exchange_read</span></div>
              <div><span className="text-slate-500">truth_level:</span> <span className="text-slate-200">reconciled</span></div>
              <div><span className="text-slate-500">reconciliation:</span> <span className="text-teal-400">clean</span></div>
              <div><span className="text-slate-500">unknown exposure:</span> <span>0</span></div>
            </div>
          </div>
        )}
      </div>

    </div>
  );
}
