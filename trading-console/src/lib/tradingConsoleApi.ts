import { useEffect, useState } from 'react';
import type { Envelope } from '@/types';

export type ReadModelState<T> = {
  envelope: Envelope<T> | null;
  loading: boolean;
  error: string | null;
};

const API_PREFIX = '/api/trading-console/';

export function useReadModel<T>(path: string): ReadModelState<T> {
  const [envelope, setEnvelope] = useState<Envelope<T> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(path, {
          method: 'GET',
          credentials: 'include',
        });
        if (response.status === 401) {
          window.dispatchEvent(new Event('trading-console:unauthorized'));
        }
        if (!response.ok) {
          throw new Error(`GET ${path} returned HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (active) setEnvelope(payload);
      } catch (err) {
        console.error('Trading Console read-only API error', { path, error: err });
        if (active) {
          setEnvelope(null);
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    if (!path.startsWith(API_PREFIX)) {
      setEnvelope(null);
      setError(`Forbidden Trading Console API path: ${path}`);
      setLoading(false);
      return;
    }

    load();
    return () => {
      active = false;
    };
  }, [path]);

  return { envelope, loading, error };
}

export function asArray<T = any>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

export function countItems(value: unknown): number {
  if (Array.isArray(value)) return value.length;
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && value.trim() !== '' && !Number.isNaN(Number(value))) return Number(value);
  return 0;
}

export function isNotAvailable(value: unknown): boolean {
  return value === null || value === undefined || value === '' || value === 'not_available' || value === 'unknown';
}

export function displayValue(value: unknown, fallback = '暂无数据'): string {
  if (isNotAvailable(value)) return fallback;
  return String(value);
}

export function actionSlotEntries(value: unknown): Array<{ name: string; status: string }> {
  if (Array.isArray(value)) {
    return value.map((name) => ({ name: String(name), status: 'deferred' }));
  }
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).map(([name, status]) => ({
      name,
      status: String(status),
    }));
  }
  return [];
}

export function formatTimestampMs(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '暂无';
  return new Date(value).toISOString();
}

export function hasUnsafeNoActionFlag(envelope: Envelope<any> | null): boolean {
  if (!envelope?.no_action_guarantee) return false;
  return Object.values(envelope.no_action_guarantee).some((value) => value !== false);
}
