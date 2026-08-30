import { describe, expect, it } from 'vitest';

import { calculateEquity } from './equity';

describe('browser equity calculator', () => {
  it('enumerates heads-up river equity exactly', async () => {
    const result = await calculateEquity({
      holeCards: ['Ah', 'Ad'],
      board: ['Ac', 'Ks', '7d', '2c', '3h'],
    });

    expect(result.method).toBe('exact');
    expect(result.samples).toBe(990);
    expect(result.standardError).toBe(0);
    expect(result.equity).toBeCloseTo(
      (result.wins + result.ties / 2) / result.samples,
    );
  });

  it('samples all five opponents deterministically', async () => {
    const request = {
      holeCards: ['Ah', 'Kh'],
      board: [] as string[],
      opponentCount: 5,
      sampleLimit: 2_000,
    };
    const first = await calculateEquity(request);
    const second = await calculateEquity(request);
    const headsUp = await calculateEquity({ ...request, opponentCount: 1 });

    expect(second).toEqual(first);
    expect(first.method).toBe('sampled');
    expect(first.samples).toBe(2_000);
    expect(first.opponentCount).toBe(5);
    expect(first.playerCount).toBe(6);
    expect(first.equity).toBeLessThan(headsUp.equity);
  });

  it('accepts a weighted range for each opponent', async () => {
    const range = [
      { cards: ['As', 'Ks'], weight: 0.7 },
      { cards: ['Qs', 'Qh'], weight: 0.3 },
    ];
    const result = await calculateEquity({
      holeCards: ['Ah', 'Kd'],
      board: ['7c', '5s', '2d'],
      opponentCount: 1,
      opponentRanges: [range],
      sampleLimit: 500,
    });

    expect(result.samples).toBe(500);
    expect(result.opponentRange).toBe('action-weighted-v1');
  });
});
