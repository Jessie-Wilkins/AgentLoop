export const POT_CAPACITY = 100;
export const MAX_WATER = 130;
export const PERFECT_RATIO = 0.18;
export const POT_COLORS = ["#a7d8ff", "#ffb3c7", "#88d7a7", "#f6c768"] as const;
export const COLOR_UNLOCK_INTERVAL = 550;

export type CoffeeFillGeometry = {
  bottom: number;
  top: number;
  bottomHalfWidth: number;
  topHalfWidth: number;
};

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function scoreBrew(brewed: number, grounds: number, water: number, fullBonus: boolean): number {
  if (brewed <= 0 || water <= 0) return 0;
  const ratio = grounds / Math.max(1, water);
  const balance = clamp(1 - Math.abs(ratio - PERFECT_RATIO) / 0.13, 0.14, 1);
  const volumeScore = brewed * 4.2;
  const finishScore = fullBonus ? 180 : 0;
  return Math.round(volumeScore * balance + finishScore);
}

export function unlockedColorCount(totalPoints: number): number {
  return Math.min(POT_COLORS.length, 1 + Math.floor(totalPoints / COLOR_UNLOCK_INTERVAL));
}

/** Returns the liquid bounds inside the tapered carafe in local scene units. */
export function coffeeFillGeometry(fill: number): CoffeeFillGeometry {
  const bottom = -1.37;
  const top = bottom + 2.2 * clamp(fill / POT_CAPACITY, 0, 1);
  const halfWidthAt = (y: number) => 0.55 + ((y - bottom) / 2.2) * 0.47;

  return {
    bottom,
    top,
    bottomHalfWidth: halfWidthAt(bottom),
    topHalfWidth: halfWidthAt(top)
  };
}
