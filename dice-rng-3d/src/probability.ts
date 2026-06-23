export type RollSummary = {
  rolls: number;
  diceCount: number;
  sides: number;
  totals: Map<number, number>;
  expected: Map<number, number>;
};

export function expectedTotalDistribution(diceCount: number, sides: number): Map<number, number> {
  let distribution = new Map<number, number>([[0, 1]]);

  for (let die = 0; die < diceCount; die += 1) {
    const next = new Map<number, number>();
    for (const [sum, count] of distribution) {
      for (let face = 1; face <= sides; face += 1) {
        next.set(sum + face, (next.get(sum + face) ?? 0) + count);
      }
    }
    distribution = next;
  }

  const combinations = sides ** diceCount;
  return new Map([...distribution.entries()].map(([total, count]) => [total, count / combinations]));
}

export function rollTotal(diceCount: number, sides: number, rng: () => number = Math.random): number {
  let total = 0;
  for (let die = 0; die < diceCount; die += 1) {
    total += Math.floor(rng() * sides) + 1;
  }
  return total;
}

export function simulateRolls(
  rolls: number,
  diceCount: number,
  sides: number,
  rng: () => number = Math.random
): RollSummary {
  const totals = new Map<number, number>();
  for (let index = 0; index < rolls; index += 1) {
    const total = rollTotal(diceCount, sides, rng);
    totals.set(total, (totals.get(total) ?? 0) + 1);
  }

  return {
    rolls,
    diceCount,
    sides,
    totals,
    expected: expectedTotalDistribution(diceCount, sides)
  };
}

export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (1664525 * state + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}
