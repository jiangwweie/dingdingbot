import { useEffect, useState } from 'react';
import { getAuthProviders, startGoogleBinding, getGoogleBinding } from '../../api/authApi';

export function GoogleLogin() {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    let mounted = true;
    getAuthProviders().then(p => { if (mounted) setEnabled(p.google_login); }).catch(() => {});
    return () => { mounted = false; };
  }, []);
  const denied = new URLSearchParams(window.location.search).get('google_result') === 'error';
  return <>
    {denied && <p role="alert" className="mb-3 text-xs text-danger">Google 登录未完成或身份不匹配。请重试或使用原登录方式。</p>}
    {enabled && <div className="mb-4 space-y-2">
      <a href="/api/owner/v1/auth/google/start" className="block rounded border border-border bg-surface-subtle px-4 py-2.5 text-center text-sm font-semibold text-text-primary hover:bg-surface-elevated">使用 Google 登录</a>
      <p className="text-[11px] text-text-muted">仅限已绑定的 Owner Google 账号；敏感控制仍需 TOTP。</p>
      <p className="pt-2 text-center text-[11px] text-text-muted">或使用原账号应急登录</p>
    </div>}
  </>;
}

export function GoogleOwnerBinding() {
  const [enabled, setEnabled] = useState(false);
  const [totp, setTotp] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<{ subject: string; email: string } | null>(null);
  useEffect(() => {
    let mounted = true;
    getAuthProviders().then(p => { if (mounted) setEnabled(p.google_binding); }).catch(() => {});
    if (new URLSearchParams(window.location.search).get('google_result') === 'binding') {
      getGoogleBinding().then(c => { if (mounted) setCandidate(c); }).catch(() => { if (mounted) setError('绑定身份已过期，请重新验证。'); });
    }
    return () => { mounted = false; };
  }, []);
  if (!enabled) return null;
  async function begin() {
    if (busy || !/^\d{6}$/.test(totp)) return;
    setBusy(true); setError(null);
    try { window.location.assign(await startGoogleBinding(totp)); }
    catch { setError('无法开始 Google 绑定，请检查 TOTP 或重新登录。'); setBusy(false); }
  }
  return <section aria-label="Google Owner 身份绑定" className="mx-auto my-4 max-w-[1480px] rounded border border-border bg-surface p-4 text-xs">
    <h2 className="font-semibold text-text-primary">绑定 Owner Google 账号</h2>
    {candidate ? <div className="mt-2 space-y-2 text-text-secondary">
      <p>Google 身份已验证。尚未启用 Google 登录，需将以下固定身份标识写入服务器认证配置。</p>
      <p>账号：{candidate.email}</p><p>Owner subject：<code className="select-all">{candidate.subject}</code></p>
      <p>此标识不是密钥。Client Secret 仍由 Owner 保管，不应粘贴到聊天中。</p>
    </div> : <div className="mt-2 flex flex-wrap items-center gap-2">
      <p className="w-full text-text-muted">原会话与 TOTP 确认后前往 Google，只读取身份标识与邮箱；不会改变交易控制。</p>
      <input aria-label="Google 绑定 TOTP" autoComplete="one-time-code" inputMode="numeric" maxLength={6} value={totp} disabled={busy}
        onChange={e => setTotp(e.target.value.replace(/\D/g, ''))} placeholder="6 位 TOTP" className="rounded border border-border bg-background p-2 text-text-primary" />
      <button type="button" disabled={busy || !/^\d{6}$/.test(totp)} onClick={begin} className="rounded bg-brand px-3 py-2 text-white disabled:opacity-50">{busy ? '正在验证…' : '验证并绑定 Google'}</button>
    </div>}
    {error && <p role="alert" className="mt-2 text-danger">{error}</p>}
  </section>;
}
