import { z } from "zod";

const reviewSearchParamsSchema = z.object({
  from_ms: z.coerce.number().int().nonnegative().optional(),
  to_ms: z.coerce.number().int().positive().optional(),
  review_status: z.enum(["in_progress", "waiting_for_settlement", "waiting_for_review", "complete", "incomplete_evidence"]).optional(),
  strategy_group_id: z.string().trim().min(1).max(160).optional(),
  cursor: z.string().min(1).max(2048).optional(),
});

export type ReviewSearchParams = z.infer<typeof reviewSearchParamsSchema>;

export function parseReviewSearchParams(searchParams: URLSearchParams): ReviewSearchParams {
  const values = Object.fromEntries([...searchParams.entries()].filter(([, value]) => value.trim().length > 0));
  const parsed = reviewSearchParamsSchema.safeParse(values);
  return parsed.success ? parsed.data : {};
}

export function reviewSearchParamsToString(filters: ReviewSearchParams): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) searchParams.set(key, String(value));
  }
  return searchParams.toString();
}
