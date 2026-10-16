import { type ReactNode, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { StatusTag, type StatusTone } from "../components/ui/StatusTag";
import { logout } from "../features/auth/api";
import { ownerQueryClient } from "./queryClient";

const navigationItems = [
  { label: "总览", to: "/overview" },
  { label: "信号", to: "/signals" },
  { label: "交易", to: "/trades" },
  { label: "策略", to: "/strategies" },
  { label: "标的", to: "/instruments" },
  { label: "复盘", to: "/review" },
  { label: "控制", to: "/controls" },
] as const;

interface AppShellProps {
  children: ReactNode;
  dataTime: ReactNode;
  statusLabel: string;
  statusTone: StatusTone;
}

export function AppShell({ children, dataTime, statusLabel, statusTone }: AppShellProps) {
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
      ownerQueryClient.clear();
      navigate("/login", { replace: true });
    } finally {
      setIsLoggingOut(false);
    }
  };
  return (
    <>
      <header className="top-navigation">
        <div className="app-container top-navigation__inner">
          <Link className="brand-mark brand-mark--link" to="/overview">
            <svg
              className="h-4 w-4 text-[var(--color-emphasis)] flex-none transition-transform hover:scale-110"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M12 2L4 12l8 10 8-10L12 2zm0 4.236L17.412 12 12 18.764 6.588 12 12 6.236z" />
            </svg>
            <span>BRC OWNER</span>
          </Link>
          <nav className="primary-navigation" aria-label="一级导航">
            {navigationItems.map((item) => (
              <NavLink className="primary-navigation__link" to={item.to} key={item.to}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="runtime-summary" aria-label="运行摘要">
            <span className="tabular-number inline-flex items-center rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-bold text-emerald-400">
              PROD
            </span>
            <span className="runtime-summary__separator" aria-hidden="true">
              ·
            </span>
            <StatusTag tone={statusTone}>{statusLabel}</StatusTag>
            <span className="runtime-summary__separator runtime-summary__time" aria-hidden="true">
              ·
            </span>
            <span className="runtime-summary__time tabular-number text-[var(--color-text-secondary)]">{dataTime}</span>
            <button className="runtime-summary__logout" disabled={isLoggingOut} type="button" onClick={() => void handleLogout()}>
              {isLoggingOut ? "退出中" : "退出"}
            </button>
          </div>
        </div>
      </header>
      <main className="app-container owner-main">{children}</main>
    </>
  );
}
