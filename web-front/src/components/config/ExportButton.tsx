import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { exportConfig } from '../../lib/api';
import { cn } from '../../lib/utils';

interface ExportButtonProps {
  className?: string;
}

export default function ExportButton({ className }: ExportButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const blob = await exportConfig();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;

      // 生成带时间戳的文件名
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
      link.download = `user_config_${timestamp}.yaml`;

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err.message || '导出失败，请重试');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={cn('inline-flex flex-col', className)}>
      <button
        onClick={handleExport}
        disabled={isLoading}
        className={cn(
          'inline-flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all',
          isLoading
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-black text-white hover:bg-gray-800'
        )}
      >
        {isLoading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            导出中...
          </>
        ) : (
          <>
            <Download className="w-4 h-4" />
            导出配置
          </>
        )}
      </button>
      {error && (
        <span className="mt-1 text-xs text-red-500">{error}</span>
      )}
    </div>
  );
}
