import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { isUnauthorized } from "../api/errors";

export const sessionExpiredEvent = "owner-console:session-expired";

function notifySessionExpired(error: unknown) {
  if (isUnauthorized(error) && typeof window !== "undefined") {
    window.dispatchEvent(new Event(sessionExpiredEvent));
  }
}

export const ownerQueryClient = new QueryClient({
  queryCache: new QueryCache({ onError: notifySessionExpired }),
  mutationCache: new MutationCache({ onError: notifySessionExpired }),
  defaultOptions: {
    queries: {
      refetchInterval: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      retry: false,
      staleTime: Infinity,
      gcTime: Infinity,
    },
    mutations: { retry: false },
  },
});
