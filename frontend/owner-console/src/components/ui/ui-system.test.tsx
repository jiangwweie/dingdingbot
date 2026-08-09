import { render, screen } from "@testing-library/react";
import { Button } from "./Button";
import { StatusTag } from "./StatusTag";

it("renders dense b-spec controls without saas card defaults", () => {
  render(
    <>
      <Button>刷新当前页</Button>
      <StatusTag tone="success">正常</StatusTag>
    </>,
  );

  expect(screen.getByRole("button")).toHaveClass("h-8");
  expect(screen.getByText("正常")).toHaveAttribute("data-tone", "success");
});
