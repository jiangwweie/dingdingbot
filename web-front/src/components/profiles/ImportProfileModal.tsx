import { useState, useCallback } from 'react';
import { X, Upload, FileText } from 'lucide-react';
import { importProfile } from '../../lib/api';
import { cn } from '../../lib/utils';

interface ImportProfileModalProps {
  open: boolean;
  onClose: () => void;
  onImportSuccess: () => void;
}

export default function ImportProfileModal({
  open,
  onClose,
  onImportSuccess,
}: ImportProfileModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [yamlContent, setYamlContent] = useState<string>('');
  const [profileName, setProfileName] = useState('');
  const [mode, setMode] = useState<'create' | 'overwrite'>('create');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{
    name: string;
    description: string;
    configCount: number;
  } | null>(null);

  // Parse YAML content when file is selected
  const parseYamlContent = useCallback((content: string) => {
    try {
      // Simple YAML parsing for preview
      // In production, use a proper YAML parser
      const lines = content.split('\n');
      let name = '';
      let description = '';
      let configCount = 0;

      for (const line of lines) {
        if (line.startsWith('profile:')) {
          continue;
        }
        const trimmed = line.trim();
        if (trimmed.startsWith('name:')) {
          name = trimmed.replace('name:', '').trim().replace(/["']/g, '');
        } else if (trimmed.startsWith('description:')) {
          description = trimmed.replace('description:', '').trim().replace(/["']/g, '');
        } else if (trimmed.includes(':') && !trimmed.startsWith('#')) {
          configCount++;
        }
      }

      setPreview({
        name: name || 'imported',
        description,
        configCount: Math.max(0, configCount - 2), // Subtract profile metadata
      });
      setProfileName(name || 'imported');
      setYamlContent(content);
      setError(null);
    } catch (err: any) {
      setError('YAML 解析失败');
    }
  }, []);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFile = e.target.files?.[0];
      if (!selectedFile) return;

      // Validate file type
      if (!selectedFile.name.endsWith('.yaml') && !selectedFile.name.endsWith('.yml')) {
        setError('请选择 .yaml 或 .yml 格式的文件');
        return;
      }

      // Validate file size (max 1MB)
      if (selectedFile.size > 1024 * 1024) {
        setError('文件大小不能超过 1MB');
        return;
      }

      setFile(selectedFile);

      // Read file content
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        parseYamlContent(content);
      };
      reader.onerror = () => {
        setError('文件读取失败');
      };
      reader.readAsText(selectedFile);
    },
    [parseYamlContent]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const droppedFile = e.dataTransfer.files?.[0];
      if (droppedFile) {
        // Validate and read file
        if (!droppedFile.name.endsWith('.yaml') && !droppedFile.name.endsWith('.yml')) {
          setError('请选择 .yaml 或 .yml 格式的文件');
          return;
        }
        if (droppedFile.size > 1024 * 1024) {
          setError('文件大小不能超过 1MB');
          return;
        }
        setFile(droppedFile);
        const reader = new FileReader();
        reader.onload = (e) => {
          const content = e.target?.result as string;
          parseYamlContent(content);
        };
        reader.readAsText(droppedFile);
      }
    },
    [parseYamlContent]
  );

  const handleSubmit = async () => {
    if (!yamlContent) {
      setError('请选择文件');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      await importProfile({
        yaml_content: yamlContent,
        profile_name: profileName || undefined,
        mode,
      });

      // Reset and close
      setFile(null);
      setYamlContent('');
      setProfileName('');
      setMode('create');
      setPreview(null);

      onImportSuccess();
    } catch (err: any) {
      setError(err.message || '导入失败');
    } finally {
      setLoading(false);
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
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">导入 Profile</h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* File Upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              选择 YAML 文件
            </label>
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              className={cn(
                'border-2 border-dashed rounded-xl p-8 text-center transition-colors',
                file
                  ? 'border-green-300 bg-green-50'
                  : 'border-gray-300 hover:border-gray-400'
              )}
            >
              <input
                type="file"
                accept=".yaml,.yml"
                onChange={handleFileSelect}
                className="hidden"
                id="yaml-upload"
              />
              <label htmlFor="yaml-upload" className="cursor-pointer">
                <Upload className="w-8 h-8 text-gray-400 mx-auto mb-3" />
                <p className="text-sm text-gray-600">
                  {file ? file.name : '拖拽文件到此处 或 点击选择文件'}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  支持 .yaml, .yml 格式，最大 1MB
                </p>
              </label>
            </div>
          </div>

          {/* Preview */}
          {preview && (
            <div className="border border-gray-200 rounded-xl overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                <h3 className="text-sm font-semibold text-gray-900">预览内容</h3>
              </div>
              <div className="p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-gray-400" />
                  <span className="text-sm text-gray-600">
                    Profile 名称：{preview.name}
                  </span>
                </div>
                {preview.description && (
                  <p className="text-sm text-gray-500 pl-6">{preview.description}</p>
                )}
                <p className="text-sm text-gray-500 pl-6">
                  配置项数量：{preview.configCount}
                </p>
              </div>
            </div>
          )}

          {/* Import Mode */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              导入模式
            </label>
            <div className="space-y-2">
              <label
                className={cn(
                  'flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-colors',
                  mode === 'create'
                    ? 'border-black bg-gray-50'
                    : 'border-gray-200 hover:border-gray-300'
                )}
              >
                <input
                  type="radio"
                  name="mode"
                  value="create"
                  checked={mode === 'create'}
                  onChange={() => setMode('create')}
                  className="w-4 h-4 text-black border-gray-300 focus:ring-black"
                />
                <span className="text-sm text-gray-700">创建新 Profile</span>
              </label>
              <label
                className={cn(
                  'flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-colors',
                  mode === 'overwrite'
                    ? 'border-black bg-gray-50'
                    : 'border-gray-200 hover:border-gray-300'
                )}
              >
                <input
                  type="radio"
                  name="mode"
                  value="overwrite"
                  checked={mode === 'overwrite'}
                  onChange={() => setMode('overwrite')}
                  className="w-4 h-4 text-black border-gray-300 focus:ring-black"
                />
                <span className="text-sm text-gray-700">覆盖现有 Profile</span>
              </label>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 px-6 py-4 border-t border-gray-100">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg font-medium hover:bg-gray-50 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || !yamlContent}
            className="flex-1 px-4 py-2 text-white bg-black rounded-lg font-medium hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '导入中...' : '导入'}
          </button>
        </div>
      </div>
    </div>
  );
}
