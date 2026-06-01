export default function StrategyGroups() {
  const groups = [
    { id: 1, name: 'MI-001 动量冲击', status: '准备完成', target: 'SOL 多头', signal: '暂无', action: '查看详情', highlight: true },
    { id: 2, name: 'MI-001 动量冲击', status: '候选', target: 'BNB 多头', signal: '暂无', action: '准备观察' },
    { id: 3, name: 'VI-001 波动扩张', status: '候选', target: 'ETH 多头', signal: '暂无', action: '查看证据' },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="bg-slate-900 border border-slate-800 text-white rounded-xl p-5 shadow-sm">
        <h2 className="text-lg font-bold mb-1">策略组</h2>
        <p className="text-sm text-slate-400">当前共有 3 个候选，1 个已进入试验前准备。</p>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden flex flex-col">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800">
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">策略组</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">状态</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">标的</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">最近信号</th>
                <th className="px-5 py-4 text-[13px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">下一步</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {groups.map((group) => (
                <tr key={group.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/20 transition-colors">
                  <td className="px-5 py-4 whitespace-nowrap">
                    <span className="font-bold text-slate-900 dark:text-slate-100">{group.name}</span>
                  </td>
                  <td className="px-5 py-4 whitespace-nowrap">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium border ${group.highlight ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20' : 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'}`}>
                      {group.status}
                    </span>
                  </td>
                  <td className="px-5 py-4 whitespace-nowrap">
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{group.target}</span>
                  </td>
                  <td className="px-5 py-4 whitespace-nowrap">
                    <span className="text-sm text-slate-500 dark:text-slate-400">{group.signal}</span>
                  </td>
                  <td className="px-5 py-4 whitespace-nowrap">
                    <button className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 transition-colors">
                      {group.action}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail Card for the first active one */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm p-6 mt-4">
        <div className="mb-6">
          <h3 className="text-xl font-bold text-slate-900 dark:text-slate-50 mb-2">MI-001 动量冲击</h3>
          <p className="text-sm text-slate-600 dark:text-slate-400 mb-1"><span className="font-medium text-slate-800 dark:text-slate-300">假设：</span>价格出现动量冲击后，短期有延续概率。</p>
          <p className="text-sm text-slate-600 dark:text-slate-400"><span className="font-medium text-slate-800 dark:text-slate-300">当前主策略：</span>SOL 多头观察</p>
        </div>

        <div className="overflow-x-auto border border-slate-200 dark:border-slate-800 rounded-lg mb-6">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800">
                <th className="px-4 py-3 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider border-r border-slate-200 dark:border-slate-800">具体策略</th>
                <th className="px-4 py-3 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider border-r border-slate-200 dark:border-slate-800">状态</th>
                <th className="px-4 py-3 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider border-r border-slate-200 dark:border-slate-800">观察模式</th>
                <th className="px-4 py-3 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">阻断</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              <tr>
                <td className="px-4 py-3 text-sm font-medium text-slate-900 dark:text-slate-100 border-r border-slate-100 dark:border-slate-800">SOL 多头</td>
                <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300 border-r border-slate-100 dark:border-slate-800">试验前准备完成</td>
                <td className="px-4 py-3 text-sm font-medium text-teal-600 dark:text-teal-400 border-r border-slate-100 dark:border-slate-800">只读 / 记录意图</td>
                <td className="px-4 py-3 text-sm font-medium text-amber-600 dark:text-amber-400">启动保护未预检</td>
              </tr>
              <tr>
                <td className="px-4 py-3 text-sm font-medium text-slate-900 dark:text-slate-100 border-r border-slate-100 dark:border-slate-800">BNB 多头</td>
                <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-500 border-r border-slate-100 dark:border-slate-800">候选</td>
                <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-500 border-r border-slate-100 dark:border-slate-800">未开始</td>
                <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-500">无</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="flex gap-3">
          <button className="px-4 py-2 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-700 dark:text-indigo-400 rounded-md text-sm font-medium transition-colors border border-indigo-200 dark:border-indigo-500/30">
            查看证据
          </button>
          <button className="px-4 py-2 bg-slate-50 hover:bg-slate-100 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-md text-sm font-medium transition-colors border border-slate-200 dark:border-slate-700">
            查看执行意图
          </button>
          <button className="px-4 py-2 bg-transparent hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 rounded-md text-sm font-medium transition-colors border border-transparent">
            技术详情
          </button>
        </div>
      </div>
    </div>
  );
}
