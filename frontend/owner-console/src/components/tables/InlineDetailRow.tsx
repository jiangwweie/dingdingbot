import type { ReactNode } from "react";

interface InlineDetailRowProps {
  children: ReactNode;
  colSpan: number;
}

export function InlineDetailRow({ children, colSpan }: InlineDetailRowProps) {
  return (
    <tr className="border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)]">
      <td colSpan={colSpan} className="p-2 align-top">
        {children}
      </td>
    </tr>
  );
}
