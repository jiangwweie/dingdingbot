export interface Envelope<T> {
  read_model: string;
  generated_at_ms: number;
  source: string;
  freshness_status: 'fresh' | 'warning' | 'degraded' | 'not_live_connected' | 'unknown';
  warnings: Array<{ code: string, severity: string, message: string, count: number }>;
  blockers: Array<{ code: string, message: string, affected_area?: string }>;
  unavailable: Array<{ source: string, code: string, error?: string }>;
  data: T;
  no_action_guarantee: Record<string, boolean>;
  live_ready: boolean;
}
