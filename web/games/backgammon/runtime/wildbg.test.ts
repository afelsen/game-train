import { describe, expect, it } from 'vitest';

import { createInitialBackgammonState } from './backgammon-engine';
import { encodeWildBgPosition, toWildBgPosition, wildBgPhase } from './wildbg';

describe('WildBG board encoding', () => {
  it('matches WildBG starting-point orientation for player zero', () => {
    const position = toWildBgPosition(createInitialBackgammonState(), 0);
    expect(position.pips).toEqual([
      0, -2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0,
      0, 2, 0,
    ]);
    expect(position.xOff).toBe(0);
    expect(position.oOff).toBe(0);
    expect(wildBgPhase(position)).toBe('contact');
    expect(encodeWildBgPosition(position, 'contact')).toHaveLength(202);
  });

  it('rotates and swaps the same board for player one', () => {
    const position = toWildBgPosition(createInitialBackgammonState(), 1);
    expect(position.pips).toEqual([
      0, -2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0,
      0, 2, 0,
    ]);
  });

  it('uses the 186-input race encoding after contact has ended', () => {
    const state = createInitialBackgammonState();
    state.points = Array(24).fill(0);
    state.points[0] = 15;
    state.points[23] = -15;
    const position = toWildBgPosition(state, 0);
    expect(wildBgPhase(position)).toBe('race');
    expect(encodeWildBgPosition(position, 'race')).toHaveLength(186);
  });
});
