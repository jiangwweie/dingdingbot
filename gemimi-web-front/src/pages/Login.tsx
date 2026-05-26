import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KeyRound, ShieldCheck } from 'lucide-react';
import { brcApi } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('owner');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await brcApi.login(username, password, totpCode);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败。请检查账号、密码和 Authenticator 6 位码。');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-white px-4 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-blue-500" />
            BRC Operator Console
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 p-4">
          <div>
            <h1 className="text-base font-bold">Owner 登录</h1>
            <p className="mt-1 text-xs leading-5 text-zinc-500">
              使用账号、密码和 Google Authenticator。控制台不会保存交易密钥或 Authenticator secret。
            </p>
          </div>
          <form className="space-y-3" onSubmit={submit}>
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">账号</span>
              <input
                className="mt-1 w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
              />
            </label>
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">密码</span>
              <input
                className="mt-1 w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
              />
            </label>
            <label className="block">
              <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">Authenticator 6 位码</span>
              <input
                className="mt-1 w-full rounded-sm border border-zinc-300 bg-white px-3 py-2 text-sm tracking-[0.3em] outline-none focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
                value={totpCode}
                onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                inputMode="numeric"
                autoComplete="one-time-code"
              />
            </label>
            {error && (
              <div className="rounded-sm border border-rose-500/20 bg-rose-500/[0.04] px-3 py-2 text-xs leading-5 text-rose-500">
                {error}
              </div>
            )}
            <button
              className="flex w-full items-center justify-center gap-2 rounded-sm border border-blue-500 bg-blue-600 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-60"
              disabled={loading}
            >
              <KeyRound className="h-3.5 w-3.5" />
              {loading ? '登录中' : '进入控制台'}
            </button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
