import type { BestHand } from './contracts';

const RANKS = '23456789TJQKA';

type EvaluatedHand = BestHand & { score: number[] };

const rankValue = (card: string) => RANKS.indexOf(card[0]) + 2;

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
function compareScores(left: number[], right: number[]) {
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference !== 0) return difference;
  }
  return 0;
}

function evaluateFive(cards: string[]): EvaluatedHand {
  const values = cards.map(rankValue).sort((a, b) => b - a);
  const groups = new Map<number, number>();
  values.forEach((value) => groups.set(value, (groups.get(value) ?? 0) + 1));
  const orderedGroups = [...groups.entries()].sort(
    (left, right) => right[1] - left[1] || right[0] - left[0],
  );
  const flush = cards.every((card) => card[1] === cards[0][1]);
  const unique = [...new Set(values)];
  const wheel = unique.join(',') === '14,5,4,3,2';
  const straight =
    unique.length === 5 && (wheel || unique[0] - unique[4] === 4);
  const straightHigh = wheel ? 5 : unique[0];

  let category: string;
  let score: number[];
  if (straight && flush) {
    category = 'straight-flush';
    score = [8, straightHigh];
  } else if (orderedGroups[0][1] === 4) {
    category = 'four-of-a-kind';
    score = [7, orderedGroups[0][0], orderedGroups[1][0]];
  } else if (orderedGroups[0][1] === 3 && orderedGroups[1][1] === 2) {
    category = 'full-house';
    score = [6, orderedGroups[0][0], orderedGroups[1][0]];
  } else if (flush) {
    category = 'flush';
    score = [5, ...values];
  } else if (straight) {
    category = 'straight';
    score = [4, straightHigh];
  } else if (orderedGroups[0][1] === 3) {
    category = 'three-of-a-kind';
    score = [3, orderedGroups[0][0], ...orderedGroups.slice(1).map(([value]) => value).sort((a, b) => b - a)];
  } else if (orderedGroups[0][1] === 2 && orderedGroups[1][1] === 2) {
    const pairs = orderedGroups.slice(0, 2).map(([value]) => value).sort((a, b) => b - a);
    category = 'two-pair';
    score = [2, ...pairs, orderedGroups[2][0]];
  } else if (orderedGroups[0][1] === 2) {
    category = 'one-pair';
    score = [1, orderedGroups[0][0], ...orderedGroups.slice(1).map(([value]) => value).sort((a, b) => b - a)];
  } else {
    category = 'high-card';
    score = [0, ...values];
  }
  return { cards, category, score, importance: cardImportance(cards, category) };
}

export function bestHand(cards: string[]): EvaluatedHand | null {
  if (cards.length < 5) return null;
  return combinations(cards, 5)
    .map(evaluateFive)
    .reduce((best, candidate) =>
      compareScores(candidate.score, best.score) > 0 ? candidate : best,
    );
}

export function compareHands(left: string[], right: string[]) {
  const leftHand = bestHand(left);
  const rightHand = bestHand(right);
  if (!leftHand || !rightHand) throw new Error('At least five cards are required');
  return compareScores(leftHand.score, rightHand.score);
}

export function cardImportance(cards: string[], category: string) {
  if (category === 'straight' || category === 'straight-flush') {
    return Object.fromEntries(cards.map((card) => [card, 3]));
  }
  const groups = new Map<string, string[]>();
  cards.forEach((card) => groups.set(card[0], [...(groups.get(card[0]) ?? []), card]));
  const ordered = [...groups.values()].sort(
    (left, right) => right.length - left.length || rankValue(right[0]) - rankValue(left[0]),
  );
  const levels =
    category === 'four-of-a-kind'
      ? [3, 1]
      : category === 'full-house'
        ? [3, 3]
        : category === 'three-of-a-kind'
          ? [3, 1, 1]
          : category === 'two-pair'
            ? [3, 3, 1]
            : category === 'one-pair'
              ? [3, 1, 1, 1]
              : [3, 2, 1, 1, 1];
  return Object.fromEntries(
    ordered.flatMap((group, index) => group.map((card) => [card, levels[index] ?? 1])),
  );
}

export function preflopHighlight(cards: string[]) {
  if (cards[0][0] === cards[1][0]) {
    return { category: 'one-pair', importance: Object.fromEntries(cards.map((card) => [card, 3])) };
  }
  const ordered = [...cards].sort((left, right) => rankValue(right) - rankValue(left));
  return { category: 'high-card', importance: { [ordered[0]]: 3, [ordered[1]]: 1 } };
}
