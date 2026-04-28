import React, { useState, useEffect, useRef } from 'react';
import { Settings2, Check } from 'lucide-react';
import { cn } from '@/src/lib/utils';

export interface ColumnDef {
  key: string;
  label: string;
  defaultVisible: boolean;
}

interface ColumnVisibilityProps {
  columns: ColumnDef[];
  storageKey: string;
  onChange: (visibleKeys: Set<string>) => void;
}

export function ColumnVisibility({ columns, storageKey, onChange }: ColumnVisibilityProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const [visible, setVisible] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        return new Set(JSON.parse(stored));
      }
    } catch (e) {
      // ignore
    }
    return new Set(columns.filter(c => c.defaultVisible).map(c => c.key));
  });

  useEffect(() => {
    onChange(visible);
    localStorage.setItem(storageKey, JSON.stringify(Array.from(visible)));
  }, [visible, storageKey]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleColumn = (key: string) => {
    setVisible(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        // Don't allow hiding all columns
        if (next.size > 1) {
          next.delete(key);
        }
      } else {
        next.add(key);
      }
      return next;
    });
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-200/50 dark:hover:bg-zinc-800/50 rounded-sm transition-colors border border-transparent hover:border-zinc-300 dark:hover:border-zinc-700"
        title="配置显示列"
      >
        <Settings2 className="w-3 h-3" />
        <span>列配置</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-48 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded shadow-xl z-50 py-1 flex flex-col">
          <div className="px-3 py-1.5 border-b border-zinc-100 dark:border-zinc-800 text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
            显示/隐藏列
          </div>
          <div className="max-h-64 overflow-y-auto p-1">
            {columns.map(col => {
              const isVisible = visible.has(col.key);
              return (
                <button
                  key={col.key}
                  onClick={() => toggleColumn(col.key)}
                  className="w-full flex items-center justify-between px-2 py-1.5 text-xs text-left rounded-sm hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                >
                  <span className={cn(isVisible ? 'text-zinc-900 dark:text-zinc-100 font-medium' : 'text-zinc-500')}>{col.label}</span>
                  {isVisible && <Check className="w-3.5 h-3.5 text-blue-500" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
