interface CursorPaginationProps {
  hasNextPage: boolean;
  label?: string;
  onNextPage: () => void;
}

export function CursorPagination({ hasNextPage, label = "还有更多持久化 Signal", onNextPage }: CursorPaginationProps) {
  if (!hasNextPage) return null;

  return (
    <div className="mt-2 flex min-h-[30px] items-center justify-between border border-[var(--color-divider)] bg-[var(--color-surface)] px-2">
      <span className="text-[11px] text-[var(--color-text-secondary)]">{label}</span>
      <button className="owner-button h-[26px]" type="button" onClick={onNextPage}>
        下一页
      </button>
    </div>
  );
}
