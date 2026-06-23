import { describe, expect, it } from "vitest";
import { coffeeFillGeometry, COLOR_UNLOCK_INTERVAL, scoreBrew, unlockedColorCount } from "../src/coffeeScoring";

describe("coffee scoring", () => {
  it("rewards balanced strength more than weak or over-extracted coffee", () => {
    const balanced = scoreBrew(80, 14, 80, false);
    const weak = scoreBrew(80, 3, 80, false);
    const tooStrong = scoreBrew(80, 34, 80, false);

    expect(balanced).toBeGreaterThan(weak);
    expect(balanced).toBeGreaterThan(tooStrong);
  });

  it("adds a meaningful full-pot bonus", () => {
    const partial = scoreBrew(100, 23, 130, false);
    const complete = scoreBrew(100, 23, 130, true);

    expect(complete - partial).toBe(180);
  });

  it("unlocks pot colors from lifetime points while keeping the palette bounded", () => {
    expect(unlockedColorCount(0)).toBe(1);
    expect(unlockedColorCount(COLOR_UNLOCK_INTERVAL)).toBe(2);
    expect(unlockedColorCount(COLOR_UNLOCK_INTERVAL * 8)).toBe(4);
  });

  it("fills the visible carafe all the way to the rim at 100 percent", () => {
    const empty = coffeeFillGeometry(0);
    const half = coffeeFillGeometry(50);
    const full = coffeeFillGeometry(100);

    expect(empty.top).toBe(empty.bottom);
    expect(half.top).toBeCloseTo(-0.27);
    expect(full.top).toBeCloseTo(0.83);
    expect(full.topHalfWidth).toBeGreaterThan(half.topHalfWidth);
  });
});
