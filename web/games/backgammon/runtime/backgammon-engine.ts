export type BackgammonPlayer = 0 | 1;
export type BackgammonPoint = number | 'bar';
export type BackgammonDestination = number | 'off';

export type BackgammonMove = {
  from: BackgammonPoint;
  to: BackgammonDestination;
  die: number;
  hit: boolean;
};

export type BackgammonState = {
  /** Points 1–24. Positive checkers belong to player 0; negative to player 1. */
  points: number[];
  bar: [number, number];
  off: [number, number];
  turn: BackgammonPlayer;
  dice: number[];
  moveNumber: number;
  winner: BackgammonPlayer | null;
};

export function createInitialBackgammonState(): BackgammonState {
  const points = Array<number>(24).fill(0);
  points[23] = 2;
  points[12] = 5;
  points[7] = 3;
  points[5] = 5;
  points[0] = -2;
  points[11] = -5;
  points[16] = -3;
  points[18] = -5;
  return {
    points,
    bar: [0, 0],
    off: [0, 0],
    turn: 0,
    dice: [],
    moveNumber: 0,
    winner: null,
  };
}

function ownerValue(player: BackgammonPlayer) {
  return player === 0 ? 1 : -1;
}

function opponent(player: BackgammonPlayer): BackgammonPlayer {
  return player === 0 ? 1 : 0;
}

function destinationFor(player: BackgammonPlayer, from: number, die: number) {
  return player === 0 ? from - die : from + die;
}

function entryPoint(player: BackgammonPlayer, die: number) {
  return player === 0 ? 25 - die : die;
}

function isOpen(
  state: BackgammonState,
  player: BackgammonPlayer,
  point: number,
) {
  const value = state.points[point - 1];
  return (
    value === 0 ||
    Math.sign(value) === ownerValue(player) ||
    Math.abs(value) === 1
  );
}

function allCheckersHome(state: BackgammonState, player: BackgammonPlayer) {
  if (state.bar[player] > 0) return false;
  return state.points.every((value, index) => {
    if (Math.sign(value) !== ownerValue(player)) return true;
    const point = index + 1;
    return player === 0 ? point <= 6 : point >= 19;
  });
}

function canBearOff(
  state: BackgammonState,
  player: BackgammonPlayer,
  from: number,
  die: number,
) {
  if (!allCheckersHome(state, player)) return false;
  const destination = destinationFor(player, from, die);
  if (player === 0) {
    if (destination === 0) return true;
    if (destination > 0) return false;
    return !state.points.some((value, index) => index + 1 > from && value > 0);
  }
  if (destination === 25) return true;
  if (destination < 25) return false;
  return !state.points.some((value, index) => index + 1 < from && value < 0);
}

export function legalMovesForDie(state: BackgammonState, die: number) {
  if (state.winner !== null || die < 1 || die > 6) return [];
  const player = state.turn;
  if (state.bar[player] > 0) {
    const to = entryPoint(player, die);
    if (!isOpen(state, player, to)) return [];
    const target = state.points[to - 1];
    return [
      {
        from: 'bar',
        to,
        die,
        hit:
          Math.sign(target) === ownerValue(opponent(player)) &&
          Math.abs(target) === 1,
      } satisfies BackgammonMove,
    ];
  }

  const moves: BackgammonMove[] = [];
  for (let index = 0; index < state.points.length; index += 1) {
    if (Math.sign(state.points[index]) !== ownerValue(player)) continue;
    const from = index + 1;
    const destination = destinationFor(player, from, die);
    if (destination >= 1 && destination <= 24) {
      if (!isOpen(state, player, destination)) continue;
      const target = state.points[destination - 1];
      moves.push({
        from,
        to: destination,
        die,
        hit:
          Math.sign(target) === ownerValue(opponent(player)) &&
          Math.abs(target) === 1,
      });
    } else if (canBearOff(state, player, from, die)) {
      moves.push({ from, to: 'off', die, hit: false });
    }
  }
  return moves;
}

export function applyBackgammonMove(
  state: BackgammonState,
  move: BackgammonMove,
) {
  const next: BackgammonState = {
    ...state,
    points: [...state.points],
    bar: [...state.bar] as [number, number],
    off: [...state.off] as [number, number],
  };
  const player = state.turn;
  const value = ownerValue(player);
  if (move.from === 'bar') next.bar[player] -= 1;
  else next.points[move.from - 1] -= value;

  if (move.to === 'off') {
    next.off[player] += 1;
  } else {
    if (move.hit) {
      next.points[move.to - 1] = 0;
      next.bar[opponent(player)] += 1;
    }
    next.points[move.to - 1] += value;
  }
  if (next.off[player] === 15) next.winner = player;
  return next;
}

function diceOrders(dice: number[]) {
  if (dice.length !== 2) return [dice];
  if (dice[0] === dice[1]) return [[dice[0], dice[0], dice[0], dice[0]]];
  return [dice, [dice[1], dice[0]]];
}

function sequenceKey(sequence: BackgammonMove[]) {
  return sequence
    .map((move) => `${move.from}-${move.to}-${move.die}-${move.hit ? 1 : 0}`)
    .join('|');
}

export function legalMoveSequences(state: BackgammonState, dice = state.dice) {
  const candidates: BackgammonMove[][] = [];
  for (const order of diceOrders(dice)) {
    const walk = (
      current: BackgammonState,
      dieIndex: number,
      sequence: BackgammonMove[],
    ) => {
      if (dieIndex === order.length) {
        candidates.push(sequence);
        return;
      }
      const moves = legalMovesForDie(current, order[dieIndex]);
      if (moves.length === 0) {
        candidates.push(sequence);
        return;
      }
      for (const move of moves) {
        walk(applyBackgammonMove(current, move), dieIndex + 1, [
          ...sequence,
          move,
        ]);
      }
    };
    walk(state, 0, []);
  }

  const maximumMoves = Math.max(0, ...candidates.map((item) => item.length));
  let filtered = candidates.filter((item) => item.length === maximumMoves);
  if (maximumMoves === 1 && dice.length === 2 && dice[0] !== dice[1]) {
    const highestPlayableDie = Math.max(...filtered.map((item) => item[0].die));
    filtered = filtered.filter((item) => item[0].die === highestPlayableDie);
  }
  const unique = new Map<string, BackgammonMove[]>();
  for (const sequence of filtered) unique.set(sequenceKey(sequence), sequence);
  return [...unique.values()];
}

export function applyMoveSequence(
  state: BackgammonState,
  sequence: BackgammonMove[],
) {
  return sequence.reduce(applyBackgammonMove, state);
}

export function checkerCount(state: BackgammonState, player: BackgammonPlayer) {
  const onBoard = state.points.reduce(
    (total, value) =>
      total + (Math.sign(value) === ownerValue(player) ? Math.abs(value) : 0),
    0,
  );
  return onBoard + state.bar[player] + state.off[player];
}
