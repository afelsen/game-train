import { compareScores, evaluateFive } from './poker-evaluator';

const RANKS = '23456789TJQKA';
const SUITS = 'cdhs';
const FULL_DECK = [...SUITS].flatMap((suit) =>
  [...RANKS].map((rank) => `${rank}${suit}`),
);

export const HAND_CATEGORIES = [
  'high-card',
  'one-pair',
  'two-pair',
  'three-of-a-kind',
  'straight',
  'flush',
  'full-house',
  'four-of-a-kind',
  'straight-flush',
] as const;

export type HandCategory = (typeof HAND_CATEGORIES)[number];

export type HandChanceRequest = {
  holeCards: string[];
  board?: string[];
  sampleLimit?: number;
};

export type HandChanceResult = {
  schemaVersion: '1.0.0';
  method: 'exact' | 'sampled';
  samples: number;
  exact: Record<HandCategory, number>;
  combinations: Record<HandCategory, number>;
  atLeast: Record<HandCategory, number>;
  outs: Record<HandCategory, number>;
  baselineExact: Record<HandCategory, number>;
  baselineAtLeast: Record<HandCategory, number>;
  percentile75Exact: Record<HandCategory, number>;
  baselineSamples: number;
  baselineLabel: '75th percentile of random legal hands';
};

function emptyCounts() {
  return Object.fromEntries(
    HAND_CATEGORIES.map((category) => [category, 0]),
  ) as Record<HandCategory, number>;
}

function hashSeed(value: string) {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function seededRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function drawWithoutReplacement(
  cards: string[],
  count: number,
  random: () => number,
) {
  const pool = [...cards];
  for (let index = 0; index < count; index += 1) {
    const swap = index + Math.floor(random() * (pool.length - index));
    [pool[index], pool[swap]] = [pool[swap], pool[index]];
  }
  return pool.slice(0, count);
}

function combinations<T>(items: T[], count: number): T[][] {
  if (count === 0) return [[]];
  const result: T[][] = [];
  for (let index = 0; index <= items.length - count; index += 1) {
    for (const tail of combinations(items.slice(index + 1), count - 1)) {
      result.push([items[index], ...tail]);
    }
  }
  return result;
}

function combinationCount(items: number, count: number) {
  if (count < 0 || count > items) return 0;
  let result = 1;
  for (let index = 1; index <= count; index += 1) {
    result = (result * (items - count + index)) / index;
  }
  return result;
}

function participatingCategory(holeCards: string[], board: string[]) {
  const candidates = combinations([...holeCards, ...board], 5).filter((cards) =>
    cards.some((card) => holeCards.includes(card)),
  );
  let best = evaluateFive(candidates[0]);
  for (const cards of candidates.slice(1)) {
    const candidate = evaluateFive(cards);
    if (compareScores(candidate.score, best.score) > 0) best = candidate;
  }
  return best.category as HandCategory;
}

/** Hand categories an opponent could already hold using the current board. */
export function possibleCurrentOpponentCategories(
  knownCards: string[],
  board: string[],
) {
  const possible = new Set<HandCategory>();
  if (board.length < 3 || board.length > 5) return possible;
  const unavailable = new Set([...knownCards, ...board]);
  const remaining = FULL_DECK.filter((card) => !unavailable.has(card));
  for (const holeCards of combinations(remaining, 2)) {
    possible.add(participatingCategory(holeCards, board));
  }
  return possible;
}

function tick() {
  return new Promise<void>((resolve) => setTimeout(resolve, 0));
}

function validateRequest(request: HandChanceRequest) {
  const board = request.board ?? [];
  const sampleLimit = request.sampleLimit ?? 20_000;
  if (request.holeCards.length !== 2) {
    throw new Error('Hand chances require exactly two hole cards');
  }
  if (board.length > 5)
    throw new Error('Board cannot contain more than five cards');
  if (!Number.isInteger(sampleLimit) || sampleLimit < 1) {
    throw new Error('sampleLimit must be a positive integer');
  }
  const known = [...request.holeCards, ...board];
  if (known.some((card) => !FULL_DECK.includes(card)))
    throw new Error('Hand chance cards are invalid');
  if (new Set(known).size !== known.length)
    throw new Error('Hand chance cards must be unique');
  return { board, sampleLimit };
}

/** Calculate final hand-category probabilities using only public/hero cards. */
export async function calculateHandChances(
  request: HandChanceRequest,
  signal?: AbortSignal | null,
): Promise<HandChanceResult> {
  const { board, sampleLimit } = validateRequest(request);
  signal?.throwIfAborted();
  const remaining = FULL_DECK.filter(
    (card) => !request.holeCards.includes(card) && !board.includes(card),
  );
  const missingBoard = 5 - board.length;
  const runoutCount = combinationCount(remaining.length, missingBoard);
  const exactMethod = runoutCount <= sampleLimit;
  const counts = emptyCounts();
  const record = (runout: string[]) => {
    counts[participatingCategory(request.holeCards, [...board, ...runout])] +=
      1;
  };

  if (exactMethod) {
    for (const runout of combinations(remaining, missingBoard)) record(runout);
  } else {
    const random = seededRandom(
      hashSeed(
        `hand-chances|${[...request.holeCards].sort().join(',')}|${board.join(',')}`,
      ),
    );
    for (let sample = 0; sample < sampleLimit; sample += 1) {
      record(drawWithoutReplacement(remaining, missingBoard, random));
      if (sample > 0 && sample % 250 === 0) {
        signal?.throwIfAborted();
        if (typeof window !== 'undefined') await tick();
      }
    }
  }

  const samples = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const exact = emptyCounts();
  const atLeast = emptyCounts();
  let cumulative = 0;
  for (const category of [...HAND_CATEGORIES].reverse()) {
    exact[category] = counts[category] / samples;
    cumulative += counts[category];
    atLeast[category] = cumulative / samples;
  }

  const targetBaselineSamples = Math.min(5_000, sampleLimit);
  const baselineHandCount = Math.min(200, targetBaselineSamples);
  const runoutsPerBaselineHand = Math.max(
    1,
    Math.floor(targetBaselineSamples / baselineHandCount),
  );
  const baselineCounts = emptyCounts();
  const baselineByHand = Object.fromEntries(
    HAND_CATEGORIES.map((category) => [category, [] as number[]]),
  ) as Record<HandCategory, number[]>;
  const baselineRandom = seededRandom(
    hashSeed(
      `hand-baseline|${[...request.holeCards].sort().join(',')}|${board.join(',')}`,
    ),
  );

  for (let handIndex = 0; handIndex < baselineHandCount; handIndex += 1) {
    const baselineHole = drawWithoutReplacement(remaining, 2, baselineRandom);
    const runoutPool = remaining.filter((card) => !baselineHole.includes(card));
    const handCounts = emptyCounts();
    for (
      let runoutIndex = 0;
      runoutIndex < runoutsPerBaselineHand;
      runoutIndex += 1
    ) {
      const runout = drawWithoutReplacement(
        runoutPool,
        missingBoard,
        baselineRandom,
      );
      const category = participatingCategory(baselineHole, [
        ...board,
        ...runout,
      ]);
      baselineCounts[category] += 1;
      handCounts[category] += 1;
    }
    for (const category of HAND_CATEGORIES) {
      baselineByHand[category].push(
        handCounts[category] / runoutsPerBaselineHand,
      );
    }
    if (handIndex > 0 && handIndex % 20 === 0) {
      signal?.throwIfAborted();
      if (typeof window !== 'undefined') await tick();
    }
  }

  const baselineSamples = baselineHandCount * runoutsPerBaselineHand;
  const baselineExact = emptyCounts();
  const baselineAtLeast = emptyCounts();
  const percentile75Exact = emptyCounts();
  let baselineCumulative = 0;
  for (const category of [...HAND_CATEGORIES].reverse()) {
    baselineExact[category] = baselineCounts[category] / baselineSamples;
    const ordered = [...baselineByHand[category]].sort(
      (left, right) => left - right,
    );
    percentile75Exact[category] = ordered[Math.ceil(0.75 * ordered.length) - 1];
    baselineCumulative += baselineCounts[category];
    baselineAtLeast[category] = baselineCumulative / baselineSamples;
  }

  return {
    schemaVersion: '1.0.0',
    method: exactMethod ? 'exact' : 'sampled',
    samples,
    exact,
    combinations: { ...counts },
    atLeast,
    outs: { ...counts },
    baselineExact,
    baselineAtLeast,
    percentile75Exact,
    baselineSamples,
    baselineLabel: '75th percentile of random legal hands',
  };
}
