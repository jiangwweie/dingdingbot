import { useState, useMemo, useCallback } from 'react';

// ── Sort direction ────────────────────────────────────────────
export type SortOrder = 'asc' | 'desc';

// ── useTableSort ──────────────────────────────────────────────
/** Minimal sort state + toggle for table columns. */
export function useTableSort<T>(
  defaultField: keyof T & string,
  defaultOrder: SortOrder = 'desc',
) {
  const [sortField, setSortField] = useState<string>(defaultField);
  const [sortOrder, setSortOrder] = useState<SortOrder>(defaultOrder);

  const toggleSort = useCallback((field: string) => {
    setSortField(prev => {
      if (prev === field) {
        setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
        return prev;
      }
      setSortOrder('desc');
      return field;
    });
  }, []);

  const sortIndicator = useCallback(
    (field: string) => {
      if (sortField !== field) return '';
      return sortOrder === 'asc' ? ' ↑' : ' ↓';
    },
    [sortField, sortOrder],
  );

  const setSort = useCallback((field: string, order: SortOrder) => {
    setSortField(field);
    setSortOrder(order);
  }, []);

  return { sortField, sortOrder, toggleSort, sortIndicator, setSort };
}

// ── Comparator helpers ────────────────────────────────────────
/** Compare two values, handling null/undefined by pushing them to the end. */
export function comparePrimitive(a: unknown, b: unknown, order: SortOrder): number {
  const aNull = a == null;
  const bNull = b == null;
  if (aNull && bNull) return 0;
  if (aNull) return 1; // nulls sink
  if (bNull) return -1;

  let cmp: number;
  if (typeof a === 'number' && typeof b === 'number') {
    cmp = a - b;
  } else if (typeof a === 'string' && typeof b === 'string') {
    cmp = a.localeCompare(b);
  } else {
    cmp = String(a).localeCompare(String(b));
  }
  return order === 'asc' ? cmp : -cmp;
}

/** Compare ISO timestamp strings by actual time value. Invalid dates sink. */
export function compareTimestamp(a: string | null | undefined, b: string | null | undefined, order: SortOrder): number {
  const ta = a ? new Date(a).getTime() : NaN;
  const tb = b ? new Date(b).getTime() : NaN;
  const aInvalid = isNaN(ta);
  const bInvalid = isNaN(tb);
  if (aInvalid && bInvalid) return 0;
  if (aInvalid) return 1;
  if (bInvalid) return -1;
  const cmp = ta - tb;
  return order === 'asc' ? cmp : -cmp;
}

// ── FilterSelect ──────────────────────────────────────────────
const SELECT_CLS =
  'bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded px-2 py-1 text-xs font-mono text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500';

interface FilterSelectProps {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}

/** Lightweight filter dropdown styled for the console observation bar. */
export function FilterSelect({ value, onChange, options }: FilterSelectProps) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className={SELECT_CLS}
    >
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

// ── Empty state helpers ───────────────────────────────────────
/** "No results after filtering" table row. */
export function EmptyFilterRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-6 text-center text-zinc-500 text-sm">
        筛选后无匹配结果
      </td>
    </tr>
  );
}

/** Full-width card for "no data at all" state. */
export function emptyDataCard(message: string = '暂无数据') {
  return (
    <div className="py-10 text-center text-zinc-500">{message}</div>
  );
}
