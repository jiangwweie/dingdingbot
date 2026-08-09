import { z } from "zod";

const optionalNonBlankText = z
  .string()
  .trim()
  .min(1)
  .max(160)
  .optional();

const signalSearchParamsSchema = z.object({
  from_ms: z.coerce.number().int().nonnegative().optional(),
  to_ms: z.coerce.number().int().positive().optional(),
  strategy_group_id: optionalNonBlankText,
  exchange_instrument_id: optionalNonBlankText,
  position_side: z.enum(["long", "short"]).optional(),
  decision_status: z.enum(["admitted", "rejected"]).optional(),
  cursor: z.string().min(1).max(2048).optional(),
});

export type SignalSearchParams = z.infer<typeof signalSearchParamsSchema>;

export function parseSignalSearchParams(searchParams: URLSearchParams): SignalSearchParams {
  const values = Object.fromEntries(
    [...searchParams.entries()].filter(([, value]) => value.trim().length > 0),
  );
  const parsed = signalSearchParamsSchema.safeParse(values);
  return parsed.success ? parsed.data : {};
}

export function signalSearchParamsToString(filters: SignalSearchParams): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) searchParams.set(key, String(value));
  }
  return searchParams.toString();
}
