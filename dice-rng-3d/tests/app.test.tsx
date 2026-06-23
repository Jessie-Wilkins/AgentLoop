import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "../src/App";

vi.mock("@react-three/fiber", () => ({
  Canvas: () => <div data-testid="canvas" />,
  useFrame: () => undefined
}));

vi.mock("@react-three/drei", () => ({
  OrthographicCamera: () => <div data-testid="camera" />
}));

describe("App", () => {
  it("renders coffee setup controls and updates water and grounds", () => {
    render(<App />);

    const water = screen.getByRole("slider", { name: "water" }) as HTMLInputElement;
    const grounds = screen.getByRole("slider", { name: "grounds" }) as HTMLInputElement;

    fireEvent.change(water, { target: { value: "110" } });
    fireEvent.change(grounds, { target: { value: "20" } });

    expect(water.value).toBe("110");
    expect(grounds.value).toBe("20");
    expect(screen.getByTestId("canvas")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Brew" })).toBeInTheDocument();
  });

  it("locks ingredient controls while brewing and exposes smash/reset actions", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Brew" }));

    expect(screen.getByRole("slider", { name: "water" })).toBeDisabled();
    expect(screen.getByRole("slider", { name: "grounds" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Smash" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.getByRole("slider", { name: "water" })).not.toBeDisabled();
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });
});
