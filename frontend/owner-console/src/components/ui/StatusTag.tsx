import type { ReactNode } from "react";

export type StatusTone = "success" | "danger" | "attention" | "neutral";

interface StatusTagProps {
  children: ReactNode;
  tone?: StatusTone;
}

export function StatusTag({ children, tone = "neutral" }: StatusTagProps) {
  return (
    <span className="status-tag" data-tone={tone}>
      {children}
    </span>
  );
}
