import { Fragment, useState, useRef, ChangeEvent, DragEvent } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, Upload, FileText, AlertCircle, CheckCircle, Loader2 } from 'lucide-react';
import { importConfig } from '../../lib/api';
import { cn } from '../../lib/utils';

interface ImportDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function ImportDialog({ open, onClose, onSuccess }: ImportDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>('');
  const [description, setDescription] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    // 验证文件类型
    if (!selectedFile.name.endsWith('.yaml') && !selectedFile.name.endsWith('.yml')) {
      setError('请上传 YAML 格式文件 (.yaml 或 .yml)');
      return;
    }

    // 验证文件大小（最大 1MB）
    if (selectedFile.size > 1024 * 1024) {
      setError('文件大小不能超过 1MB');
      return;
    }

    setFile(selectedFile);
    setError(null);
    setSuccess(false);

    // 读取文件内容进行预览
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setPreview(content.slice(0, 500)); // 只显示前 500 字符
    };
    reader.readAsText(selectedFile);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files?.[0];
    if (!droppedFile) return;

    if (!droppedFile.name.endsWith('.yaml') && !droppedFile.name.endsWith('.yml')) {
      setError('请上传 YAML 格式文件 (.yaml 或 .yml)');
      return;
    }

    if (droppedFile.size > 1024 * 1024) {
      setError('文件大小不能超过 1MB');
      return;
    }

    setFile(droppedFile);
    setError(null);
    setSuccess(false);

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setPreview(content.slice(0, 500));
    };
    reader.readAsText(droppedFile);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleImport = async () => {
    if (!file) {
      setError('请选择要导入的文件');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      await importConfig(file, description || '配置导入');
      setSuccess(true);
      setTimeout(() => {
        onSuccess();
        handleClose();
      }, 1500);
    } catch (err: any) {
      setError(err.message || '导入失败，请重试');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setFile(null);
    setPreview('');
    setDescription('');
    setError(null);
    setSuccess(false);
    onClose();
  };

  return (
    <Transition appear show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/25 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                  <div className="flex items-center gap-3">
                    <Upload className="w-5 h-5 text-gray-500" />
                    <Dialog.Title className="text-lg font-semibold text-gray-900">
                      导入配置
                    </Dialog.Title>
                  </div>
                  <button
                    onClick={handleClose}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5 text-gray-500" />
                  </button>
                </div>

                {/* Content */}
                <div className="p-6 space-y-4">
                  {/* Error banner */}
                  {error && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 flex-shrink-0" />
                      {error}
                    </div>
                  )}

                  {/* Success banner */}
                  {success && (
                    <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm flex items-center gap-2">
                      <CheckCircle className="w-4 h-4 flex-shrink-0" />
                      配置导入成功
                    </div>
                  )}

                  {/* Drop zone */}
                  {!file ? (
                    <div
                      onDrop={handleDrop}
                      onDragOver={handleDragOver}
                      onClick={() => fileInputRef.current?.click()}
                      className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-black transition-colors"
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".yaml,.yml"
                        onChange={handleFileSelect}
                        className="hidden"
                      />
                      <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                      <p className="text-sm font-medium text-gray-700">
                        点击或拖拽文件到此处
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        支持 YAML 格式 (.yaml 或 .yml)，最大 1MB
                      </p>
                    </div>
                  ) : (
                    <div className="border border-gray-200 rounded-xl p-4">
                      <div className="flex items-center gap-3 mb-3">
                        <FileText className="w-8 h-8 text-black" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {file.name}
                          </p>
                          <p className="text-xs text-gray-500">
                            {(file.size / 1024).toFixed(1)} KB
                          </p>
                        </div>
                        <button
                          onClick={() => {
                            setFile(null);
                            setPreview('');
                            setError(null);
                          }}
                          className="p-1 hover:bg-gray-100 rounded transition-colors"
                        >
                          <X className="w-4 h-4 text-gray-400" />
                        </button>
                      </div>

                      {/* Preview */}
                      {preview && (
                        <div className="bg-gray-50 rounded-lg p-3">
                          <p className="text-xs text-gray-500 mb-1">文件预览:</p>
                          <pre className="text-xs text-gray-700 font-mono whitespace-pre-wrap overflow-hidden">
                            {preview}
                            {preview.length >= 500 && '...'}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Description input */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      快照描述（可选）
                    </label>
                    <input
                      type="text"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="例如：配置导入"
                      maxLength={200}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
                    />
                  </div>
                </div>

                {/* Footer */}
                <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex gap-3">
                  <button
                    onClick={handleClose}
                    disabled={isLoading}
                    className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-100 transition-colors disabled:opacity-50"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleImport}
                    disabled={!file || isLoading}
                    className={cn(
                      'flex-1 px-4 py-2 rounded-lg font-medium transition-all flex items-center justify-center gap-2',
                      !file || isLoading
                        ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                        : 'bg-black text-white hover:bg-gray-800'
                    )}
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        导入中...
                      </>
                    ) : (
                      <>
                        <Upload className="w-4 h-4" />
                        导入并应用
                      </>
                    )}
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
