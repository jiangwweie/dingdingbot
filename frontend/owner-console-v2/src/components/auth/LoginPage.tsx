import React, { useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { Shield, Sun, Moon, Lock, User, KeyRound, AlertCircle } from 'lucide-react';
import type { LoginRequest } from '../../api/authApi';

interface LoginPageProps {
  onLogin: (credentials: LoginRequest) => Promise<void>;
  isLoading: boolean;
  error?: unknown;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onLogin, isLoading, error }) => {
  const { theme, toggleTheme } = useTheme();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);

    if (!username.trim()) {
      setValidationError('请输入 Owner 用户名');
      return;
    }
    if (!password) {
      setValidationError('请输入登录密码');
      return;
    }
    const cleanTotp = totpCode.trim();
    if (!/^\d{6}$/.test(cleanTotp)) {
      setValidationError('动态口令必须为 6 位数字');
      return;
    }

    try {
      await onLogin({
        username: username.trim(),
        password,
        totp_code: cleanTotp,
      });
    } catch (err: any) {
      // Handled by parent or displayed via error prop
    }
  };

  const errorMessage =
    validationError ||
    (error instanceof Error ? error.message : typeof error === 'string' ? error : null);

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4 selection:bg-brand selection:text-white">
      {/* Top right theme toggle */}
      <div className="absolute top-4 right-4">
        <button
          type="button"
          onClick={toggleTheme}
          className="flex h-8 w-8 items-center justify-center rounded border border-border bg-surface text-text-secondary hover:text-text-primary hover:bg-surface-elevated transition-colors"
          title={`切换为${theme === 'dark' ? '浅色' : '深色'}主题`}
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>

      <div className="w-full max-w-sm">
        {/* Brand header */}
        <div className="mb-6 text-center">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-xl bg-brand/10 border border-brand/20 text-brand mb-3 shadow-xs">
            <Shield className="h-6 w-6" />
          </div>
          <h1 className="text-lg font-bold tracking-tight text-text-primary flex items-center justify-center gap-2">
            <span>BRC OWNER CONSOLE</span>
            <span className="rounded bg-brand/10 text-brand text-[10px] font-mono px-1.5 py-0.5 border border-brand/20">
              PROD
            </span>
          </h1>
          <p className="mt-1 text-xs text-text-muted">
            Tokyo Trading Kernel · 生产控制台
          </p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <div className="mb-5 pb-3 border-b border-border">
            <h2 className="text-sm font-semibold text-text-primary">Owner 身份验证</h2>
            <p className="text-[11px] text-text-muted mt-0.5">
              需要输入生产账号凭据与 6 位 TOTP 动态验证码
            </p>
          </div>

          {errorMessage && (
            <div className="mb-4 flex items-start gap-2.5 rounded-lg border border-danger/30 bg-danger/10 p-3 text-xs text-danger animate-in fade-in-50">
              <AlertCircle className="h-4 w-4 flex-none mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5" htmlFor="username">
                Owner 用户名
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-muted">
                  <User className="h-3.5 w-3.5" />
                </div>
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={isLoading}
                  placeholder="owner"
                  className="w-full rounded border border-border bg-surface-subtle pl-9 pr-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand disabled:opacity-50 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5" htmlFor="password">
                登录密码
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-muted">
                  <Lock className="h-3.5 w-3.5" />
                </div>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  placeholder="••••••••••••"
                  className="w-full rounded border border-border bg-surface-subtle pl-9 pr-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand disabled:opacity-50 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5" htmlFor="totp">
                TOTP 动态口令 (6 位数字)
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-muted">
                  <KeyRound className="h-3.5 w-3.5" />
                </div>
                <input
                  id="totp"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                  disabled={isLoading}
                  placeholder="123456"
                  className="w-full rounded border border-border bg-surface-subtle pl-9 pr-3 py-2 font-mono text-sm tracking-widest text-text-primary placeholder:text-text-muted placeholder:tracking-normal focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand disabled:opacity-50 transition-colors"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full mt-2 inline-flex items-center justify-center gap-2 rounded bg-brand px-4 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-brand/90 focus:outline-none focus:ring-2 focus:ring-brand/40 disabled:opacity-60 transition-colors"
            >
              {isLoading ? (
                <>
                  <div className="h-3.5 w-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>正在验证会话...</span>
                </>
              ) : (
                <span>登录 Owner Console</span>
              )}
            </button>
          </form>

          <div className="mt-5 pt-3 border-t border-border text-center">
            <span className="text-[10px] text-text-muted">
              会话采用 HttpOnly / Secure / Strict Cookie 保护 · 严禁凭据硬编码
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
