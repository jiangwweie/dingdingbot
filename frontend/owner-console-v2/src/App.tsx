import { incomeNavigationSearch } from './utils/urlParams';
import React, { useState, useEffect } from 'react';
import { useAuth } from './hooks/useAuth';
import { LoginPage } from './components/auth/LoginPage';
import { Navbar, type NavTabId } from './components/Navbar';
import { OverviewPage } from './components/overview/OverviewPage';
import { TradesPage } from './components/trades/TradesPage';
import { StrategiesPage } from './components/strategies/StrategiesPage';
import { ReviewPage } from './components/review/ReviewPage';
import { ControlsPage } from './components/ControlsPage';
import { GoogleOwnerBinding } from './components/auth/GoogleAuth';
import { AlertCircle } from 'lucide-react';

const getInitialTab = (): NavTabId => {
  if (typeof window !== 'undefined') {
    const tab = new URLSearchParams(window.location.search).get('tab');
    if (tab === 'trades' || tab === 'strategies' || tab === 'controls' || tab === 'overview' || tab === 'review') {
      return tab;
    }
  }
  return 'overview';
};

export const App: React.FC = () => {
  const {
    isAuthenticated,
    isLoading: isCheckingSession,
    login,
    isLoggingIn,
    loginError,
    logout,
    isLoggingOut,
    logoutError,
    isLogoutUnconfirmed,
    acknowledgeUnconfirmedSession,
  } = useAuth();

  const [activeTab, setActiveTab] = useState<NavTabId>(getInitialTab);

  // Synchronize activeTab with browser URL search params on popstate
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const onPopState = () => {
      const tab = new URLSearchParams(window.location.search).get('tab');
      if (tab === 'trades' || tab === 'strategies' || tab === 'controls' || tab === 'overview' || tab === 'review') {
        setActiveTab(tab);
      } else {
        setActiveTab('overview');
      }
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const handleSelectTab = (tab: NavTabId) => {
    if (typeof window !== 'undefined') {
      const sp = new URLSearchParams(window.location.search);
      if (sp.get('tab') !== tab) {
        const search = incomeNavigationSearch(window.location.search, tab);
        window.history.pushState(null, '', `${window.location.pathname}?${search}`);
      }
    }
    setActiveTab(tab);
  };

  const handleNavigateWithSearch = (tab: NavTabId, search: string) => {
    if (typeof window !== 'undefined') {
      window.history.pushState(null, '', `${window.location.pathname}?${search}`);
    }
    setActiveTab(tab);
  };

  // 1. Session Verification View
  if (isCheckingSession) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
        <div className="h-8 w-8 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
        <p className="text-xs font-semibold text-text-primary">正在验证 Owner 会话...</p>
        <span className="text-[11px] text-text-muted mt-1">GET /api/owner/v1/auth/session</span>
      </div>
    );
  }

  // 2. Unconfirmed Logout Screen
  if (isLogoutUnconfirmed) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
        <div className="max-w-md w-full rounded-lg border border-danger/40 bg-surface p-6 shadow-xl text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-danger/10 text-danger mb-4 border border-danger/20">
            <AlertCircle className="h-6 w-6" />
          </div>
          <h2 className="text-base font-bold text-text-primary">
            服务端退出未确认
          </h2>
          <p className="mt-2 text-xs text-text-secondary leading-relaxed">
            {logoutError ?? '此前退出请求未获得服务端有效性注销确认。为保障交易安全，当前页面已进行隐私遮蔽。'}
          </p>
          <div className="mt-6 flex flex-col gap-2.5">
            <button
              type="button"
              disabled={isLoggingOut}
              onClick={() => logout()}
              className="w-full rounded bg-danger px-4 py-2 text-xs font-bold text-white hover:bg-danger/90 transition-colors shadow-xs cursor-pointer flex items-center justify-center gap-2"
            >
              {isLoggingOut ? '正在重试注销...' : '重试退出服务端会话 (POST /auth/logout)'}
            </button>
            <button
              type="button"
              onClick={acknowledgeUnconfirmedSession}
              className="w-full rounded border border-border bg-surface-subtle px-4 py-2 text-xs font-semibold text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors cursor-pointer"
            >
              忽略警告并进入控制台
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 3. Unauthenticated -> Show Login Page
  if (!isAuthenticated) {
    return <LoginPage onLogin={login} isLoading={isLoggingIn} error={loginError} />;
  }

  // 3. Authenticated Console
  return (
    <div className="min-h-screen bg-background text-text-primary">
      <Navbar
        activeTab={activeTab}
        onSelectTab={handleSelectTab}
        isRealData={true}
        onLogout={logout}
        isLoggingOut={isLoggingOut}
      />

      <GoogleOwnerBinding />
      <main className="mx-auto max-w-[1520px] px-4 py-4 sm:px-6">
        {activeTab === 'overview' && (
          <OverviewPage
            onNavigateToControls={() => handleSelectTab('controls')}
            onNavigateToTab={handleSelectTab}
            onNavigateWithSearch={handleNavigateWithSearch}
          />
        )}

        {activeTab === 'trades' && (
          <TradesPage />
        )}

        {activeTab === 'strategies' && (
          <StrategiesPage />
        )}

        {activeTab === 'review' && (
          <ReviewPage />
        )}

        {activeTab === 'controls' && (
          <ControlsPage />
        )}
      </main>
    </div>
  );
};
