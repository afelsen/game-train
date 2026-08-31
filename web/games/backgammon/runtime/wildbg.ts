import * as ort from 'onnxruntime-web/wasm';

import {
  applyMoveSequence,
  type BackgammonMove,
  type BackgammonPlayer,
  type BackgammonState,
} from './backgammon-engine';

type Phase = 'contact' | 'race';

export type WildBgEvaluation = {
  sequence: BackgammonMove[];
  equity: number;
  winChance: number;
};

type WildBgPosition = {
  pips: number[];
  xOff: number;
  oOff: number;
};

const sessions = new Map<Phase, Promise<ort.InferenceSession>>();

function assetRoot() {
  const url = new URL(window.location.href);
  const gameSegment = '/backgammon';
  const gameIndex = url.pathname.indexOf(gameSegment);
  const basePath = gameIndex >= 0 ? url.pathname.slice(0, gameIndex + 1) : '/';
  return `${url.origin}${basePath}models/wildbg/`;
}

async function sessionFor(phase: Phase) {
  let pending = sessions.get(phase);
  if (!pending) {
    const root = assetRoot();
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.wasmPaths = root;
    pending = ort.InferenceSession.create(`${root}${phase}.onnx`, {
      executionProviders: ['wasm'],
      graphOptimizationLevel: 'all',
    });
    sessions.set(phase, pending);
  }
  return pending;
}

/** Convert the app board to WildBG's x-to-move point of view. */
export function toWildBgPosition(
  state: BackgammonState,
  player: BackgammonPlayer = state.turn,
): WildBgPosition {
  const pips = Array<number>(26).fill(0);
  for (let point = 1; point <= 24; point += 1) {
    const appValue = state.points[point - 1];
    if (player === 0) pips[point] = appValue;
    else pips[25 - point] = appValue === 0 ? 0 : -appValue;
  }
  if (player === 0) {
    pips[25] = state.bar[0];
    pips[0] = state.bar[1] ? -state.bar[1] : 0;
    return { pips, xOff: state.off[0], oOff: state.off[1] };
  }
  pips[25] = state.bar[1];
  pips[0] = state.bar[0] ? -state.bar[0] : 0;
  return { pips, xOff: state.off[1], oOff: state.off[0] };
}

export function wildBgPhase(position: WildBgPosition): Phase {
  const lastOwn = position.pips.findLastIndex((pip) => pip > 0);
  const firstOpponent = position.pips.findIndex((pip) => pip < 0);
  return lastOwn > firstOpponent ? 'contact' : 'race';
}

function tdInputs(checkers: number) {
  if (checkers <= 0) return [0, 0, 0, 0];
  if (checkers === 1) return [1, 0, 0, 0];
  if (checkers === 2) return [0, 1, 0, 0];
  return [0, 0, 1, checkers - 3];
}

export function encodeWildBgPosition(position: WildBgPosition, phase: Phase) {
  const inputs = [position.xOff, position.oOff];
  if (phase === 'contact') {
    inputs.push(...tdInputs(position.pips[25]));
    for (let point = 1; point <= 24; point += 1)
      inputs.push(...tdInputs(position.pips[point]));
    for (let point = 0; point <= 24; point += 1)
      inputs.push(...tdInputs(-position.pips[point]));
  } else {
    for (let point = 1; point <= 23; point += 1)
      inputs.push(...tdInputs(position.pips[point]));
    for (let point = 2; point <= 24; point += 1)
      inputs.push(...tdInputs(-position.pips[point]));
  }
  return inputs;
}

function terminalEvaluation(state: BackgammonState, player: BackgammonPlayer) {
  if (state.winner === null) return null;
  return {
    equity: state.winner === player ? 1 : -1,
    winChance: state.winner === player ? 1 : 0,
  };
}

async function evaluatePositions(positions: WildBgPosition[], phase: Phase) {
  const session = await sessionFor(phase);
  const width = phase === 'contact' ? 202 : 186;
  // The published checkpoints have a fixed batch dimension of one. WildBG's
  // Rust runtime rewrites it dynamically; in browsers we keep the originals
  // intact and run the candidate positions concurrently instead.
  return Promise.all(
    positions.map(async (position) => {
      const data = new Float32Array(encodeWildBgPosition(position, phase));
      const results = await session.run({
        [session.inputNames[0]]: new ort.Tensor('float32', data, [1, width]),
      });
      const output = results[session.outputNames[0]].data as Float32Array;
      const winNormal = output[0];
      const winGammon = output[1];
      const winBackgammon = output[2];
      const loseNormal = output[3];
      const loseGammon = output[4];
      const loseBackgammon = output[5];
      return {
        winChance: winNormal + winGammon + winBackgammon,
        equity:
          winNormal -
          loseNormal +
          2 * (winGammon - loseGammon) +
          3 * (winBackgammon - loseBackgammon),
      };
    }),
  );
}

export async function rankWithWildBg(
  state: BackgammonState,
  sequences: BackgammonMove[][],
): Promise<WildBgEvaluation[]> {
  if (!sequences.length) return [];
  const player = state.turn;
  const evaluations: Array<WildBgEvaluation | undefined> = Array(
    sequences.length,
  );
  const groups = new Map<
    Phase,
    Array<{ index: number; position: WildBgPosition }>
  >();

  sequences.forEach((sequence, index) => {
    const after = applyMoveSequence(state, sequence);
    const terminal = terminalEvaluation(after, player);
    if (terminal) {
      evaluations[index] = { sequence, ...terminal };
      return;
    }
    const position = toWildBgPosition(after, player);
    const phase = wildBgPhase(position);
    groups.set(phase, [...(groups.get(phase) ?? []), { index, position }]);
  });

  await Promise.all(
    [...groups.entries()].map(async ([phase, group]) => {
      const values = await evaluatePositions(
        group.map(({ position }) => position),
        phase,
      );
      group.forEach(({ index }, groupIndex) => {
        evaluations[index] = {
          sequence: sequences[index],
          ...values[groupIndex],
        };
      });
    }),
  );

  return evaluations
    .filter((item): item is WildBgEvaluation => Boolean(item))
    .sort((left, right) => right.equity - left.equity);
}

export async function warmWildBg() {
  await Promise.all([sessionFor('contact'), sessionFor('race')]);
}
