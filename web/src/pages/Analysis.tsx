import { CheckCircle2, AlertCircle } from "lucide-react";
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

export default function Analysis() {
  const [showTechDetails, setShowTechDetails] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      <div className="bg-slate-900 border border-slate-800 text-white rounded-xl p-5 shadow-sm">
        <h2 className="text-lg font-bold mb-1">复盘分析</h2>
        <p className="text-sm text-slate-400">MI-001 SOL 已完成试验前复核，尚未开始试验。</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-sm flex items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-teal-50 dark:bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
            <CheckCircle2 size={24} />
          </div>
          <div>
            <h3 className="text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">试验前复核</h3>
            <p className="text-base font-bold text-slate-900 dark:text-slate-100">已完成</p>
          </div>
        </div>
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-sm flex items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-teal-50 dark:bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
            <CheckCircle2 size={24} />
          </div>
          <div>
            <h3 className="text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">风险披露</h3>
            <p className="text-base font-bold text-slate-900 dark:text-slate-100">已完成</p>
          </div>
        </div>
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-sm flex items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-teal-50 dark:bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
            <CheckCircle2 size={24} />
          </div>
          <div>
            <h3 className="text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Owner 接受</h3>
            <p className="text-base font-bold text-slate-900 dark:text-slate-100">已完成</p>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm p-6">
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
          <AlertCircle className="text-amber-500" size={18} /> 当前结论
        </h3>
        <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-5 border border-slate-100 dark:border-slate-700/50 text-sm text-slate-700 dark:text-slate-300 space-y-4">
          <p className="leading-relaxed">
            <span className="font-medium text-slate-900 dark:text-slate-100">策略候选已完成准备，但运行时启动保护未完成预检。</span>
          </p>
          <p className="leading-relaxed">
            当前只适合继续查看证据或等待下一次授权。
          </p>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm p-6">
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-4">证据摘要</h3>
        <ul className="space-y-3">
          <li className="flex items-center gap-3 text-sm">
            <CheckCircle2 className="text-teal-500" size={16} />
            <span className="text-slate-600 dark:text-slate-400 w-40 font-mono">broad smoke</span>
            <span className="font-medium text-slate-800 dark:text-slate-200 border-l border-slate-200 dark:border-slate-700 pl-3">已完成</span>
          </li>
          <li className="flex items-center gap-3 text-sm">
            <CheckCircle2 className="text-teal-500" size={16} />
            <span className="text-slate-600 dark:text-slate-400 w-40 font-mono">Owner acceptance</span>
            <span className="font-medium text-slate-800 dark:text-slate-200 border-l border-slate-200 dark:border-slate-700 pl-3">已完成</span>
          </li>
          <li className="flex items-center gap-3 text-sm">
            <CheckCircle2 className="text-teal-500" size={16} />
            <span className="text-slate-600 dark:text-slate-400 w-40 font-mono">PG 注册</span>
            <span className="font-medium text-slate-800 dark:text-slate-200 border-l border-slate-200 dark:border-slate-700 pl-3">已完成</span>
          </li>
          <li className="flex items-center gap-3 text-sm">
            <CheckCircle2 className="text-teal-500" size={16} />
            <span className="text-slate-600 dark:text-slate-400 w-40 font-mono">final review</span>
            <span className="font-medium text-slate-800 dark:text-slate-200 border-l border-slate-200 dark:border-slate-700 pl-3">已完成</span>
          </li>
        </ul>
      </div>

      {/* Tech Details Fold */}
      <div className="text-sm">
        <button
          onClick={() => setShowTechDetails(!showTechDetails)}
          className="flex items-center gap-1.5 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors py-2 px-3 rounded-md hover:bg-slate-200/50 dark:hover:bg-slate-800/50"
        >
          {showTechDetails ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          查看技术详情
        </button>

        {showTechDetails && (
          <div className="mt-2 bg-slate-900 text-slate-300 p-5 rounded-lg text-[13px] font-mono overflow-x-auto shadow-inner border border-slate-800">
            <div className="flex flex-col gap-2">
              <div><span className="text-slate-500">review_id:</span> <span className="text-slate-200">rev_c90djx3lmn</span></div>
              <div><span className="text-slate-500">pg_entry:</span> <span className="text-slate-200">0f7ac98</span></div>
            </div>
          </div>
        )}
      </div>

    </div>
  );
}
