import { bestHand } from './poker-evaluator';

const RANKS = '23456789TJQKA';
const SUITS = 'cdhs';
const FULL_DECK = [...SUITS].flatMap((suit) =>
  [...RANKS].map((rank) => `${rank}${suit}`),
);

export type WeightedCombo = { cards: string[]; weight: number };

export type EquityRequest = {
  holeCards: string[];
  board?: string[];
  sampleLimit?: number;
  opponentCount?: number;
  opponentWeights?: WeightedCombo[];
  opponentRanges?: WeightedCombo[][];
};

export type EquityResult = {
  schemaVersion: '1.0.0';
  method: 'exact' | 'sampled';
  samples: number;
  wins: number;
  ties: number;
  losses: number;
  equity: number;
  standardError: number;
  opponentCount: number;
  playerCount: number;
  opponentRange: 'uniform-random' | 'action-weighted-v1';
};

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

function compareScores(left: number[], right: number[]) {
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference !== 0) return difference;
  }
  return 0;
}

function validateRequest(request: EquityRequest) {
  const board = request.board ?? [];
  const opponentCount = request.opponentCount ?? 1;
  const sampleLimit = request.sampleLimit ?? 20_000;
  if (request.holeCards.length !== 2)
    throw new Error('Equity requires exactly two hole cards');
  if (board.length > 5)
    throw new Error('Board cannot contain more than five cards');
  if (
    !Number.isInteger(opponentCount) ||
    opponentCount < 1 ||
    opponentCount > 5
  ) {
    throw new Error('opponentCount must be an integer from 1 to 5');
  }
  if (!Number.isInteger(sampleLimit) || sampleLimit < 1) {
    throw new Error('sampleLimit must be a positive integer');
  }
  const known = [...request.holeCards, ...board];
  if (known.some((card) => !FULL_DECK.includes(card)))
    throw new Error('Equity cards are invalid');
  if (new Set(known).size !== known.length)
    throw new Error('Equity cards must be unique');
  if (request.opponentWeights && request.opponentRanges) {
    throw new Error('Use opponentWeights or opponentRanges, not both');
  }
  const ranges =
    request.opponentRanges ??
    (request.opponentWeights ? [request.opponentWeights] : undefined);
  if (ranges && ranges.length !== opponentCount) {
    throw new Error('opponentRanges must contain one range per opponent');
  }
  return { board, opponentCount, sampleLimit, ranges };
}

function normalizedRanges(ranges: WeightedCombo[][], remaining: Set<string>) {
  return ranges.map((range) => {
    const valid = range.map(({ cards, weight }) => {
      if (
        !Array.isArray(cards) ||
        cards.length !== 2 ||
        cards[0] === cards[1] ||
        cards.some((card) => !remaining.has(card)) ||
        !Number.isFinite(weight) ||
        weight < 0
      ) {
        throw new Error('Invalid weighted opponent combo');
      }
      return { cards, weight };
    });
    const total = valid.reduce((sum, item) => sum + item.weight, 0);
    if (valid.length === 0 || total <= 0)
      throw new Error('Weighted opponent range has no probability mass');
    let cumulative = 0;
    return valid.map((item) => ({
      cards: item.cards,
      cumulative: (cumulative += item.weight / total),
    }));
  });
}

function chooseWeighted(
  range: Array<{ cards: string[]; cumulative: number }>,
  random: () => number,
) {
  const value = random();
  return (range.find((item) => value <= item.cumulative) ?? range.at(-1))!
    .cards;
}

function tick() {
  return new Promise<void>((resolve) => setTimeout(resolve, 0));
}

/**
 * Deterministic browser-side Hold'em equity. It samples only unknown cards and
 * never reads the hidden cards held by a live BrowserPokerHand.
 */
export async function calculateEquity(
  request: EquityRequest,
  signal?: AbortSignal | null,
): Promise<EquityResult> {
  const { board, opponentCount, sampleLimit, ranges } =
    validateRequest(request);
  const remaining = FULL_DECK.filter(
    (card) => !request.holeCards.includes(card) && !board.includes(card),
  );
  const missingBoard = 5 - board.length;
  const cardsNeeded = opponentCount * 2 + missingBoard;
  if (cardsNeeded > remaining.length)
    throw new Error('Not enough unknown cards');

  const outcomeCount =
    combinationCount(remaining.length, 2) *
    combinationCount(remaining.length - 2, missingBoard);
  const exact = !ranges && opponentCount === 1 && outcomeCount <= sampleLimit;
  const random = seededRandom(
    hashSeed(
      `${ranges ? 'weighted-' : ''}equity-${opponentCount}|${[...request.holeCards].sort().join(',')}|${board.join(',')}`,
    ),
  );
  const weighted = ranges ? normalizedRanges(ranges, new Set(remaining)) : null;
  let wins = 0;
  let ties = 0;
  let losses = 0;
  let equityTotal = 0;
  let equitySquareTotal = 0;

  const score = (opponents: string[][], runout: string[]) => {
    const completeBoard = [...board, ...runout];
    const heroScore = bestHand([...request.holeCards, ...completeBoard])!.score;
    const opponentScores = opponents.map(
      (opponent) => bestHand([...opponent, ...completeBoard])!.score,
    );
    const comparisons = opponentScores.map((opponentScore) =>
      compareScores(heroScore, opponentScore),
    );
    let share: number;
    if (comparisons.every((comparison) => comparison > 0)) {
      wins += 1;
      share = 1;
    } else if (comparisons.every((comparison) => comparison >= 0)) {
      ties += 1;
      share =
        1 / (1 + comparisons.filter((comparison) => comparison === 0).length);
    } else {
      losses += 1;
      share = 0;
    }
    equityTotal += share;
    equitySquareTotal += share * share;
  };

  if (exact) {
    for (const opponent of combinations(remaining, 2)) {
      const runoutPool = remaining.filter((card) => !opponent.includes(card));
      for (const runout of combinations(runoutPool, missingBoard))
        score([opponent], runout);
    }
  } else {
    for (let sample = 0; sample < sampleLimit; sample += 1) {
      if (weighted) {
        const opponents: string[][] = [];
        const blocked = new Set<string>();
        for (const range of weighted) {
          let cards: string[] | null = null;
          for (let attempt = 0; attempt < 100; attempt += 1) {
            const candidate = chooseWeighted(range, random);
            if (candidate.every((card) => !blocked.has(card))) {
              cards = candidate;
              break;
            }
          }
          if (!cards)
            throw new Error(
              'Opponent ranges have no collision-free assignment',
            );
          opponents.push(cards);
          cards.forEach((card) => blocked.add(card));
        }
        const runoutPool = remaining.filter((card) => !blocked.has(card));
        score(
          opponents,
          drawWithoutReplacement(runoutPool, missingBoard, random),
        );
      } else {
        const drawn = drawWithoutReplacement(remaining, cardsNeeded, random);
        const opponents = Array.from({ length: opponentCount }, (_, index) =>
          drawn.slice(index * 2, index * 2 + 2),
        );
        score(opponents, drawn.slice(opponentCount * 2));
      }
      if (sample > 0 && sample % 500 === 0 && typeof window !== 'undefined') {
        await tick();
        signal?.throwIfAborted();
      }
    }
  }

  const samples = wins + ties + losses;
  const equity = equityTotal / samples;
  const variance = Math.max(0, equitySquareTotal / samples - equity * equity);
  return {
    schemaVersion: '1.0.0',
    method: exact ? 'exact' : 'sampled',
    samples,
    wins,
    ties,
    losses,
    equity,
    standardError: exact ? 0 : Math.sqrt(variance / samples),
    opponentCount,
    playerCount: opponentCount + 1,
    opponentRange: ranges ? 'action-weighted-v1' : 'uniform-random',
  };
}
