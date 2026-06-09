import React, { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { LockKeyhole, ShieldCheck } from 'lucide-react';
import { Badge, Card } from '@/components/ui';
import { ThemeToggle } from '@/components/ThemeToggle';
import { useAuth } from '@/lib/auth';

type LocationState = {
  from?: {
    pathname?: string;
  };
};

export default function Login() {
  const { session, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as LocationState | null;
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!loading && session?.authenticated) {
    return <Navigate to={state?.from?.pathname || '/'} replace />;
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({
        username: username.trim(),
        password,
        totp_code: totpCode.trim(),
      });
      navigate(state?.from?.pathname || '/', { replace: true });
    } catch (loginError) {
      console.error('Operator login failed', loginError);
      setError('登录失败，请核对账号、密码和验证码。');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="console-surface flex min-h-screen items-center justify-center p-4 text-slate-900 dark:text-slate-100">
      <div className="fixed right-4 top-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-md space-y-5">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-blue-600 dark:text-blue-400">
            <ShieldCheck className="h-5 w-5" />
            <span className="text-sm font-medium">受控交易控制台</span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">登录交易控制台</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            使用 Operator 账号进入；操作控制需经过预检和确认。
          </p>
        </div>

        <Card className="p-5">
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="username" className="text-sm font-medium">账号</label>
              <input
                id="username"
                name="username"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="w-full rounded-md border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 px-3 py-2 text-sm outline-none focus:border-blue-500"
                required
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="password" className="text-sm font-medium">密码</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-md border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 px-3 py-2 text-sm outline-none focus:border-blue-500"
                required
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="totp" className="text-sm font-medium">动态验证码</label>
              <input
                id="totp"
                name="totp"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={totpCode}
                onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                className="w-full rounded-md border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 px-3 py-2 text-sm font-mono tracking-widest outline-none focus:border-blue-500"
                required
                minLength={6}
                maxLength={6}
              />
            </div>

            {error && (
              <div className="rounded-md border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/20 p-3 text-sm text-red-700 dark:text-red-300">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || loading}
              className="w-full inline-flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300 dark:disabled:bg-slate-700"
            >
              <LockKeyhole className="h-4 w-4" />
              {submitting ? '正在登录' : '登录'}
            </button>
          </form>
        </Card>

        <div className="flex items-center justify-between text-xs text-slate-500">
          <Badge variant="muted">操作需确认</Badge>
          <span>不会直接开放下单、撤单、平仓或保护重试。</span>
        </div>
      </div>
    </div>
  );
}
