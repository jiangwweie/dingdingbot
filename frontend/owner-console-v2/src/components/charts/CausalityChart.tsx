import React, { useEffect, useRef } from 'react';
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineStyle,
  type IChartApi,
} from 'lightweight-charts';
import { useTheme } from '../../context/ThemeContext';
import {
  toCandlestickData,
  toChartNumber,
  toSeriesMarkers,
  type CandleView,
  type ChartAnnotation,
  type ChartPriceLevel,
} from '../../mapping/chartAdapter';

export interface CausalityChartProps {
  candles: CandleView[];
  annotations?: ChartAnnotation[];
  priceLevels?: ChartPriceLevel[];
  fullscreen?: boolean;
}

export const CausalityChart: React.FC<CausalityChartProps> = ({
  candles,
  annotations = [],
  priceLevels = [],
  fullscreen = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    if (!containerRef.current) return;

    const isDark = theme === 'dark';
    const bg = isDark ? '#11141A' : '#FFFFFF';
    const text = isDark ? '#848E9C' : '#64748B';
    const grid = isDark ? 'rgba(43, 49, 57, 0.45)' : 'rgba(226, 232, 240, 0.8)';
    const border = isDark ? '#2B3139' : '#CBD5E1';

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: bg },
        textColor: text,
        fontFamily: 'Inter, "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: grid },
        horzLines: { color: grid },
      },
      rightPriceScale: { borderColor: border },
      timeScale: { borderColor: border, timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: text }, horzLine: { color: text } },
    });

    chartInstanceRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#0ECB81',
      downColor: '#F6465D',
      borderVisible: false,
      wickUpColor: '#0ECB81',
      wickDownColor: '#F6465D',
    });

    const candlestickData = toCandlestickData(candles);
    series.setData(candlestickData);
    if (containerRef.current) {
      (containerRef.current as any).__candlestickData = candlestickData;
    }

    const markers = toSeriesMarkers(annotations, candles);
    if (markers.length > 0) {
      createSeriesMarkers(series, markers);
    }

    for (const level of priceLevels) {
      try {
        series.createPriceLine({
          price: toChartNumber(level.price),
          color: level.color,
          lineWidth: level.lineWidth ?? 1,
          lineStyle: level.lineStyle ?? LineStyle.Dashed,
          axisLabelVisible: true,
          title: level.label,
        });
      } catch {
        // Skip invalid price coordinate gracefully
      }
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartInstanceRef.current = null;
      if (containerRef.current) {
        delete (containerRef.current as any).__candlestickData;
      }
    };
  }, [candles, annotations, priceLevels, theme]);

  return (
    <div
      data-testid="causality-chart"
      ref={containerRef}
      data-candles-count={candles.length}
      data-first-open={candles[0]?.open}
      data-last-close={candles[candles.length - 1]?.close}
      className={
        fullscreen
          ? 'h-[calc(100vh-140px)] min-h-[500px] w-full'
          : 'h-[420px] min-h-[320px] w-full'
      }
    />
  );
};
