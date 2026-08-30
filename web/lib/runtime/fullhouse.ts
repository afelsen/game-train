import { eval7CompatibleScore } from './poker-evaluator';
import type { Strategy, StrategyAction } from './contracts';
import type { BrowserPokerHand } from './poker-engine';

export const FULLHOUSE_PROVIDER_ID = 'fullhouse-deep-cfr-experimental-hu';
export const FULLHOUSE_PROVIDER = {
  id: FULLHOUSE_PROVIDER_ID,
  version: 'e504793-browser-1',
  experimental: true,
};

const ACTIONS = ['fold', 'check-call', 'bet-half-pot', 'bet-pot', 'all-in'] as const;
const RANKS = '23456789TJQKA';
const SUITS = 'cdhs';
const STARTING_STACK = 10_000;
const MAX_EVAL7_SCORE = 135_004_160;

type EncodedArray = { shape: number[]; data: string };
export type FullhouseArtifact = {
  schemaVersion: string;
  modelId: string;
  modelVersion: string;
  arrays: Record<string, EncodedArray>;
  equity: Record<'paired' | 'suited' | 'offsuit', EncodedArray>;
};
type Tensor = { shape: number[]; data: Float32Array };
export type LoadedFullhouseModel = {
  arrays: Record<string, Tensor>;
  equity: Record<'paired' | 'suited' | 'offsuit', Tensor>;
};

let modelPromise: Promise<LoadedFullhouseModel> | null = null;

function decodeFloat32(encoded: EncodedArray): Tensor {
  const binary = atob(encoded.data);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  if (bytes.byteLength % 4 !== 0) throw new Error('Invalid Fullhouse tensor byte length');
  const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  return { shape: encoded.shape, data: new Float32Array(copy) };
}

async function loadModel() {
  if (!modelPromise) {
    modelPromise = fetch(new URL('models/fullhouse-v17.json', document.baseURI))
      .then(async (response) => {
        if (!response.ok) throw new Error(`Fullhouse checkpoint failed to load (${response.status})`);
        return response.json() as Promise<FullhouseArtifact>;
      })
      .then((artifact) => {
        if (artifact.schemaVersion !== 'game-train-fullhouse/v1' || artifact.modelId !== FULLHOUSE_PROVIDER_ID) {
          throw new Error('Fullhouse checkpoint contract is incompatible');
        }
        return decodeFullhouseArtifact(artifact);
      });
  }
  return modelPromise;
}

export function decodeFullhouseArtifact(artifact: FullhouseArtifact): LoadedFullhouseModel {
  return {
    arrays: Object.fromEntries(Object.entries(artifact.arrays).map(([name, value]) => [name, decodeFloat32(value)])),
    equity: {
      paired: decodeFloat32(artifact.equity.paired),
      suited: decodeFloat32(artifact.equity.suited),
      offsuit: decodeFloat32(artifact.equity.offsuit),
    },
  };
}

const cardIndex = (card: string) => SUITS.indexOf(card[1]) * 13 + RANKS.indexOf(card[0]);

function straightOutRanks(present: boolean[]) {
  const outs = new Set<number>();
  for (let start = 0; start < 9; start += 1) {
    const missing: number[] = [];
    for (let rank = start; rank < start + 5; rank += 1) if (!present[rank]) missing.push(rank);
    if (missing.length === 1) outs.add(missing[0]);
  }
  const wheel = [12, 0, 1, 2, 3];
  const missing = wheel.filter((rank) => !present[rank]);
  if (missing.length === 1) outs.add(missing[0]);
  return outs.size;
}

function drawFeatures(holes: number[], board: number[], street: number) {
  if (street >= 3 || board.length === 0) return [0, 0, 0, 0, 0];
  const cards = [...holes, ...board];
  const suits = [0, 0, 0, 0];
  cards.forEach((card) => { suits[Math.floor(card / 13)] += 1; });
  const maximum = Math.max(...suits);
  const flushDraw = maximum === 4;
  const flushSuit = flushDraw ? suits.indexOf(maximum) : -1;
  const boardFlushRanks = board.filter((card) => Math.floor(card / 13) === flushSuit).map((card) => card % 13);
  const heroFlushRanks = holes.filter((card) => Math.floor(card / 13) === flushSuit).map((card) => card % 13);
  const nutFlushDraw = flushDraw && heroFlushRanks.length > 0 && Math.max(...heroFlushRanks) === Math.max(...boardFlushRanks, ...heroFlushRanks);
  const present = Array(13).fill(false) as boolean[];
  cards.forEach((card) => { present[card % 13] = true; });
  const straightRanks = straightOutRanks(present);
  const overlap = flushDraw && straightRanks > 0 ? Math.min(straightRanks, 2) : 0;
  const outs = (flushDraw ? 9 : 0) + straightRanks * 4 - overlap;
  return [Number(flushDraw), Number(straightRanks >= 2), Number(straightRanks === 1), outs / 20, Number(nutFlushDraw)];
}

function textureFeatures(board: number[], heroHigh: number) {
  if (!board.length) return [0, 0, 0, 0, 0];
  const ranks = board.map((card) => card % 13);
  const suits = board.map((card) => Math.floor(card / 13));
  const paired = new Set(ranks).size < ranks.length;
  const monotone = new Set(suits).size === 1;
  let close = 0;
  let pairs = 0;
  for (let left = 0; left < ranks.length; left += 1) {
    for (let right = left + 1; right < ranks.length; right += 1) {
      pairs += 1;
      if (Math.abs(ranks[left] - ranks[right]) <= 2) close += 1;
    }
  }
  const present = new Set(ranks);
  let straightPossible = false;
  for (let start = 0; start < 9; start += 1) {
    if ([0, 1, 2, 3, 4].filter((offset) => present.has(start + offset)).length >= 3) straightPossible = true;
  }
  if ([12, 0, 1, 2, 3].filter((rank) => present.has(rank)).length >= 3) straightPossible = true;
  return [Number(paired), Number(monotone), ranks.filter((rank) => rank > heroHigh).length / 5, pairs ? close / pairs : 0, Number(straightPossible)];
}

function equityAt(table: Tensor, row: number, column = 0) {
  return table.data[table.shape.length === 1 ? row : row * table.shape[1] + column];
}

export function encodeFullhouseFeatures(hand: BrowserPokerHand, model: LoadedFullhouseModel) {
  if (hand.toAct === null || hand.terminal) throw new Error('Fullhouse requires an active decision');
  const actor = hand.seats[hand.toAct];
  const holes = (actor.holeCards ?? []).map(cardIndex);
  const board = hand.board.map(cardIndex);
  const ranks = holes.map((card) => card % 13);
  const suits = holes.map((card) => Math.floor(card / 13));
  const high = Math.max(...ranks);
  const low = Math.min(...ranks);
  const street = { preflop: 0, flop: 1, turn: 2, river: 3 }[hand.street as 'preflop' | 'flop' | 'turn' | 'river'];
  const features = new Float32Array(51);

  features[0] = ranks[0] === ranks[1]
    ? equityAt(model.equity.paired, ranks[0])
    : suits[0] === suits[1]
      ? equityAt(model.equity.suited, high, low)
      : equityAt(model.equity.offsuit, high, low);
  if (street > 0) features[1] = eval7CompatibleScore([...(actor.holeCards ?? []), ...hand.board]) / MAX_EVAL7_SCORE;
  drawFeatures(holes, board, street).forEach((value, index) => { features[2 + index] = value; });
  features[7] = high / 12;
  features[8] = low / 12;
  features[9] = Number(suits[0] === suits[1]);
  features[10] = Number(ranks[0] === ranks[1]);
  features[11] = high === low ? 0 : (high - low - 1) / 12;
  textureFeatures(board, high).forEach((value, index) => { features[12 + index] = value; });
  features[17 + street] = 1;
  features[21 + Math.min((actor.seat - hand.button + hand.playerCount) % hand.playerCount, 5)] = 1;
  features[27] = hand.pot / STARTING_STACK;
  features[28] = actor.stack / STARTING_STACK;
  const active = hand.seats.filter((seat) => seat.status !== 'folded');
  const minimumStack = Math.min(...active.map((seat) => seat.stack));
  features[29] = Math.min(Math.max(minimumStack / Math.max(hand.pot, 1), 0), 10) / 10;
  const owed = hand.amountToCall();
  features[30] = owed > 0 ? owed / (hand.pot + owed) : 0;
  hand.seats
    .filter((seat) => seat.seat !== actor.seat && seat.status !== 'folded')
    .map((seat) => seat.stack)
    .sort((left, right) => right - left)
    .slice(0, 5)
    .forEach((stack, index) => { features[31 + index] = stack / STARTING_STACK; });
  const raises = hand.actions.filter((action) => action.street === hand.street && (action.type === 'raise-to' || action.type === 'all-in'));
  const lastRaiser = raises.at(-1)?.seat ?? null;
  const blindOnly = hand.street === 'preflop' && hand.currentBet <= (hand.bigBlind ?? 100);
  features[36] = Math.min(raises.length, 4) / 4;
  features[37] = Number(lastRaiser !== null || (hand.currentBet > 0 && !blindOnly));
  features[38] = Number(lastRaiser === actor.seat);
  features[39] = actor.streetCommitted / STARTING_STACK;
  features[40] = actor.handCommitted / STARTING_STACK;
  features[41] = hand.currentBet / Math.max(hand.pot, 1);
  features[42] = owed / Math.max(actor.stack, 1);
  features[43] = Math.max(...active.filter((seat) => seat.seat !== actor.seat).map((seat) => seat.streetCommitted), 0) / STARTING_STACK;
  features[44] = Math.max(...active.filter((seat) => seat.seat !== actor.seat).map((seat) => seat.handCommitted), 0) / STARTING_STACK;
  features[45] = active.length / 6;

  const legal = abstractLegalMask(hand);
  legal.forEach((value, index) => { features[46 + index] = value; });
  return { features, legal };
}

function abstractLegalMask(hand: BrowserPokerHand) {
  if (hand.toAct === null) return new Float32Array(5);
  const actor = hand.seats[hand.toAct];
  const owed = hand.amountToCall();
  const legal = new Float32Array(5);
  legal[0] = Number(owed > 0);
  legal[1] = 1;
  const raise = hand.legalActions().find((action) => action.type === 'raise-to');
  if (actor.stack > owed && raise?.minAmount) {
    const potAfterCall = hand.pot + owed;
    const room = actor.stack - owed;
    const half = Math.round(0.5 * potAfterCall);
    legal[2] = Number(half >= hand.lastFullRaise && room > half);
    legal[3] = Number(potAfterCall >= hand.lastFullRaise && room > potAfterCall);
    const opposingStacks = hand.seats.filter((seat) => seat.seat !== actor.seat && seat.status !== 'folded').map((seat) => seat.stack);
    const effective = Math.min(actor.stack, Math.max(...opposingStacks, 0) || actor.stack);
    legal[4] = Number(effective / Math.max(hand.pot, 1) < 4);
  }
  return legal;
}

function linear(input: Float32Array, weight: Tensor, bias: Tensor) {
  const output = new Float32Array(weight.shape[0]);
  const width = weight.shape[1];
  for (let row = 0; row < output.length; row += 1) {
    let value = bias.data[row];
    const offset = row * width;
    for (let column = 0; column < width; column += 1) value += input[column] * weight.data[offset + column];
    output[row] = value;
  }
  return output;
}

function leakyRelu(values: Float32Array) {
  return Float32Array.from(values, (value) => value > 0 ? value : 0.01 * value);
}

function layerNorm(values: Float32Array, gamma: Tensor, beta: Tensor) {
  let mean = 0;
  values.forEach((value) => { mean += value; });
  mean /= values.length;
  let variance = 0;
  values.forEach((value) => { variance += (value - mean) ** 2; });
  variance /= values.length;
  const denominator = Math.sqrt(variance + 1e-5);
  return Float32Array.from(values, (value, index) => gamma.data[index] * (value - mean) / denominator + beta.data[index]);
}

export function inferFullhouseFeatures(features: Float32Array, legal: Float32Array, model: LoadedFullhouseModel) {
  const arrays = model.arrays;
  let hidden = leakyRelu(layerNorm(linear(features, arrays.trunk_w0, arrays.trunk_b0), arrays.trunk_ln0_g, arrays.trunk_ln0_b));
  hidden = leakyRelu(layerNorm(linear(hidden, arrays.trunk_w1, arrays.trunk_b1), arrays.trunk_ln1_g, arrays.trunk_ln1_b));
  let value = leakyRelu(linear(hidden, arrays.val_w0, arrays.val_b0));
  value = linear(value, arrays.val_w1, arrays.val_b1);
  let advantage = leakyRelu(linear(hidden, arrays.adv_w0, arrays.adv_b0));
  advantage = linear(advantage, arrays.adv_w1, arrays.adv_b1);
  let sum = 0;
  let count = 0;
  for (let index = 0; index < legal.length; index += 1) {
    if (legal[index]) { sum += advantage[index]; count += 1; }
  }
  if (!count) throw new Error('Fullhouse has no legal abstract actions');
  const mean = sum / count;
  const regrets = Float32Array.from(advantage, (item, index) => legal[index] ? Math.max(value[0] + item - mean, 0) : 0);
  const total = regrets.reduce((accumulator, item) => accumulator + item, 0);
  return total > 0
    ? Float32Array.from(regrets, (item) => item / total)
    : Float32Array.from(legal, (item) => item / count);
}

function mapAction(hand: BrowserPokerHand, name: typeof ACTIONS[number]) {
  const legal = hand.legalActions();
  if (name === 'fold') return legal.some((action) => action.type === 'fold') ? { type: 'fold', amount: null } : null;
  if (name === 'check-call') {
    if (legal.some((action) => action.type === 'check')) return { type: 'check', amount: null };
    if (legal.some((action) => action.type === 'call')) return { type: 'call', amount: null };
    return null;
  }
  if (name === 'all-in') return legal.some((action) => action.type === 'all-in') ? { type: 'all-in', amount: null } : null;
  const raise = legal.find((action) => action.type === 'raise-to');
  if (!raise || raise.minAmount === null || raise.maxAmount === null || hand.toAct === null) return null;
  const fraction = name === 'bet-half-pot' ? 0.5 : 1;
  const actor = hand.seats[hand.toAct];
  const owed = hand.amountToCall();
  const target = owed === 0
    ? actor.streetCommitted + Math.round(hand.pot * fraction)
    : hand.currentBet + Math.round((hand.pot + Math.min(owed, actor.stack)) * fraction);
  return { type: 'raise-to', amount: Math.max(raise.minAmount, Math.min(target, raise.maxAmount)) };
}

export async function fullhouseStrategy(hand: BrowserPokerHand): Promise<Strategy> {
  const started = performance.now();
  const model = await loadModel();
  const { features, legal } = encodeFullhouseFeatures(hand, model);
  const probabilities = inferFullhouseFeatures(features, legal, model);
  const modelActions: StrategyAction[] = ACTIONS.map((name, index) => ({
    abstractAction: name,
    probability: probabilities[index],
    available: mapAction(hand, name) !== null,
    legalAction: mapAction(hand, name),
  }));
  const mapped = modelActions.filter((action) => action.available && action.probability > 0 && action.legalAction);
  const total = mapped.reduce((sum, action) => sum + action.probability, 0);
  const actions = total > 0
    ? mapped.map((action) => ({ ...action, probability: action.probability / total }))
    : [{ abstractAction: 'check-call', probability: 1, available: true, legalAction: mapAction(hand, 'check-call') }];
  return {
    provider: { modelId: FULLHOUSE_PROVIDER_ID },
    status: 'ok',
    actions,
    modelActions,
    diagnostics: { exactState: true, inferenceMs: performance.now() - started, warnings: [], message: null },
  };
}
