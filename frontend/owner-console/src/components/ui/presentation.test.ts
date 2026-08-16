import { expect, it } from "vitest";
import { formatMoney, formatOwnerReason, formatOwnerStatus } from "./presentation";

it("rounds decimal display values to two places without changing the source value", () => {
  expect(formatMoney("438.953439370000000000", "USDT")).toBe("438.95 USDT");
  expect(formatMoney("-0.005", "USDT", { sign: true })).toBe("-0.01 USDT");
  expect(formatMoney("1.2", "R")).toBe("1.20 R");
});

it("uses Owner language while retaining the raw reason for technical detail", () => {
  expect(formatOwnerStatus("needs_intervention")).toBe("需要关注");
  expect(formatOwnerReason("owner_flatten_all:owner-authorization:1")).toEqual({
    label: "Owner 受控平仓",
    raw: "owner_flatten_all:owner-authorization:1",
  });
  expect(formatOwnerReason("runner_stop")).toEqual({
    label: "Runner 止损退出",
    raw: "runner_stop",
  });
  expect(formatOwnerReason("venue_truth_timeout")).toEqual({
    label: "系统记录：venue_truth_timeout",
    raw: "venue_truth_timeout",
  });
});
