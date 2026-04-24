import React from 'react';
import { cn } from '@/src/lib/utils';

interface BadgeProps extends React.ComponentProps<'span'> {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'outline';
  children?: React.ReactNode;
  className?: string;
}

export function Badge({ className, variant = 'default', children, ...props }: BadgeProps) {
  const variants = {
    default: "bg-zinc-100 dark:bg-zinc-800 text-zinc-500 border-zinc-300 dark:border-zinc-700",
    success: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
    warning: "bg-amber-500/10 text-amber-500 border-amber-500/20",
    danger: "bg-rose-500/10 text-rose-500 border-rose-500/20",
    info: "bg-blue-500/10 text-blue-500 border-blue-500/20",
    outline: "bg-transparent text-zinc-600 dark:text-zinc-400 border-zinc-300 dark:border-zinc-700",
  };

  return (
    <span 
      className={cn("px-1.5 py-0.5 text-[10px] uppercase font-bold rounded-sm border inline-flex items-center whitespace-nowrap font-sans tracking-wide", variants[variant], className)}
      {...props}
    >
      {children}
    </span>
  );
}
