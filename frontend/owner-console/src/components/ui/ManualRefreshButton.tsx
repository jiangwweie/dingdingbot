import { RotateCw } from "lucide-react";
import { Button } from "./Button";

interface ManualRefreshButtonProps {
  isRefreshing: boolean;
  onRefresh: () => void;
}

export function ManualRefreshButton({ isRefreshing, onRefresh }: ManualRefreshButtonProps) {
  return (
    <Button disabled={isRefreshing} onClick={onRefresh}>
      <RotateCw
        className={`mr-1.5 h-3.5 w-3.5 ${isRefreshing ? "animate-spin text-[var(--color-emphasis)]" : "text-[var(--color-text-secondary)]"}`}
        aria-hidden="true"
      />
      {isRefreshing ? "刷新中" : "刷新当前页"}
    </Button>
  );
}
