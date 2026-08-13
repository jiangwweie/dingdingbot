import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { instrumentFixture } from "../../api/fixtures";
import { ownerQueryClient } from "../../app/queryClient";
import { InstrumentPage } from "./InstrumentPage";
import { getInstruments } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, getInstruments: vi.fn() };
});

const mockedGetInstruments = vi.mocked(getInstruments);

beforeEach(() => {
  ownerQueryClient.clear();
  mockedGetInstruments.mockReset();
  mockedGetInstruments.mockResolvedValue(instrumentFixture);
});

it("shows product facts and opens the Universe editor without allowing references", async () => {
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={ownerQueryClient}>
      <MemoryRouter initialEntries={["/instruments"]}>
        <InstrumentPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText("AAPLUSDT")).toBeInTheDocument();
  expect(screen.getAllByText("REGULAR").length).toBeGreaterThan(0);
  expect(screen.getByText("1.8 / 20 bps")).toBeInTheDocument();
  expect(screen.getByText("1.8 / 50 bps")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "编辑 Universe" }));

  expect(screen.getByRole("dialog", { name: /Universe 成员/ })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: /QQQUSDT/ })).toBeDisabled();
});
