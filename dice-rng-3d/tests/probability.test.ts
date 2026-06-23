import { describe, expect, it } from "vitest";
import { expectedTotalDistribution, seededRandom, simulateRolls } from "../src/probability";

function maxDistributionError(summary: ReturnType<typeof simulateRolls>): number {
  let max = 0;
  for (const [total, expected] of summary.expected) {
    const observed = (summary.totals.get(total) ?? 0) / summary.rolls;
    max = Math.max(max, Math.abs(observed - expected));
  }
  return max;
}

describe("probability utilities", () => {
  it("computes the exact predicted distribution for one six-sided die", () => {
    const distribution = expectedTotalDistribution(1, 6);
    expect(distribution.size).toBe(6);
    for (let face = 1; face <= 6; face += 1) {
      expect(distribution.get(face)).toBeCloseTo(1 / 6, 12);
    }
  });

  it("100 rolls trend toward the predicted probability for 1d6", () => {
    const summary = simulateRolls(100, 1, 6, seededRandom(6));
    expect(maxDistributionError(summary)).toBeLessThanOrEqual(0.12);
  });

  it("100 rolls trend toward the predicted probability for 1d10", () => {
    const summary = simulateRolls(100, 1, 10, seededRandom(10));
    expect(maxDistributionError(summary)).toBeLessThanOrEqual(0.1);
  });

  it("100 rolls trend toward the predicted probability for 2d6", () => {
    const summary = simulateRolls(100, 2, 6, seededRandom(26));
    expect(maxDistributionError(summary)).toBeLessThanOrEqual(0.12);
    expect(summary.expected.get(7)).toBeCloseTo(6 / 36, 12);
    expect(summary.expected.get(2)).toBeCloseTo(1 / 36, 12);
    expect(summary.expected.get(12)).toBeCloseTo(1 / 36, 12);
  });
});
