import React from 'react';
import { cn } from '@/src/lib/utils';

export function Card({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-sm flex flex-col shadow-sm text-sm", className)} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("px-3 py-2 border-b border-zinc-200 dark:border-zinc-800/80 flex items-center justify-between bg-zinc-50/50 dark:bg-zinc-900/50", className)}>
      {children}
    </div>
  );
}

export function CardTitle({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <h3 className={cn("text-[10px] font-bold uppercase tracking-widest text-zinc-500 dark:text-zinc-400", className)}>
      {children}
    </h3>
  );
}

export function CardContent({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("p-2.5 flex-1 overflow-hidden", className)}>
      {children}
    </div>
  );
}
