import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { StatusTag, type StatusTone } from "../components/ui/StatusTag";

const navigationItems = [
  { label: "总览", to: "/overview" },
  { label: "信号", to: "/signals" },
  { label: "交易", to: "/trades" },
  { label: "复盘", to: "/review" },
] as const;

interface AppShellProps {
  children: ReactNode;
  dataTime: ReactNode;
  statusLabel: string;
  statusTone: StatusTone;
}

export function AppShell({ children, dataTime, statusLabel, statusTone }: AppShellProps) {
  return (
    <>
      <header className="top-navigation">
        <div className="app-container top-navigation__inner">
          <Link className="brand-mark brand-mark--link" to="/overview">
            BRC OWNER
          </Link>
          <nav className="primary-navigation" aria-label="一级导航">
            {navigationItems.map((item) => (
              <NavLink className="primary-navigation__link" to={item.to} key={item.to}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="runtime-summary" aria-label="运行摘要">
            <span className="tabular-number">PROD</span>
            <span className="runtime-summary__separator" aria-hidden="true">
              ·
            </span>
            <StatusTag tone={statusTone}>{statusLabel}</StatusTag>
            <span className="runtime-summary__separator runtime-summary__time" aria-hidden="true">
              ·
            </span>
            <span className="runtime-summary__time tabular-number">{dataTime}</span>
          </div>
        </div>
      </header>
      <main className="app-container owner-main">{children}</main>
    </>
  );
}
