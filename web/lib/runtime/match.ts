export const DEFAULT_BUY_IN = 10_000;

/**
 * Preserve surviving stacks, automatically rebuy busted bots, and require an
 * explicit choice before replenishing the hero's stack.
 */
export function prepareNextHandStacks(
  stacks: number[],
  rebuyHero: boolean,
  heroSeat = 0,
) {
  if (stacks[heroSeat] <= 0 && !rebuyHero) return null;
  return stacks.map((stack) => (stack > 0 ? stack : DEFAULT_BUY_IN));
}
