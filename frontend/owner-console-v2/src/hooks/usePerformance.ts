import { useQuery } from '@tanstack/react-query';
import { fetchPerformance, type PerformanceParams } from '../api/performanceApi';
export function usePerformance(params: PerformanceParams) {
  return useQuery({ queryKey: ['owner', 'performance', params], queryFn: () => fetchPerformance(params), enabled: Boolean(params.from_ms && params.to_ms), staleTime: 15_000, retry: false });
}
