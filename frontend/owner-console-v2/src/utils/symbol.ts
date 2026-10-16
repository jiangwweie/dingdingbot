export function cleanSymbol(rawSymbol: string): string {
  if (!rawSymbol) return rawSymbol;
  // e.g. "binance-usdm:TRXUSDT:perpetual" -> "TRXUSDT"
  const parts = rawSymbol.split(':');
  if (parts.length >= 2) {
    return parts[1];
  }
  return rawSymbol;
}
