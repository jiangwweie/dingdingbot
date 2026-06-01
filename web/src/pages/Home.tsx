import { ChevronDown, ChevronRight, Zap } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

export default function Home() {
  const [showTechDetails, setShowTechDetails] = useState(false);

  return (
    <>
      {/* Current Conclusion */}
      <div className="bg-slate-900 dark:bg-slate-800/80 text-white rounded-xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4 border border-slate-800 dark:border-slate-700">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-5 h-5 rounded-full bg-teal-500/20 text-teal-400 flex items-center justify-center text-xs font-bold border border-teal-500/30">!</div>
            <h2 className="text-lg font-bold text-slate-50">MI-001 SOL 已完成试验前准备，当前因启动保护未预检而阻断，试验未启动。</h2>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm text-slate-300">
            <span className="flex items-center gap-1.5 font-medium"><div className="w-1.5 h-1.5 rounded-full bg-teal-400"></div> 实盘只读</span>
            <span className="text-slate-600">·</span>
            <span className="flex items-center gap-1.5 font-medium"><div className="w-1.5 h-1.5 rounded-full bg-indigo-400"></div> 记录意图</span>
            <span className="text-slate-600">·</span>
            <span className="flex items-center gap-1.5 font-medium"><div className="w-1.5 h-1.5 rounded-full bg-red-400"></div> 禁止下单</span>
          </div>
        </div>
        <button className="bg-white/10 hover:bg-white/20 border border-white/10 text-white px-5 py-2.5 rounded-lg transition-colors text-sm font-medium whitespace-nowrap">
          新建观察
        </button>
      </div>

      {/* 4 Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-sm">
          <h3 className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">系统状态</h3>
          <div className="text-xl font-bold text-slate-900 dark:text-slate-50 mb-1 flex items-center gap-2">
            安全 <div className="w-2 h-2 rounded-full bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.6)]"></div>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-2">禁止下单</p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-sm">
          <h3 className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">账户状态</h3>
          <div className="text-xl font-bold text-slate-900 dark:text-slate-50 mb-1 flex items-center gap-2">
            读取正常 <div className="w-2 h-2 rounded-full bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.6)]"></div>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-2">持仓 0 / 挂单 0</p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-sm">
          <h3 className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">当前策略组</h3>
          <div className="text-xl font-bold text-slate-900 dark:text-slate-50 mb-1">MI-001 SOL</div>
          <div className="mt-2 text-sm text-indigo-700 bg-indigo-50 dark:text-indigo-300 dark:bg-indigo-500/10 inline-block px-2.5 py-0.5 rounded border border-indigo-200 dark:border-indigo-500/20 font-medium">多头观察</div>
        </div>

        <div className="bg-white dark:bg-slate-900 border-l-4 border-l-amber-400 border-y border-y-slate-200 dark:border-y-slate-800 border-r border-r-slate-200 dark:border-r-slate-800 rounded-r-xl rounded-l-sm p-5 shadow-sm">
          <h3 className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">当前阻断</h3>
          <div className="text-xl font-bold text-slate-900 dark:text-slate-50 mb-1">启动保护未预检</div>
          <div className="mt-2 text-sm text-amber-700 bg-amber-50 dark:text-amber-400 dark:bg-amber-500/10 inline-block px-2.5 py-0.5 rounded border border-amber-200 dark:border-amber-500/20 font-medium">试验未启动</div>
        </div>
      </div>

      {/* Account Overview & Intention */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm flex flex-col h-full overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/20">
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">全仓账户概览</h3>
          </div>
          <div className="p-5 grid grid-cols-2 gap-6 flex-grow items-center">
            <div className="space-y-1">
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">总权益</p>
              <p className="text-2xl font-bold text-slate-800 dark:text-white">-- <span className="text-sm font-normal text-slate-400">USDT</span></p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">可用余额</p>
              <p className="text-2xl font-bold text-slate-800 dark:text-white">-- <span className="text-sm font-normal text-slate-400">USDT</span></p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">未实现盈亏</p>
              <p className="text-2xl font-bold text-slate-800 dark:text-white">--</p>
            </div>
            <div className="flex gap-8">
              <div className="space-y-1">
                <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">持仓</p>
                <p className="text-2xl font-bold text-slate-800 dark:text-white">0</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">挂单</p>
                <p className="text-2xl font-bold text-slate-800 dark:text-white">0</p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm flex flex-col h-full overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/20 flex justify-between items-center">
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">最近执行意图</h3>
            <Link to="/intents" className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 font-medium">查看全部</Link>
          </div>
          <div className="p-10 flex flex-col items-center justify-center flex-grow text-center">
            <div className="w-12 h-12 bg-slate-50 dark:bg-slate-800 rounded-full flex items-center justify-center mb-4 border border-slate-200 dark:border-slate-700">
              <Zap className="text-slate-400 dark:text-slate-500" size={24} />
            </div>
            <h4 className="text-slate-800 dark:text-slate-200 font-bold mb-2">暂无新意图</h4>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-5 max-w-xs leading-relaxed">策略还没有产生可记录的意图，或当前仍处于准备阶段。</p>
            <div className="flex space-x-4 text-xs font-medium text-slate-400 dark:text-slate-500">
              <span>最近信号：--</span>
              <span>最近阻断：启动保护</span>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="bg-indigo-50/80 dark:bg-indigo-950/30 border border-indigo-100 dark:border-indigo-900/50 rounded-xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-bold text-indigo-900 dark:text-indigo-300 mb-1">当前可做</h3>
          <p className="text-xs text-indigo-700/80 dark:text-indigo-400/80">您可以继续查看详细信息。当前不可做：启动试验 / 创建执行指令 / 下单。</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link to="/strategy-groups" className="bg-white dark:bg-slate-800 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors shadow-sm">
            查看策略组
          </Link>
          <Link to="/analysis" className="bg-white dark:bg-slate-800 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors shadow-sm">
            查看复盘证据
          </Link>
          <Link to="/trace" className="bg-white dark:bg-slate-800 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors shadow-sm">
            查看链路追踪
          </Link>
        </div>
      </div>

      {/* Tech Details Fold */}
      <div className="mt-2">
        <button
          onClick={() => setShowTechDetails(!showTechDetails)}
          className="flex items-center gap-1.5 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors py-2 px-3 rounded-md hover:bg-slate-200/50 dark:hover:bg-slate-800/50"
        >
          {showTechDetails ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          技术详情
        </button>

        {showTechDetails && (
          <div className="mt-3 bg-slate-900 text-slate-300 p-5 rounded-lg text-[13px] font-mono overflow-x-auto shadow-inner border border-slate-800">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-y-3 gap-x-8">
              <div className="flex flex-col">
                <span className="text-slate-500 text-[11px] uppercase mb-1">技术状态</span>
                <span className="text-amber-400">blocked_startup_guard_runtime_coupled</span>
              </div>
              <div className="flex flex-col">
                <span className="text-slate-500 text-[11px] uppercase mb-1">PG 引用</span>
                <span className="text-slate-200">0f7ac98</span>
              </div>
              <div className="flex flex-col">
                <span className="text-slate-500 text-[11px] uppercase mb-1">试验计划</span>
                <span className="text-slate-200">final_pre_start_review_mi001_sol.md</span>
              </div>
              <div className="flex flex-col">
                <span className="text-slate-500 text-[11px] uppercase mb-1">权限</span>
                <span className="text-teal-400">intent_recording</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
