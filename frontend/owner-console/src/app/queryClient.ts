import { QueryClient } from "@tanstack/react-query";

export const ownerQueryClient = new QueryClient({
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
