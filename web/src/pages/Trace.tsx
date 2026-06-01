import { useState } from "react";
import { CheckCircle2, Circle, AlertCircle, ChevronDown, ChevronRight, Check } from "lucide-react";

export default function Trace() {
  const [expandedNode, setExpandedNode] = useState<string | null>("startup");

  const toggleNode = (nodeId: string) => {
    if (expandedNode === nodeId) {
      setExpandedNode(null);
    } else {
      setExpandedNode(nodeId);
    }
  };

  const steps = [
    {
      id: "candidate",
      title: "策略候选形成",
      status: "已完成",
      statusColor: "teal",
      desc: "MI-001 SOL long",
      icon: Check
    },
    {
      id: "risk",
      title: "Owner 风险接受",
      status: "已完成",
      statusColor: "teal",
      desc: "已接受进入准备阶段",
      icon: Check
    },
    {
      id: "pg",
      title: "PG 注册",
      status: "已完成",
      statusColor: "teal",
      desc: "已写入主数据源",
      icon: Check
    },
    {
      id: "review",
      title: "最终复核",
      status: "已完成",
      statusColor: "teal",
      desc: "final pre-start review",
      icon: Check
    },
    {
      id: "startup",
      title: "启动保护",
      status: "阻断",
      statusColor: "amber",
      desc: "需要运行时预检",
      icon: AlertCircle,
      details: {
        reason: "运行时启动保护还没有完成预检。",
        techState: "blocked_startup_guard_runtime_coupled"
      }
    }
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="bg-slate-900 border border-slate-800 text-white rounded-xl p-5 shadow-sm">
        <h2 className="text-lg font-bold mb-1">链路追踪</h2>
        <p className="text-sm text-slate-400">查看 MI-001 SOL 从候选到当前阻断状态的完整过程。</p>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm p-6">
        <div className="relative border-l-2 border-slate-200 dark:border-slate-800 ml-5 py-4 space-y-10">

          {steps.map((step, index) => (
            <div key={step.id} className="relative pl-8">
              {/* Node dot */}
              <div className={`absolute -left-[17px] top-1 w-8 h-8 rounded-full border-4 border-white dark:border-slate-900 flex items-center justify-center
                  ${step.statusColor === 'teal' ? 'bg-teal-100 text-teal-600 dark:bg-teal-900/50 dark:text-teal-400' : 'bg-amber-100 text-amber-600 dark:bg-amber-900/50 dark:text-amber-400'}
                `}>
                <step.icon size={14} strokeWidth={3} />
              </div>

              {/* Node Content */}
              <div
                className="bg-slate-50 dark:bg-slate-800/30 rounded-xl p-4 border border-slate-100 dark:border-slate-700/50 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800/50 transition-colors"
                onClick={() => {
                  if (step.details) toggleNode(step.id);
                }}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">{step.title}</h3>
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium border
                        ${step.statusColor === 'teal'
                          ? 'bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-500/10 dark:text-teal-400 dark:border-teal-500/20'
                          : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20'}
                      `}>
                      {step.status}
                    </span>
                  </div>
                  {step.details && (
                    <div className="text-slate-400 dark:text-slate-500">
                      {expandedNode === step.id ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    </div>
                  )}
                </div>

                <p className="text-sm text-slate-600 dark:text-slate-400 mt-2">{step.desc}</p>

                {/* Expanded Details */}
                {expandedNode === step.id && step.details && (
                  <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-700/50">
                    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg p-4 space-y-3">
                      <div className="flex items-center gap-2">
                        <span className={`inline-block w-2.5 h-2.5 rounded-full ${step.statusColor === 'amber' ? 'bg-amber-500' : 'bg-teal-500'}`}></span>
                        <span className="text-sm font-medium text-slate-900 dark:text-slate-100">状态：{step.status}</span>
                      </div>
                      <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                        说明：{step.details.reason}
                      </p>

                      <div className="mt-4 bg-slate-100/50 dark:bg-slate-950 p-3 rounded border border-slate-200 dark:border-slate-800">
                        <p className="text-[11px] font-bold text-slate-500 dark:text-slate-500 uppercase mb-1">技术状态</p>
                        <p className="text-xs font-mono text-amber-600 dark:text-amber-400 break-all">{step.details.techState}</p>
                      </div>
                    </div>
                  </div>
                )}

              </div>
            </div>
          ))}

        </div>
      </div>
    </div>
  );
}
