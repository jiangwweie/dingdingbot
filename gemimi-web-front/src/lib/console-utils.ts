/**
 * Shared formatting and status utilities for the observation console.
 *
 * Single source of truth for:
 * - Status badge mapping (Runtime health, Research review)
 * - Number/time formatting (percentages, decimals, timestamps)
 * - Missing-value display
 */

// ─── Missing value ────────────────────────────────────────────

export const DASH = '--';

export function fmtDash(val: unknown): string {
  return val === null || val === undefined || val === '' ? DASH : String(val);
}

// ─── Number formatting ────────────────────────────────────────

/** Format a ratio (0.45) as percentage string "45.0%". Null → "--". */
export function fmtPct(val: number | null | undefined): string {
  if (val === null || val === undefined) return DASH;
  return `${(val * 100).toFixed(1)}%`;
}

/** Format a decimal with fixed precision. Null → "--". */
export function fmtDec(val: number | null | undefined, digits = 2): string {
  if (val === null || val === undefined) return DASH;
  return val.toFixed(digits);
}

/** Format an integer. Null → "--". */
export function fmtInt(val: number | null | undefined): string {
  if (val === null || val === undefined) return DASH;
  return Math.round(val).toString();
}

// ─── Time formatting ──────────────────────────────────────────

/** Compact time for tables: "HH:mm:ss" */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return DASH;
    return d.toTimeString().slice(0, 8);
  } catch {
    return DASH;
  }
}

/** Short datetime for lists: "yyyy-MM-dd HH:mm" */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return DASH;
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return DASH;
  }
}

/** Full datetime for detail views: "yyyy-MM-dd HH:mm:ss" */
export function fmtDateTimeFull(iso: string | null | undefined): string {
  if (!iso) return DASH;
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return DASH;
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  } catch {
    return DASH;
  }
}

// ─── Runtime health status ────────────────────────────────────

export type RuntimeHealthStatus = 'OK' | 'DEGRADED' | 'DOWN' | 'UNKNOWN';

export type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'outline';

/** Map runtime health status to badge variant. */
export function runtimeHealthVariant(status: string | null | undefined): BadgeVariant {
  switch (status) {
    case 'OK': return 'success';
    case 'DEGRADED': return 'warning';
    case 'DOWN': return 'danger';
    default: return 'default';
  }
}

/** Map runtime health status to display label. */
export function runtimeHealthLabel(status: string | null | undefined): string {
  switch (status) {
    case 'OK': return 'OK';
    case 'DEGRADED': return 'DEGRADED';
    case 'DOWN': return 'DOWN';
    case 'UNKNOWN': return 'UNKNOWN';
    default: return DASH;
  }
}

// ─── Freshness status ─────────────────────────────────────────

export function freshnessVariant(status: string | null | undefined): BadgeVariant {
  switch (status) {
    case 'Fresh': return 'success';
    case 'Stale': return 'warning';
    case 'Possibly Dead': return 'danger';
    default: return 'default';
  }
}

export function freshnessLabel(status: string | null | undefined): string {
  switch (status) {
    case 'Fresh': return 'Fresh';
    case 'Stale': return 'Stale';
    case 'Possibly Dead': return 'Possibly Dead';
    case 'UNKNOWN': return 'UNKNOWN';
    default: return DASH;
  }
}

// ─── Research review status ────────────────────────────────────

export function reviewStatusVariant(status: string | null | undefined): BadgeVariant {
  switch (status) {
    case 'PASS_STRICT': return 'success';
    case 'PASS_STRICT_WITH_WARNINGS': return 'warning';
    case 'PASS_LOOSE': return 'info';
    case 'REJECT': return 'danger';
    case 'PENDING': return 'default';
    default: return 'default';
  }
}

export function reviewStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'PASS_STRICT': return 'PASS STRICT';
    case 'PASS_STRICT_WITH_WARNINGS': return 'PASS (WARNINGS)';
    case 'PASS_LOOSE': return 'PASS LOOSE';
    case 'REJECT': return 'REJECT';
    case 'PENDING': return 'PENDING';
    default: return status ?? DASH;
  }
}

/** Strict gate result (PASSED / FAILED / PENDING) */
export function gateResultVariant(result: string | null | undefined): BadgeVariant {
  switch (result) {
    case 'PASSED': return 'success';
    case 'FAILED': return 'danger';
    case 'PENDING': return 'warning';
    default: return 'default';
  }
}