import { useState, useEffect } from 'react';
import { X, Copy } from 'lucide-react';
import { cn } from '../../lib/utils';

interface CreateProfileModalProps {
  open: boolean;
  onClose: () => void;
  onCreate: (
    name: string,
    description?: string,
    switchAfterCreate?: boolean
  ) => Promise<void>;
  existingNames: string[];
  sourceProfile?: string | null; // Optional source profile for copying
}

export default function CreateProfileModal({
  open,
  onClose,
  onCreate,
  existingNames,
  sourceProfile,
}: CreateProfileModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [switchAfterCreate, setSwitchAfterCreate] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Update description when sourceProfile changes
  useEffect(() => {
    if (open && sourceProfile) {
      setDescription(`复制自 "${sourceProfile}"`);
    }
  }, [open, sourceProfile]);

  // Validate name
  const validateName = (value: string): string | null => {
    if (!value || value.trim().length === 0) {
      return '名称不能为空';
    }
    if (value.length > 32) {
      return '名称长度不能超过 32 个字符';
    }
    if (existingNames.includes(value)) {
      return '该名称已被使用';
    }
    if (value === 'default') {
      return "'default' 是保留名称";
    }
    // Check for valid characters (allow Chinese, letters, numbers, underscore, hyphen)
    const validPattern = /^[\u4e00-\u9fa5a-zA-Z0-9_-]+$/;
    if (!validPattern.test(value)) {
      return '名称只能包含字母、数字、中文、下划线或连字符';
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const validationError = validateName(name);
    if (validationError) {
      setError(validationError);
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      await onCreate(name, description || undefined, switchAfterCreate);
      // Reset form
      setName('');
      setDescription('');
      setSwitchAfterCreate(true);
    } catch (err: any) {
      setError(err.message || '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setName(value);
    const validationError = validateName(value);
    setError(validationError);
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
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">新建 Profile</h2>
            {sourceProfile && (
              <p className="text-sm text-gray-500 mt-1">
                从 "{sourceProfile}" 复制配置
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Name Input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              名称 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={handleNameChange}
              placeholder="如：保守型、激进型、美盘时段..."
              className={cn(
                'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-black focus:border-transparent',
                error ? 'border-red-300' : 'border-gray-300'
              )}
              autoFocus
            />
            {error && (
              <p className="mt-1 text-sm text-red-600">{error}</p>
            )}
            <p className="mt-1 text-xs text-gray-500">
              1-32 个字符，只能包含字母、数字、中文、下划线或连字符
            </p>
          </div>

          {/* Description Input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              描述
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简短说明此 Profile 的用途..."
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-black focus:border-transparent resize-none"
            />
            <p className="mt-1 text-xs text-gray-500">
              可选，最多 100 个字符
            </p>
          </div>

          {/* Switch After Create */}
          <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
            <input
              type="checkbox"
              id="switchAfterCreate"
              checked={switchAfterCreate}
              onChange={(e) => setSwitchAfterCreate(e.target.checked)}
              className="w-4 h-4 text-black border-gray-300 rounded focus:ring-black"
            />
            <label htmlFor="switchAfterCreate" className="text-sm text-gray-700">
              创建后立即切换到此 Profile
            </label>
          </div>

          {/* Submit Button */}
          <div className="flex items-center gap-3 pt-4 border-t border-gray-100">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={submitting || !!error || !name.trim()}
              className="flex-1 px-4 py-2 text-white bg-black rounded-lg font-medium hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? '创建中...' : '创建'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
