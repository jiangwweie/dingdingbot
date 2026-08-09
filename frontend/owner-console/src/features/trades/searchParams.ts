import { z } from "zod";

const optionalNonBlankText = z.string().trim().min(1).max(160).optional();

const tradeSearchParamsSchema = z.object({
  from_ms: z.coerce.number().int().nonnegative().optional(),
  to_ms: z.coerce.number().int().positive().optional(),
  strategy_group_id: optionalNonBlankText,
  exchange_instrument_id: optionalNonBlankText,
  position_side: z.enum(["long", "short"]).optional(),
  aggregate_status: optionalNonBlankText,
  cursor: z.string().min(1).max(2048).optional(),
});

export type TradeSearchParams = z.infer<typeof tradeSearchParamsSchema>;

export function parseTradeSearchParams(searchParams: URLSearchParams): TradeSearchParams {
  const values = Object.fromEntries(
    [...searchParams.entries()].filter(([, value]) => value.trim().length > 0),
  );
  const parsed = tradeSearchParamsSchema.safeParse(values);
  return parsed.success ? parsed.data : {};
}

export function tradeSearchParamsToString(filters: TradeSearchParams): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) searchParams.set(key, String(value));
  }
  return searchParams.toString();
}

