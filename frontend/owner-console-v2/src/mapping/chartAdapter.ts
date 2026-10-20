import Decimal from 'decimal.js';
import { LineStyle, type CandlestickData, type LineWidth, type SeriesMarker, type UTCTimestamp } from 'lightweight-charts';
import type { components } from '../api/schema.d.ts';

export type CandleView = components['schemas']['CandleView'];
export type ChartAnnotation = components['schemas']['ChartAnnotation'];
export type TradeCausalityDetail = components['schemas']['TradeCausalityDetail'];
export type TradePricePlanView = components['schemas']['TradePricePlanView'];
export type StrategyObservationListItem = components['schemas']['StrategyObservationListItem'];
export type CandleTimeframe = '15m' | '1h';

export interface ChartPriceLevel {
  price: string;
  color: string;
  label: string;
  lineStyle?: LineStyle;
  lineWidth?: LineWidth;
}

export function isSamePrice(
  a: string | number | null | undefined,
  b: string | number | null | undefined
): boolean {
  if (a === null || a === undefined || b === null || b === undefined || a === '' || b === '') {
    return false;
  }
  try {
    const decA = new Decimal(a);
    const decB = new Decimal(b);
    return decA.equals(decB);
  } catch {
    return false;
  }
}

export function toChartNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) throw new Error('missing chart coordinate');
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`invalid chart coordinate: ${value}`);
  return parsed;
}

export function formatChartPrice(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const str = String(value);
  const [integerPart = '0', rawDecimal] = str.split('.');
  const sign = integerPart.startsWith('-') ? '-' : '';
  const digits = sign ? integerPart.slice(1) : integerPart;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  if (rawDecimal === undefined) {
    return `${sign}${grouped}`;
  }
  let trimmed = rawDecimal.replace(/0+$/, '');
  if (trimmed.length < 2 && rawDecimal.length >= 2) {
    trimmed = rawDecimal.slice(0, 2);
  } else if (trimmed.length === 0) {
    trimmed = rawDecimal;
  }
  return `${sign}${grouped}.${trimmed}`;
}

export function toCandlestickData(candles: CandleView[]): CandlestickData<UTCTimestamp>[] {
  const result: CandlestickData<UTCTimestamp>[] = [];
  const seenTimes = new Set<number>();

  for (const candle of candles) {
    const time = Math.floor(candle.open_time_ms / 1000) as UTCTimestamp;
    if (seenTimes.has(time)) continue; // prevent duplicate timestamps
    seenTimes.add(time);

    result.push({
      time,
      open: toChartNumber(candle.open),
      high: toChartNumber(candle.high),
      low: toChartNumber(candle.low),
      close: toChartNumber(candle.close),
    });
  }

  return result.sort((a, b) => (a.time as number) - (b.time as number));
}

const markerColor: Record<ChartAnnotation['kind'], string> = {
  signal: '#FCD535',
  entry: '#0ECB81',
  stop: '#F6465D',
  take_profit: '#14B8A6',
  exit: '#F6465D',
};

export function isAnnotationInCandles(annotation: ChartAnnotation, candles: CandleView[]): boolean {
  if (!candles || candles.length === 0 || !Number.isFinite(annotation.occurred_at_ms)) {
    return false;
  }
  return candles.some((c) => {
    const openMs = c.open_time_ms;
    const closeMs = c.close_time_ms && c.close_time_ms > openMs ? c.close_time_ms : openMs + 1000;
    return annotation.occurred_at_ms >= openMs && annotation.occurred_at_ms <= closeMs;
  });
}

export function getOutOfWindowAnnotations(
  annotations: ChartAnnotation[],
  candles?: CandleView[]
): ChartAnnotation[] {
  if (!annotations || annotations.length === 0 || !candles || candles.length === 0) return [];
  return annotations.filter((annotation) => !isAnnotationInCandles(annotation, candles));
}

export function toSeriesMarkers(
  annotations: ChartAnnotation[],
  candles?: CandleView[]
): SeriesMarker<UTCTimestamp>[] {
  if (!annotations || annotations.length === 0) return [];

  const markers: SeriesMarker<UTCTimestamp>[] = [];

  for (const annotation of annotations) {
    if (!Number.isFinite(annotation.occurred_at_ms)) continue;

    let timeSec: number | null = null;

    if (candles && candles.length > 0) {
      // Find the candle bar whose time range covers the annotation
      const matching = candles.find((c) => {
        const openMs = c.open_time_ms;
        const closeMs = c.close_time_ms && c.close_time_ms > openMs ? c.close_time_ms : openMs + 1000;
        return annotation.occurred_at_ms >= openMs && annotation.occurred_at_ms <= closeMs;
      });

      if (matching) {
        timeSec = Math.floor(matching.open_time_ms / 1000);
      } else {
        // Event is outside the available candles window.
        // P1-1 REQUIREMENT: Strictly prohibit nearest-neighbor snapping (e.g. 1000ms onto 100000ms).
        // Skip plotting this marker on a false candlestick bar.
        continue;
      }
    } else {
      timeSec = Math.floor(annotation.occurred_at_ms / 1000);
    }

    if (timeSec === null) continue;

    const isAbove = annotation.kind === 'stop' || annotation.kind === 'exit';
    const isArrowUp = annotation.kind === 'entry' || annotation.kind === 'signal';
    const isArrowDown = annotation.kind === 'stop' || annotation.kind === 'exit';

    markers.push({
      time: timeSec as UTCTimestamp,
      position: isAbove ? 'aboveBar' : 'belowBar',
      color: markerColor[annotation.kind] ?? '#848E9C',
      shape: isArrowUp ? 'arrowUp' : isArrowDown ? 'arrowDown' : 'circle',
      text: `${annotation.label} · ${formatChartPrice(annotation.price)}`,
    });
  }

  // Lightweight charts strictly requires markers to be sorted by time ascending
  return markers.sort((a, b) => (a.time as number) - (b.time as number));
}

export function computeChartWindow(input: {
  data: TradeCausalityDetail;
  generatedAt?: string | null;
  timeframe: CandleTimeframe;
}): { closedAtMs: number; limit: number } {
  const barMs = input.timeframe === '1h' ? 3_600_000 : 900_000;
  const signalAtMs =
    input.data.annotations.find((item) => item.kind === 'signal')?.occurred_at_ms ??
    input.data.trade.issued_at_ms;

  const generatedAtMs = input.generatedAt ? Date.parse(input.generatedAt) : NaN;
  const observedAtMs = Number.isFinite(generatedAtMs) ? generatedAtMs : signalAtMs;

  // Filter valid modern annotation timestamps to avoid corrupted epoch like 1000ms distorting limits
  const validTimes = input.data.annotations
    .map((a) => a.occurred_at_ms)
    .filter((t) => Number.isFinite(t) && t > 1_000_000_000_000);

  const startAnchorMs = validTimes.length > 0
    ? Math.min(signalAtMs, ...validTimes)
    : signalAtMs;

  const terminalOrObserved = input.data.trade.terminal_at_ms ?? observedAtMs;
  const endAnchorMs = validTimes.length > 0
    ? Math.max(terminalOrObserved, ...validTimes)
    : terminalOrObserved;

  const closedAtMs = endAnchorMs + 12 * barMs;
  const firstAtMs = startAnchorMs - 12 * barMs;

  return {
    closedAtMs,
    limit: Math.min(500, Math.max(48, Math.ceil((closedAtMs - firstAtMs) / barMs) + 1)),
  };
}

export function computeObservationChartWindow(obs: StrategyObservationListItem): {
  closedAtMs: number;
  limit: number;
} {
  const barMs = 900_000; // Observations use 15m bars
  const endMs = obs.completed_at_ms ?? obs.horizon_end_ms;
  const closedAtMs = endMs + 4 * barMs;
  const startMs = obs.occurred_at_ms || obs.horizon_start_ms;
  const firstAtMs = startMs - 4 * barMs;

  return {
    closedAtMs,
    limit: Math.min(500, Math.max(48, Math.ceil((closedAtMs - firstAtMs) / barMs) + 1)),
  };
}

export function ticketPriceLevels(plan: TradePricePlanView): ChartPriceLevel[] {
  const levels: ChartPriceLevel[] = [];

  const hasActual =
    plan.actual_entry_price !== null &&
    plan.actual_entry_price !== undefined &&
    plan.actual_entry_price !== '';
  const hasRef =
    plan.entry_reference_price !== null &&
    plan.entry_reference_price !== undefined &&
    plan.entry_reference_price !== '';

  if (hasActual) {
    const isSameAsRef = hasRef && isSamePrice(plan.actual_entry_price, plan.entry_reference_price);
    levels.push({
      price: plan.actual_entry_price!,
      color: '#0ECB81',
      label: isSameAsRef
        ? `实际 Entry · ${formatChartPrice(plan.actual_entry_price)} (等同计划)`
        : `实际 Entry · ${formatChartPrice(plan.actual_entry_price)}`,
      lineStyle: LineStyle.Solid,
      lineWidth: 2,
    });
    // If planned reference is numerically distinct, plot it as dashed line
    if (hasRef && !isSameAsRef) {
      levels.push({
        price: plan.entry_reference_price!,
        color: '#F59E0B',
        label: `计划 Entry · ${formatChartPrice(plan.entry_reference_price)}`,
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
      });
    }
  } else if (hasRef) {
    levels.push({
      price: plan.entry_reference_price!,
      color: '#F59E0B',
      label: `计划 Entry · ${formatChartPrice(plan.entry_reference_price)}`,
      lineStyle: LineStyle.Dashed,
      lineWidth: 1,
    });
  }

  const hasInitialStop =
    plan.initial_stop_price !== null &&
    plan.initial_stop_price !== undefined &&
    plan.initial_stop_price !== '';
  const hasActiveStop =
    plan.active_stop_price !== null &&
    plan.active_stop_price !== undefined &&
    plan.active_stop_price !== '';

  if (hasInitialStop && hasActiveStop) {
    const isStopSame = isSamePrice(plan.active_stop_price, plan.initial_stop_price);
    if (isStopSame) {
      // Merged visual position, but preserve both identifiable fact semantics
      levels.push({
        price: plan.initial_stop_price!,
        color: '#EF4444',
        label: `Initial / Active Stop · ${formatChartPrice(plan.initial_stop_price)} (数值相同)`,
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
      });
    } else {
      // Both exist with genuinely distinct prices - neither is hidden or logically deleted
      levels.push({
        price: plan.initial_stop_price!,
        color: '#EF4444',
        label: `Initial Stop · ${formatChartPrice(plan.initial_stop_price)}`,
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
      });
      levels.push({
        price: plan.active_stop_price!,
        color: '#3B82F6',
        label: `Active Stop · ${formatChartPrice(plan.active_stop_price)}`,
        lineStyle: LineStyle.Dotted,
        lineWidth: 1,
      });
    }
  } else if (hasInitialStop) {
    levels.push({
      price: plan.initial_stop_price!,
      color: '#EF4444',
      label: `Initial Stop · ${formatChartPrice(plan.initial_stop_price)}`,
      lineStyle: LineStyle.Dashed,
      lineWidth: 1,
    });
  } else if (hasActiveStop) {
    levels.push({
      price: plan.active_stop_price!,
      color: '#3B82F6',
      label: `Active Stop · ${formatChartPrice(plan.active_stop_price)}`,
      lineStyle: LineStyle.Dotted,
      lineWidth: 1,
    });
  }

  // Take Profit 1 (Teal)
  if (
    plan.tp1_price !== null &&
    plan.tp1_price !== undefined &&
    plan.tp1_price !== ''
  ) {
    levels.push({
      price: plan.tp1_price,
      color: '#14B8A6',
      label: `TP1 · ${formatChartPrice(plan.tp1_price)}`,
      lineStyle: LineStyle.Dashed,
      lineWidth: 1,
    });
  }

  return levels;
}

export function observationPriceLevels(obs: StrategyObservationListItem): ChartPriceLevel[] {
  const levels: ChartPriceLevel[] = [];

  if (
    obs.entry_reference_price !== null &&
    obs.entry_reference_price !== undefined &&
    obs.entry_reference_price !== ''
  ) {
    levels.push({
      price: obs.entry_reference_price,
      color: '#F59E0B',
      label: `计划参考 (Entry) · ${formatChartPrice(obs.entry_reference_price)}`,
      lineStyle: LineStyle.Dashed,
      lineWidth: 1,
    });
  }

  if (
    obs.initial_stop_price !== null &&
    obs.initial_stop_price !== undefined &&
    obs.initial_stop_price !== ''
  ) {
    levels.push({
      price: obs.initial_stop_price,
      color: '#EF4444',
      label: `计划止损 (Stop) · ${formatChartPrice(obs.initial_stop_price)}`,
      lineStyle: LineStyle.Dashed,
      lineWidth: 1,
    });
  }

  if (
    obs.take_profit_price !== null &&
    obs.take_profit_price !== undefined &&
    obs.take_profit_price !== ''
  ) {
    levels.push({
      price: obs.take_profit_price,
      color: '#14B8A6',
      label: `计划止盈 (TP1) · ${formatChartPrice(obs.take_profit_price)}`,
      lineStyle: LineStyle.Dashed,
      lineWidth: 1,
    });
  }

  if (
    obs.opening_range_boundary_price !== null &&
    obs.opening_range_boundary_price !== undefined &&
    obs.opening_range_boundary_price !== ''
  ) {
    levels.push({
      price: obs.opening_range_boundary_price,
      color: '#8B5CF6',
      label: `首小时边界 (Opening Range) · ${formatChartPrice(obs.opening_range_boundary_price)}`,
      lineStyle: LineStyle.Dotted,
      lineWidth: 1,
    });
  }

  return levels;
}
