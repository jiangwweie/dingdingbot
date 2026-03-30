import { useState } from 'react';
import { useApi } from '../lib/api';
import { formatBeijingTime } from '../lib/utils';
import { Plus, Trash2, RotateCcw, CheckCircle, FileText } from 'lucide-react';
import { cn } from '../lib/utils';
import {
  ConfigSnapshot,
  fetchSnapshots,
  createSnapshot,
  deleteSnapshot,
  applySnapshot,
} from '../lib/api';

export default function Snapshots() {
  const [isCreating, setIsCreating] = useState(false);
  const [newVersion, setNewVersion] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // Fetch snapshots with SWR
  const { data, error, mutate } = useApi<{ total: number; data: ConfigSnapshot[] }>(
    '/api/config/snapshots'
  );

  const isLoading = !data && !error;
  const snapshots = data?.data || [];

  // Create new snapshot
  const handleCreate = async () => {
    if (!newVersion.trim()) {
      setErrorMessage('请输入版本号');
      return;
    }

    setIsSaving(true);
    setErrorMessage('');

    try {
      // 先获取当前配置
      const res = await fetch('/api/config');
      const currentConfig = await res.json();

      await createSnapshot({
        version: newVersion,
        description: newDescription,
        config_json: JSON.stringify(currentConfig),
      });
      await mutate();
      setIsCreating(false);
      setNewVersion('');
      setNewDescription('');
    } catch (err: any) {
      setErrorMessage(err.info?.detail || '创建失败，请重试');
    } finally {
      setIsSaving(false);
    }
  };

  // Activate snapshot
  const handleActivate = async (id: number, version: string) => {
    if (!confirm(`确定要回滚到版本 ${version} 吗？此操作将停用当前活跃快照。`)) {
      return;
    }

    try {
      await applySnapshot(id);
      await mutate();
    } catch (err: any) {
      alert(err.info?.detail || '回滚失败，请重试');
    }
  };

  // Delete snapshot
  const handleDelete = async (id: number) => {
    if (!confirm('确定要删除此快照吗？此操作不可恢复。')) {
      return;
    }

    try {
      await deleteSnapshot(id);
      await mutate();
    } catch (err: any) {
      alert(err.info?.detail || '删除失败，请重试');
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-12 bg-white rounded-2xl shadow-sm border border-gray-100" />
        <div className="h-96 bg-white rounded-2xl shadow-sm border border-gray-100" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">配置快照管理</h1>
          <p className="text-sm text-gray-500 mt-1">保存、查看和回滚配置历史版本</p>
        </div>
        <button
          onClick={() => setIsCreating(true)}
          className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 transition-colors"
        >
          <Plus className="w-4 h-4" />
          创建快照
        </button>
      </div>

      {/* Create Snapshot Modal */}
      {isCreating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setIsCreating(false)} />
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 m-4">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold">创建配置快照</h2>
              <button onClick={() => setIsCreating(false)} className="p-1 hover:bg-gray-100 rounded-lg">
                <FileText className="w-5 h-5 text-gray-500" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">版本号</label>
                <input
                  type="text"
                  value={newVersion}
                  onChange={(e) => setNewVersion(e.target.value)}
                  placeholder="如：v1.0.0"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-black transition-colors"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">描述</label>
                <textarea
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="快照描述..."
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-black transition-colors"
                />
              </div>
              {errorMessage && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
                  {errorMessage}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setIsCreating(false)}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={isSaving}
                className="px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 transition-colors"
              >
                {isSaving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {snapshots.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 bg-white rounded-2xl shadow-sm border border-gray-100">
          <FileText className="w-16 h-16 mb-4 opacity-20" />
          <p className="text-lg font-medium text-gray-600">暂无快照</p>
          <p className="text-sm mt-2">点击上方按钮创建第一个配置快照</p>
        </div>
      ) : (
        /* Snapshots Table */
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-500 bg-gray-50/50 uppercase">
              <tr>
                <th className="px-6 py-4 font-medium">版本</th>
                <th className="px-6 py-4 font-medium">描述</th>
                <th className="px-6 py-4 font-medium">创建时间</th>
                <th className="px-6 py-4 font-medium">状态</th>
                <th className="px-6 py-4 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {snapshots.map((snapshot) => (
                <tr key={String(snapshot.id)} className="hover:bg-gray-50">
                  <td className="px-6 py-4 font-medium">{snapshot.version}</td>
                  <td className="px-6 py-4 text-gray-600">{snapshot.description || '-'}</td>
                  <td className="px-6 py-4 text-gray-500">
                    {formatBeijingTime(snapshot.created_at, 'short')}
                  </td>
                  <td className="px-6 py-4">
                    {snapshot.is_active ? (
                      <span className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-apple-green/10 text-apple-green">
                        <CheckCircle className="w-3 h-3" />
                        活跃
                      </span>
                    ) : (
                      <span className="text-gray-400">历史</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {!snapshot.is_active && (
                        <button
                          onClick={() => handleActivate(snapshot.id, snapshot.version)}
                          className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title="回滚到此版本"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(snapshot.id)}
                        className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
