import type { components } from "../../api/schema";
import type { CandlestickData, SeriesMarker, UTCTimestamp } from "lightweight-charts";

type Candle = components["schemas"]["CandleView"];
type Annotation = components["schemas"]["ChartAnnotation"];

export function toChartNumber(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error("invalid chart coordinate");
  return parsed;
}

export function toCandlestickData(candles: Candle[]): CandlestickData<UTCTimestamp>[] {
  return candles.map((candle) => ({
    time: Math.floor(candle.open_time_ms / 1000) as UTCTimestamp,
    open: toChartNumber(candle.open),
    high: toChartNumber(candle.high),
    low: toChartNumber(candle.low),
    close: toChartNumber(candle.close),
  }));
}

const markerColor = {
  signal: "#FCD535",
  entry: "#0ECB81",
  stop: "#F6465D",
  take_profit: "#0ECB81",
  exit: "#F6465D",
} as const;

export function toSeriesMarkers(annotations: Annotation[]): SeriesMarker<UTCTimestamp>[] {
  return annotations.map((annotation) => ({
    time: Math.floor(annotation.occurred_at_ms / 1000) as UTCTimestamp,
    position: annotation.kind === "stop" || annotation.kind === "exit" ? "aboveBar" : "belowBar",
    color: markerColor[annotation.kind],
    shape: annotation.kind === "entry" || annotation.kind === "signal" ? "arrowUp" : annotation.kind === "stop" || annotation.kind === "exit" ? "arrowDown" : "circle",
    text: `${annotation.label} · ${annotation.price}`,
  }));
}

