import { z } from "zod";

const optionalTimestamp = z.coerce.number().int().nonnegative().optional();
const optionalId = z.string().trim().min(1).max(160).optional();

const strategySearchParamsSchema = z.object({
  from_ms: optionalTimestamp,
  to_ms: optionalTimestamp,
  view: z.enum(["current", "all"]).optional(),
  strategy_version_id: optionalId,
  ticket_modal: z.literal("1").optional(),
  observation_modal: z.literal("1").optional(),
  scope: z.enum(["natural", "all"]).optional(),
  exit_path: z.enum(["tp1_reached", "tp1_not_reached", "controlled_exit"]).optional(),
  observation_path: z.enum(["tp1_first", "initial_stop_first", "ambiguous_same_bar", "opening_range_failure", "time_stop", "session_exit", "horizon_complete"]).optional(),
  observation_id: optionalId,
  observation_cursor: z.string().min(1).max(2048).optional(),
  cursor: z.string().min(1).max(2048).optional(),
});

export type StrategySearchParams = z.infer<typeof strategySearchParamsSchema>;

export function parseStrategySearchParams(searchParams: URLSearchParams): StrategySearchParams {
  const values = Object.fromEntries([...searchParams.entries()].filter(([, value]) => value.trim().length > 0));
  const parsed = strategySearchParamsSchema.safeParse(values);
  return parsed.success ? parsed.data : {};
}

export function strategySearchParamsToString(filters: StrategySearchParams): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) searchParams.set(key, String(value));
  }
  return searchParams.toString();
}
