import { describe, expect, it } from 'vitest';

import { calculateHandChances, HAND_CATEGORIES } from './hand-chances';

describe('browser hand-chance calculator', () => {
  it('exactly enumerates flop runouts with Python-contract counts', async () => {
    const result = await calculateHandChances({
      holeCards: ['Ah', 'Kh'],
      board: ['Qh', 'Jh', '2c'],
    });

    expect(result.method).toBe('exact');
    expect(result.samples).toBe(1_081);
    expect(result.combinations['straight-flush']).toBe(46);
    expect(result.combinations.flush).toBe(332);
    expect(result.outs).toEqual(result.combinations);
    expect(result.atLeast['high-card']).toBe(1);
  });

  it('does not count a board-only made hand for the hero', async () => {
    const result = await calculateHandChances({
      holeCards: ['2c', '3d'],
      board: ['Ah', 'Kh', 'Qh', 'Jh', 'Th'],
    });

    expect(result.combinations['straight-flush']).toBe(0);
    expect(result.exact['straight-flush']).toBe(0);
  });

  it('samples preflop repeatably and returns all baseline fields', async () => {
    const request = { holeCards: ['7h', '2c'], sampleLimit: 2_000 };
    const first = await calculateHandChances(request);
    const second = await calculateHandChances(request);

    expect(second).toEqual(first);
    expect(first.method).toBe('sampled');
    expect(first.samples).toBe(2_000);
    expect(first.baselineSamples).toBe(2_000);
    expect(Object.keys(first.percentile75Exact).sort()).toEqual(
      [...HAND_CATEGORIES].sort(),
    );
  });
});
