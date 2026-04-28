import React from 'react';
import { cn } from '@/src/lib/utils';

export function Table({ className, ...props }: React.HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full flex-1 overflow-auto p-0">
      <table className={cn("w-full text-left border-collapse", className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("text-[10px] uppercase text-zinc-500 font-bold bg-zinc-50 dark:bg-zinc-900/80 sticky top-0 border-b border-zinc-200 dark:border-zinc-800 tracking-wider", className)} {...props} />;
}

export function TableBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("text-[11px] font-mono divide-y divide-zinc-200 dark:divide-zinc-800", className)} {...props} />;
}

export function TableRow({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("hover:bg-blue-50/50 dark:hover:bg-blue-900/10 transition-colors", className)} {...props} />;
}

export function TableHead({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("px-2.5 py-1.5 font-medium whitespace-nowrap", className)} {...props} />;
}

export function TableCell({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-2.5 py-1.5 whitespace-nowrap tabular-nums", className)} {...props} />;
}
