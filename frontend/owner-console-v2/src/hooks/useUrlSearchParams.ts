import { useState, useEffect, useCallback, useRef } from 'react';
import {
  parseTradesSearchParams,
  serializeTradesSearchParams,
  parseStrategiesSearchParams,
  serializeStrategiesSearchParams,
  parseReviewSearchParams,
  serializeReviewSearchParams,
  type TradesFilterParams,
  type StrategiesFilterParams,
  type ReviewFilterParams,
} from '../utils/urlParams.ts';
import { calculatePresetWindow } from '../utils/timeRange.ts';

/**
 * Hook to manage Trades filters synchronized with window.location.search and popstate.
 */
export function useTradesFilterState() {
  const [filters, setFiltersInternal] = useState<TradesFilterParams>(() => {
    if (typeof window === 'undefined') {
      const defWin = calculatePresetWindow('30d');
      return {
        range: '30d',
        from_ms: defWin.from_ms,
        to_ms: defWin.to_ms,
        filter_mode: 'all',
      };
    }
    return parseTradesSearchParams(new URLSearchParams(window.location.search));
  });

  useEffect(() => {
    const current=new URLSearchParams(window.location.search);
    if (!current.has('from_ms') || !current.has('to_ms')) {
      current.set('from_ms', String(filters.from_ms)); current.set('to_ms', String(filters.to_ms));
      window.history.replaceState(null, '', `${window.location.pathname}?${current}`);
    }
  }, []);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  // Listen to browser forward/back popstate
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const onPopState = () => {
      const next = parseTradesSearchParams(new URLSearchParams(window.location.search));
      filtersRef.current = next;
      setFiltersInternal(next);
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const setFilters = useCallback(
    (
      updater:
        | Partial<TradesFilterParams>
        | ((prev: TradesFilterParams) => Partial<TradesFilterParams>),
      replace: boolean = false
    ) => {
      const prev = filtersRef.current;
      const patch = typeof updater === 'function' ? updater(prev) : updater;
      const next: TradesFilterParams = { ...prev, ...patch };
      filtersRef.current = next;

      if (typeof window !== 'undefined') {
        const searchStr = serializeTradesSearchParams(next);
        const currentSearch = window.location.search.replace(/^\?/, '');
        if (searchStr !== currentSearch) {
          const newUrl = `${window.location.pathname}?${searchStr}`;
          if (replace) {
            window.history.replaceState(null, '', newUrl);
          } else {
            window.history.pushState(null, '', newUrl);
          }
        }
      }
      setFiltersInternal(next);
    },
    []
  );

  const resetFilters = useCallback(() => {
    const defWin = calculatePresetWindow('30d');
    setFilters({
      range: '30d',
      from_ms: defWin.from_ms,
      to_ms: defWin.to_ms,
      strategy_group_id: undefined,
      exchange_instrument_id: undefined,
      position_side: undefined,
      aggregate_status: undefined,
      filter_mode: 'all',
    });
  }, [setFilters]);

  return {
    filters,
    setFilters,
    resetFilters,
  };
}

/**
 * Hook to manage Strategies filters synchronized with window.location.search and popstate.
 */
export function useStrategiesFilterState() {
  const [filters, setFiltersInternal] = useState<StrategiesFilterParams>(() => {
    if (typeof window === 'undefined') {
      const defWin = calculatePresetWindow('30d');
      return {
        view: 'all',
        range: '30d',
        from_ms: defWin.from_ms,
        to_ms: defWin.to_ms,
        scope: 'all',
      };
    }
    return parseStrategiesSearchParams(new URLSearchParams(window.location.search));
  });

  useEffect(() => {
    const current=new URLSearchParams(window.location.search);
    if (!current.has('from_ms') || !current.has('to_ms')) {
      current.set('from_ms', String(filters.from_ms)); current.set('to_ms', String(filters.to_ms));
      window.history.replaceState(null, '', `${window.location.pathname}?${current}`);
    }
  }, []);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  // Listen to browser forward/back popstate
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const onPopState = () => {
      const next = parseStrategiesSearchParams(new URLSearchParams(window.location.search));
      filtersRef.current = next;
      setFiltersInternal(next);
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const setFilters = useCallback(
    (
      updater:
        | Partial<StrategiesFilterParams>
        | ((prev: StrategiesFilterParams) => Partial<StrategiesFilterParams>),
      replace: boolean = false
    ) => {
      const prev = filtersRef.current;
      const patch = typeof updater === 'function' ? updater(prev) : updater;
      const next: StrategiesFilterParams = { ...prev, ...patch };
      filtersRef.current = next;

      if (typeof window !== 'undefined') {
        const searchStr = serializeStrategiesSearchParams(next);
        const currentSearch = window.location.search.replace(/^\?/, '');
        if (searchStr !== currentSearch) {
          const newUrl = `${window.location.pathname}?${searchStr}`;
          if (replace) {
            window.history.replaceState(null, '', newUrl);
          } else {
            window.history.pushState(null, '', newUrl);
          }
        }
      }
      setFiltersInternal(next);
    },
    []
  );

  const resetFilters = useCallback(() => {
    const defWin = calculatePresetWindow('30d');
    setFilters({
      view: 'all',
      range: '30d',
      from_ms: defWin.from_ms,
      to_ms: defWin.to_ms,
      strategy_version_id: undefined,
      drawer_tab: undefined,
      scope: 'all',
      exit_path: undefined,
      first_path: undefined,
    });
  }, [setFilters]);

  return {
    filters,
    setFilters,
    resetFilters,
  };
}

/**
 * Hook to manage Review filters synchronized with window.location.search and popstate.
 */
export function useReviewFilterState() {
  const [filters, setFiltersInternal] = useState<ReviewFilterParams>(() => {
    if (typeof window === 'undefined') {
      const defWin = calculatePresetWindow('30d');
      return {
        range: '30d',
        from_ms: defWin.from_ms,
        to_ms: defWin.to_ms,
      };
    }
    return parseReviewSearchParams(new URLSearchParams(window.location.search));
  });

  useEffect(() => {
    const current=new URLSearchParams(window.location.search);
    if (!current.has('from_ms') || !current.has('to_ms')) {
      current.set('from_ms', String(filters.from_ms)); current.set('to_ms', String(filters.to_ms));
      window.history.replaceState(null, '', `${window.location.pathname}?${current}`);
    }
  }, []);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const onPopState = () => {
      const next = parseReviewSearchParams(new URLSearchParams(window.location.search));
      filtersRef.current = next;
      setFiltersInternal(next);
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const setFilters = useCallback(
    (
      updater:
        | Partial<ReviewFilterParams>
        | ((prev: ReviewFilterParams) => Partial<ReviewFilterParams>),
      replace: boolean = false
    ) => {
      const prev = filtersRef.current;
      const patch = typeof updater === 'function' ? updater(prev) : updater;
      const next: ReviewFilterParams = { ...prev, ...patch };
      filtersRef.current = next;

      if (typeof window !== 'undefined') {
        const searchStr = serializeReviewSearchParams(next);
        const currentSearch = window.location.search.replace(/^\?/, '');
        if (searchStr !== currentSearch) {
          const newUrl = `${window.location.pathname}?${searchStr}`;
          if (replace) {
            window.history.replaceState(null, '', newUrl);
          } else {
            window.history.pushState(null, '', newUrl);
          }
        }
      }
      setFiltersInternal(next);
    },
    []
  );

  const resetFilters = useCallback(() => {
    const defWin = calculatePresetWindow('30d');
    setFilters({
      range: '30d',
      from_ms: defWin.from_ms,
      to_ms: defWin.to_ms,
      review_status: undefined,
      strategy_group_id: undefined,
    });
  }, [setFilters]);

  return {
    filters,
    setFilters,
    resetFilters,
  };
}
