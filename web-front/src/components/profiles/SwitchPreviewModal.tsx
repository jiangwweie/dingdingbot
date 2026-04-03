import { useState, useEffect } from 'react';
import { X, ArrowRight, AlertCircle } from 'lucide-react';
import { compareProfiles } from '../../lib/api';
import { cn } from '../../lib/utils';

interface SwitchPreviewModalProps {
  open: boolean;
  onClose: () => void;
  profileName: string;
  onConfirm: () => Promise<void>;
}

interface DiffItem {
  path: string;
  module: string;
  old: string;
  new: string;
}

interface ModuleDiff {
  name: string;
  items: DiffItem[];
}

export default function SwitchPreviewModal({
  open,
  onClose,
  profileName,
  onConfirm,
}: SwitchPreviewModalProps) {
  const [loading, setLoading] = useState(false);
  const [diffs, setDiffs] = useState<ModuleDiff[]>([]);
  const [totalChanges, setTotalChanges] = useState(0);
  const [currentProfile, setCurrentProfile] = useState<string>('default');
  const [submitting, setSubmitting] = useState(false);

  // Load diff when modal opens
  useEffect(() => {
    if (open && profileName) {
      loadDiff();
    }
  }, [open, profileName]);

  const loadDiff = async () => {
    try {
      setLoading(true);
      // Compare current active profile with target profile
      const result = await compareProfiles(currentProfile, profileName);

      // Transform diff data into modules
      const diffData = result.diff.diff;
      const modules: Record<string, DiffItem[]> = {};

      Object.entries(diffData).forEach(([module, items]) => {
        modules[module] = Object.entries(items).map(([path, values]) => ({
          path,
          module,
          old: values.old,
          new: values.new,
        }));
      });

      const moduleDiffs: ModuleDiff[] = Object.entries(modules).map(
        ([name, items]) => ({
          name: getModuleName(name),
          items,
        })
      );

      setDiffs(moduleDiffs);
      setTotalChanges(result.diff.total_changes);
    } catch (err: any) {
      console.error('Failed to load diff:', err);
    } finally {
      setLoading(false);
    }
  };

  const getModuleName = (key: string): string => {
    const names: Record<string, string> = {
      strategy: '📊 策略配置',
      risk: '⚠️ 风控配置',
      exchange: '🔌 交易所配置',
      other: '⚙️ 其他配置',
    };
    return names[key] || key;
  };

  const handleSubmit = async () => {
    try {
      setSubmitting(true);
      await onConfirm();
    } catch (err: any) {
      console.error('Switch failed:', err);
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">切换配置预览</h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900" />
            </div>
          ) : (
            <div className="space-y-6">
              {/* Summary */}
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                <div>
                  <p className="text-sm text-gray-600">
                    从 <span className="font-medium">{currentProfile}</span>{' '}
                    切换到 <span className="font-medium">{profileName}</span>
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    共 {totalChanges} 项配置不同
                  </p>
                </div>
                {totalChanges === 0 ? (
                  <div className="flex items-center gap-2 text-green-600">
                    <div className="w-2 h-2 bg-green-500 rounded-full" />
                    <span className="text-sm font-medium">无差异</span>
                  </div>
                ) : (
                  <ArrowRight className="w-5 h-5 text-gray-400" />
                )}
              </div>

              {/* Diffs by Module */}
              {diffs.length > 0 && (
                <div className="space-y-4">
                  {diffs.map((module) => (
                    <div key={module.name} className="border border-gray-200 rounded-xl overflow-hidden">
                      <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                        <h3 className="text-sm font-semibold text-gray-900">
                          {module.name} ({module.items.length})
                        </h3>
                      </div>
                      <div className="divide-y divide-gray-100">
                        {module.items.map((item, index) => (
                          <div
                            key={index}
                            className="p-4 grid grid-cols-3 gap-4 items-center"
                          >
                            <div className="col-span-1 text-sm text-gray-600 font-mono">
                              {item.path}
                            </div>
                            <div className="col-span-1 text-sm">
                              <div className="px-3 py-1.5 bg-red-50 text-red-700 rounded-lg">
                                {item.old || '(未配置)'}
                              </div>
                            </div>
                            <div className="col-span-1 text-sm">
                              <div className="px-3 py-1.5 bg-green-50 text-green-700 rounded-lg">
                                {item.new || '(未配置)'}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {diffs.length === 0 && !loading && (
                <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                  <div className="w-2 h-2 bg-green-500 rounded-full mb-4" />
                  <p>两个 Profile 配置完全相同</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg font-medium hover:bg-gray-50 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex-1 px-4 py-2 text-white bg-black rounded-lg font-medium hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {submitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                切换中...
              </>
            ) : (
              <>
                <AlertCircle className="w-4 h-4" />
                确认切换
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
