export default function Intents() {
  const intents = [
    { id: 1, time: '10:00:00', strategy: 'MI-001 SOL', asset: 'SOL', direction: '多', intent: '想入场', status: '已记录未执行', statusColor: 'teal', result: '+1.2%', resultColor: 'teal' },
    { id: 2, time: '14:00:00', strategy: 'MI-001 SOL', asset: 'SOL', direction: '多', intent: '想入场', status: '被阻断', statusColor: 'amber', result: '-0.8%', resultColor: 'rose' },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="bg-slate-900 border border-slate-800 text-white rounded-xl p-5 shadow-sm">
        <h2 className="text-lg font-bold mb-1">执行意图</h2>
        <p className="text-sm text-slate-400">这里只记录策略意图，不会触发交易。</p>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800">
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">时间</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">策略</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">标的</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">方向</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">意图</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">状态</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">后续表现</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {intents.map((intent) => (
                <tr key={intent.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/20 transition-colors cursor-pointer">
                  <td className="px-5 py-4 whitespace-nowrap text-sm font-mono text-slate-600 dark:text-slate-400">{intent.time}</td>
                  <td className="px-5 py-4 whitespace-nowrap text-sm font-medium text-slate-900 dark:text-slate-100">{intent.strategy}</td>
                  <td className="px-5 py-4 whitespace-nowrap text-sm font-medium text-slate-700 dark:text-slate-300">{intent.asset}</td>
                  <td className="px-5 py-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-400 border border-teal-200 dark:border-teal-900/50">
                      {intent.direction}
                    </span>
                  </td>
                  <td className="px-5 py-4 whitespace-nowrap text-sm font-medium text-slate-800 dark:text-slate-200">{intent.intent}</td>
                  <td className="px-5 py-4 whitespace-nowrap">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium border ${
                      intent.statusColor === 'teal'
                        ? 'bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-500/10 dark:text-teal-400 dark:border-teal-500/20'
                        : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20'
                    }`}>
                      {intent.status}
                    </span>
                  </td>
                  <td className="px-5 py-4 whitespace-nowrap">
                    <span className={`text-sm font-bold font-mono ${
                      intent.resultColor === 'teal' ? 'text-teal-600 dark:text-teal-400' : 'text-rose-600 dark:text-rose-400'
                    }`}>
                      {intent.result}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Empty State example if there were no intents */}
      {/*
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-10 flex flex-col items-center justify-center text-center shadow-sm">
        <h4 className="text-lg font-bold text-slate-800 dark:text-slate-200 mb-2">暂无执行意图</h4>
        <p className="text-sm text-slate-500 dark:text-slate-400 max-w-sm">策略还没有产生可记录的意图，或当前仍处于准备阶段。</p>
      </div>
      */}
    </div>
  );
}
