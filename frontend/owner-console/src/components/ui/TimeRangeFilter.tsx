import type { ChangeEvent } from "react";

export interface TimeRangeValue {
  from_ms?: number | undefined;
  to_ms?: number | undefined;
}

interface TimeRangeFilterProps {
  value: TimeRangeValue;
  onChange: (value: TimeRangeValue) => void;
}

const inputClass = "h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]";

function toLocalInputValue(value: number | undefined): string {
  if (value === undefined) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function toTimestamp(value: string): number | undefined {
  if (!value) return undefined;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? undefined : timestamp;
}

function todayStart(now: Date): number {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  return start.getTime();
}

export function TimeRangeFilter({ value, onChange }: TimeRangeFilterProps) {
  const applyPreset = (range: "today" | "24h" | "7d" | "30d") => {
    const now = new Date();
    const to_ms = now.getTime();
    const from_ms = range === "today"
      ? todayStart(now)
      : to_ms - ({ "24h": 86_400_000, "7d": 7 * 86_400_000, "30d": 30 * 86_400_000 }[range] ?? 0);
    onChange({ from_ms, to_ms });
  };

  const updateBoundary = (boundary: "from_ms" | "to_ms") => (event: ChangeEvent<HTMLInputElement>) => {
    const next = toTimestamp(event.target.value);
    const candidate = { ...value, [boundary]: next };
    if (candidate.from_ms !== undefined && candidate.to_ms !== undefined && candidate.from_ms >= candidate.to_ms) {
      onChange(boundary === "from_ms" ? { from_ms: next } : { to_ms: next });
      return;
    }
    onChange(candidate);
  };

  return (
    <fieldset className="col-span-full grid gap-2 border-0 p-0" aria-label="时间范围">
      <legend className="sr-only">时间范围</legend>
      <div className="flex flex-wrap items-center gap-1">
        <span className="mr-1 text-[11px] text-[var(--color-text-secondary)]">时间范围</span>
        {(["today", "24h", "7d", "30d"] as const).map((range) => (
          <button className="owner-button h-7 px-2 text-[11px]" key={range} type="button" onClick={() => applyPreset(range)}>
            {{ today: "今日", "24h": "近 24h", "7d": "近 7 天", "30d": "近 30 天" }[range]}
          </button>
        ))}
        {(value.from_ms !== undefined || value.to_ms !== undefined) ? <button className="ml-1 bg-transparent p-1 text-[11px] text-[var(--color-text-secondary)] hover:text-[var(--color-emphasis)]" type="button" onClick={() => onChange({})}>清除</button> : null}
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">
          开始时间
          <input aria-label="开始时间" className={inputClass} type="datetime-local" value={toLocalInputValue(value.from_ms)} onChange={updateBoundary("from_ms")} />
        </label>
        <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">
          结束时间
          <input aria-label="结束时间" className={inputClass} type="datetime-local" value={toLocalInputValue(value.to_ms)} onChange={updateBoundary("to_ms")} />
        </label>
      </div>
      <small className="text-[10px] text-[var(--color-text-secondary)]">按上海时间查看，最长 90 天</small>
    </fieldset>
  );
}
