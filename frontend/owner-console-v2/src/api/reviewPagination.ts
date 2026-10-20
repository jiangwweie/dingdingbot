import { infiniteQueryOptions } from '@tanstack/react-query';
import { fetchReviewCenter, reviewInfiniteQueryKey, type ReviewQueryParams } from './reviewApi.ts';

export function reviewPaginationOptions(
  params: Omit<ReviewQueryParams, 'cursor'>,
  fetchPage: typeof fetchReviewCenter = fetchReviewCenter
) {
  return infiniteQueryOptions({
    queryKey: reviewInfiniteQueryKey(params),
    queryFn: ({ pageParam }) => fetchPage({ ...params, cursor: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.data.next_cursor ?? null,
    staleTime: 15_000,
    retry: false,
  });
}
