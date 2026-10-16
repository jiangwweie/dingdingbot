import type { ReactNode } from "react";

interface InlineDetailRowProps {
  children: ReactNode;
  colSpan: number;
}

export function InlineDetailRow({ children, colSpan }: InlineDetailRowProps) {
  return (
    <tr className="border-b border-[var(--color-divider)] bg-[var(--color-surface-subtle)]">
      <td colSpan={colSpan} className="border-l-2 border-[var(--color-emphasis)] p-3 align-top shadow-inner">
        {children}
      </td>
    </tr>
  );
}
