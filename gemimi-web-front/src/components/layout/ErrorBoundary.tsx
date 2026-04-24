import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 p-4">
          <div className="max-w-md w-full bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg shadow-xl p-6">
            <div className="flex items-center gap-3 text-rose-500 mb-4">
              <AlertTriangle className="w-8 h-8" />
              <h2 className="text-xl font-bold tracking-tight">系统组件加载失败</h2>
            </div>
            <p className="text-zinc-600 dark:text-zinc-400 text-sm mb-4">
              页面渲染期间发生未捕获的异常。请尝试刷新页面或向管理员报告此问题。
            </p>
            {this.state.error && (
              <div className="bg-rose-950/20 text-rose-400 border border-rose-900/50 p-3 rounded font-mono text-xs overflow-auto mb-6 max-h-32">
                {this.state.error.message}
              </div>
            )}
            <button
              onClick={() => window.location.reload()}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-zinc-900 dark:text-white transition-colors py-2 px-4 rounded font-medium text-sm"
            >
              <RefreshCw className="w-4 h-4" />
              重新加载应用 (Reload App)
            </button>
          </div>
        </div>
      );
    }

    return (this as any).props.children;
  }
}
