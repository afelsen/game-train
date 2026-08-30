import { describe, expect, it } from 'vitest';
import {
  applyMoveSequence,
  checkerCount,
  createInitialBackgammonState,
  legalMoveSequences,
  legalMovesForDie,
  type BackgammonState,
} from './backgammon-engine';

function emptyState(overrides: Partial<BackgammonState> = {}): BackgammonState {
  return {
    points: Array<number>(24).fill(0),
    bar: [0, 0],
    off: [0, 0],
    turn: 0,
    dice: [],
    moveNumber: 0,
    winner: null,
    ...overrides,
  };
}

describe('Backgammon rules engine', () => {
  it('creates the standard position with 15 checkers per player', () => {
    const state = createInitialBackgammonState();
    expect(checkerCount(state, 0)).toBe(15);
    expect(checkerCount(state, 1)).toBe(15);
  });

  it('generates complete legal sequences for an opening roll', () => {
    const state = { ...createInitialBackgammonState(), dice: [3, 1] };
    const sequences = legalMoveSequences(state);
    expect(sequences.length).toBeGreaterThan(0);
    expect(sequences.every((sequence) => sequence.length === 2)).toBe(true);
    for (const sequence of sequences) {
      const result = applyMoveSequence(state, sequence);
      expect(checkerCount(result, 0)).toBe(15);
      expect(checkerCount(result, 1)).toBe(15);
    }
  });

  it('forces bar entry before moving another checker', () => {
    const points = Array<number>(24).fill(0);
    points[5] = 14;
    points[0] = -15;
    const state = emptyState({ points, bar: [1, 0], dice: [3, 1] });
    expect(
      legalMoveSequences(state).every(
        (sequence) => sequence[0]?.from === 'bar',
      ),
    ).toBe(true);
  });

  it('hits a blot and places the opponent on the bar', () => {
    const points = Array<number>(24).fill(0);
    points[7] = 1;
    points[4] = -1;
    const state = emptyState({ points, off: [14, 14] });
    const move = legalMovesForDie(state, 3)[0];
    expect(move).toMatchObject({ from: 8, to: 5, hit: true });
    const result = applyMoveSequence(state, [move]);
    expect(result.bar[1]).toBe(1);
    expect(result.points[4]).toBe(1);
  });

  it('blocks landing on a point occupied by two opponents', () => {
    const points = Array<number>(24).fill(0);
    points[7] = 1;
    points[4] = -2;
    const state = emptyState({ points, off: [14, 13] });
    expect(legalMovesForDie(state, 3)).toEqual([]);
  });

  it('allows bearing off only after every checker is home', () => {
    const points = Array<number>(24).fill(0);
    points[5] = 14;
    points[6] = 1;
    const outsideHome = emptyState({ points });
    expect(
      legalMovesForDie(outsideHome, 6).some((move) => move.to === 'off'),
    ).toBe(false);

    points[6] = 0;
    points[5] = 0;
    points[0] = 1;
    const home = emptyState({ points, off: [14, 15] });
    expect(legalMovesForDie(home, 6)).toContainEqual({
      from: 1,
      to: 'off',
      die: 6,
      hit: false,
    });
  });

  it('uses four moves for playable doubles', () => {
    const points = Array<number>(24).fill(0);
    points[7] = 15;
    const state = emptyState({ points, dice: [1, 1] });
    const sequences = legalMoveSequences(state);
    expect(sequences.length).toBeGreaterThan(0);
    expect(sequences.every((sequence) => sequence.length === 4)).toBe(true);
  });
});
