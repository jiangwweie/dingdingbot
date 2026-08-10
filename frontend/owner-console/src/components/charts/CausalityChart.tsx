import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineStyle,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { components } from "../../api/schema";
import { toCandlestickData, toChartNumber, toSeriesMarkers } from "./chartAdapter";

interface CausalityChartProps {
  annotations: components["schemas"]["ChartAnnotation"][];
  candles: components["schemas"]["CandleView"][];
  priceLevels: ChartPriceLevel[];
  fullscreen?: boolean;
}

export interface ChartPriceLevel {
  color: string;
  label: string;
  price: string;
}

export default function CausalityChart({ annotations, candles, priceLevels, fullscreen = false }: CausalityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#11141A" },
        textColor: "#848E9C",
        fontFamily: 'Inter, "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(43, 49, 57, 0.45)" },
        horzLines: { color: "rgba(43, 49, 57, 0.45)" },
      },
      rightPriceScale: { borderColor: "#2B3139" },
      timeScale: { borderColor: "#2B3139", timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: "#848E9C" }, horzLine: { color: "#848E9C" } },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#0ECB81",
      downColor: "#F6465D",
      borderVisible: false,
      wickUpColor: "#0ECB81",
      wickDownColor: "#F6465D",
    });
    series.setData(toCandlestickData(candles));
    createSeriesMarkers(series, toSeriesMarkers(annotations));
    for (const level of priceLevels) {
      series.createPriceLine({
        price: toChartNumber(level.price),
        color: level.color,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: level.label,
      });
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [annotations, candles, priceLevels]);

  return <div className={fullscreen ? "h-[calc(100vh-156px)] min-h-[520px] w-full" : "h-[420px] min-h-[320px] w-full"} data-testid="causality-chart" ref={containerRef} />;
}
