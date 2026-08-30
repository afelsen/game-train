import { describe, expect, it } from 'vitest';

import { DEFAULT_BUY_IN, prepareNextHandStacks } from './match';

describe('cash-game rebuys', () => {
  it('automatically rebuys busted bots while preserving other stacks', () => {
    expect(
      prepareNextHandStacks([8_400, 0, 12_300, 0, 9_500, 10_000], false),
    ).toEqual([8_400, DEFAULT_BUY_IN, 12_300, DEFAULT_BUY_IN, 9_500, 10_000]);
  });

  it('requires hero confirmation before a 100 BB rebuy', () => {
    expect(prepareNextHandStacks([0, 11_000, 9_000], false)).toBeNull();
    expect(prepareNextHandStacks([0, 11_000, 9_000], true)).toEqual([
      DEFAULT_BUY_IN,
      11_000,
      9_000,
    ]);
  });
});
