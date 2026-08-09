import { expect, it } from "vitest";
import { toChartNumber } from "../../components/charts/chartAdapter";

it("converts API price strings only at the chart boundary", () => {
  expect(toChartNumber("61234.5000")).toBe(61234.5);
  expect(() => toChartNumber("not-a-price")).toThrow("invalid chart coordinate");
});

