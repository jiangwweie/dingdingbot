import { useQuery } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppProviders } from "../app/providers";
import { ownerQueryClient } from "../app/queryClient";

function QueryProbe({ load }: { load: () => Promise<{ snapshot_id: string }> }) {
  const query = useQuery({
    queryKey: ["query-default-probe"],
    queryFn: load,
  });

  return <div>{query.isSuccess ? "loaded" : "loading"}</div>;
}

function ManualQueryProbe({
  load,
}: {
  load: () => Promise<{
    snapshot_id: string;
    data: { active_tickets: number };
  }>;
}) {
  const query = useQuery({
    queryKey: ["manual-query-probe"],
    queryFn: load,
  });

  return (
    <div>
      <div>{query.data ? `${query.data.data.active_tickets} active` : "loading"}</div>
      <button type="button" onClick={() => void query.refetch()}>
        刷新当前页
      </button>
      {query.isRefetchError ? <div>刷新失败</div> : null}
    </div>
  );
}

beforeEach(() => {
  ownerQueryClient.clear();
});

afterEach(() => {
  ownerQueryClient.clear();
});

it("does not refetch on focus, reconnect, retry, or elapsed time", async () => {
  const calls = vi.fn().mockResolvedValue({ snapshot_id: "s1" });
  render(
    <AppProviders>
      <QueryProbe load={calls} />
    </AppProviders>,
  );

  await screen.findByText("loaded");
  window.dispatchEvent(new Event("focus"));
  window.dispatchEvent(new Event("online"));
  await new Promise((resolve) => setTimeout(resolve, 50));

  expect(calls).toHaveBeenCalledTimes(1);
});

it("does not retry a failed initial request", async () => {
  const calls = vi.fn().mockRejectedValue(new Error("offline"));
  render(
    <AppProviders>
      <QueryProbe load={calls} />
    </AppProviders>,
  );

  await screen.findByText("loading");
  await new Promise((resolve) => setTimeout(resolve, 50));

  expect(calls).toHaveBeenCalledTimes(1);
});

it("preserves last known good data when manual refresh fails", async () => {
  const user = userEvent.setup();
  const calls = vi
    .fn()
    .mockResolvedValueOnce({ snapshot_id: "s1", data: { active_tickets: 1 } })
    .mockRejectedValueOnce(new Error("offline"));
  render(
    <AppProviders>
      <ManualQueryProbe load={calls} />
    </AppProviders>,
  );

  expect(await screen.findByText("1 active")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "刷新当前页" }));

  expect(await screen.findByText("刷新失败")).toBeInTheDocument();
  expect(screen.getByText("1 active")).toBeInTheDocument();
  expect(calls).toHaveBeenCalledTimes(2);
});
