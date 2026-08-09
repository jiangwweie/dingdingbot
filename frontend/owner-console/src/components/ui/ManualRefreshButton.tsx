import { Button } from "./Button";

interface ManualRefreshButtonProps {
  isRefreshing: boolean;
  onRefresh: () => void;
}

export function ManualRefreshButton({ isRefreshing, onRefresh }: ManualRefreshButtonProps) {
  return (
    <Button disabled={isRefreshing} onClick={onRefresh}>
      {isRefreshing ? "刷新中" : "刷新当前页"}
    </Button>
  );
}
