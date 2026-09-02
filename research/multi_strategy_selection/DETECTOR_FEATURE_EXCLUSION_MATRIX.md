# Detector Feature Exclusion Matrix

Authority: `dev@2697f4b5943ed6a98f04a93e1b78d38e53780890`

| Strategy | Current Detector inputs | Protection reference | Forbidden duplicate/tightened Context features | Allowed Stage-2 features |
| --- | --- | --- | --- | --- |
| CPM | 4h close vs SMA20; latest 4h close vs previous; previous 20 completed 1h high-low depth in `[0.5%,8%]`; latest 1h close vs SMA20 and previous 1h high | minimum low of the previous 20 completed 1h bars | any stricter form of trend/SMA, previous-high reclaim, or 20h range/depth | F1-F5 market context; F6 24h directional efficiency |
| MPG | 8h 1h net return; 4h net return; previous range breakout; bullish latest candle; higher-close count; full-Universe comparative rank and return | minimum low of the five completed 1h bars before the trigger | current 8h/4h return, rank, breakout, bullish candle, higher-close count, or stricter thresholds | F1-F5 only |
| MI | 12h return threshold and full-Universe comparative rank | close 12 hours before trigger | current 12h return, current rank, stricter impulse threshold | F1-F5 only |
| BRF2 | 8h rally extension; upper-wick ratio; close reversal; bearish candle; previous close; 4h strong-uptrend disable | rally high including trigger candle | current rally/wick/reversal/bearish/4h-disable variables or stricter thresholds | F1-F5 only |

Stage-1 signal metadata is excluded from all strategies. Ticker identity remains
audit/LOSO only and cannot become an alpha feature. MPG/MI ComparisonUniverse
is the complete frozen 24-member CandidateUniverse and cannot be changed by a
hypothetical TradableUniverse.

