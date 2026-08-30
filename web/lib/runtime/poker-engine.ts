import type {
  ActionRecord,
  ActionType,
  HandResult,
  LegalAction,
  Observation,
  Seat,
  SerializedHand,
} from './contracts';
import { bestHand, compareHands, preflopHighlight } from './poker-evaluator';

const RANKS = '23456789TJQKA';
const SUITS = 'cdhs';
const FULL_DECK = [...SUITS].flatMap((suit) => [...RANKS].map((rank) => `${rank}${suit}`));

type Street = 'preflop' | 'flop' | 'turn' | 'river' | 'terminal';
export type PokerAction = { type: ActionType; amount?: number | null };

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
function shuffledDeck(seed: number) {
  const deck = [...FULL_DECK];
  const random = seededRandom(seed);
  for (let index = deck.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(random() * (index + 1));
    [deck[index], deck[swap]] = [deck[swap], deck[index]];
  }
  return deck;
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

const rankName: Record<string, string> = {
  A: 'aces', K: 'kings', Q: 'queens', J: 'jacks', T: 'tens',
  '9': '9s', '8': '8s', '7': '7s', '6': '6s', '5': '5s', '4': '4s', '3': '3s', '2': '2s',
};

export class BrowserPokerHand {
  static readonly schemaVersion = '1.0.0';

  readonly seed: number;
  readonly button: number;
  readonly startingStacks: number[];
  readonly smallBlind: number;
  readonly bigBlind: number;
  readonly playerCount: number;
  deck: string[];
  burned: string[] = [];
  board: string[] = [];
  street: Street = 'preflop';
  currentBet = 0;
  lastFullRaise: number;
  toAct: number | null;
  pending = new Set<number>();
  seats: Seat[];
  actions: ActionRecord[] = [];
  result: HandResult | null = null;

  constructor({
    seed,
    button = 0,
    startingStacks = Array(6).fill(10_000),
    smallBlind = 50,
    bigBlind = 100,
  }: {
    seed: number;
    button?: number;
    startingStacks?: number[];
    smallBlind?: number;
    bigBlind?: number;
  }) {
    if (!Number.isSafeInteger(seed)) throw new Error('seed must be a safe integer');
    if (startingStacks.length < 2 || startingStacks.length > 6 || startingStacks.some((stack) => !Number.isInteger(stack) || stack <= 0)) {
      throw new Error('startingStacks must contain two to six positive integers');
    }
    if (!Number.isInteger(button) || button < 0 || button >= startingStacks.length) {
      throw new Error('button must identify an occupied seat');
    }
    this.seed = seed;
    this.button = button;
    this.startingStacks = [...startingStacks];
    this.smallBlind = smallBlind;
    this.bigBlind = bigBlind;
    this.playerCount = startingStacks.length;
    this.lastFullRaise = bigBlind;
    this.deck = shuffledDeck(seed);
    const smallBlindSeat = this.playerCount === 2 ? button : this.clockwise(button);
    const bigBlindSeat = this.clockwise(smallBlindSeat);
    this.toAct = this.playerCount === 2 ? button : this.clockwise(bigBlindSeat);
    this.pending = new Set(startingStacks.map((_, seat) => seat));

    const holes = startingStacks.map(() => [] as string[]);
    const firstDealt = this.clockwise(button);
    const dealOrder = startingStacks.map((_, offset) => (firstDealt + offset) % this.playerCount);
    for (let round = 0; round < 2; round += 1) {
      dealOrder.forEach((seat) => holes[seat].push(this.draw()));
    }
    this.seats = startingStacks.map((stack, seat) => ({
      seat,
      stack,
      holeCards: holes[seat],
      streetCommitted: 0,
      handCommitted: 0,
      status: 'active' as const,
    }));
    this.postBlind(smallBlindSeat, smallBlind, 'small-blind');
    this.postBlind(bigBlindSeat, bigBlind, 'big-blind');
    this.currentBet = Math.max(...this.seats.map((seat) => seat.streetCommitted));
    this.autoFinishIfNoDecision();
    this.assertInvariants();
  }

  static restore(snapshot: SerializedHand) {
    const hand = Object.create(BrowserPokerHand.prototype) as BrowserPokerHand;
    Object.assign(hand, clone(snapshot), {
      playerCount: snapshot.startingStacks.length,
      pending: new Set(snapshot.pending),
    });
    hand.assertInvariants();
    return hand;
  }

  get pot() {
    return this.seats.reduce((total, seat) => total + seat.handCommitted, 0);
  }

  get terminal() {
    return this.street === 'terminal';
  }

  private draw() {
    const card = this.deck.pop();
    if (!card) throw new Error('deck is empty');
    return card;
  }

  private clockwise(seat: number) {
    return (seat + 1) % this.playerCount;
  }

  private nextPending(after: number) {
    for (let offset = 1; offset <= this.playerCount; offset += 1) {
      const candidate = (after + offset) % this.playerCount;
      if (this.pending.has(candidate) && this.seats[candidate].status === 'active') return candidate;
    }
    return null;
  }

  private commit(seat: Seat, amount: number) {
    if (!Number.isInteger(amount) || amount < 0 || amount > seat.stack) throw new Error('invalid chip commitment');
    seat.stack -= amount;
    seat.streetCommitted += amount;
    seat.handCommitted += amount;
    if (seat.stack === 0) seat.status = 'all-in';
  }

  private postBlind(seatNumber: number, blind: number, type: string) {
    const seat = this.seats[seatNumber];
    const amount = Math.min(blind, seat.stack);
    this.commit(seat, amount);
    this.actions.push({ street: 'preflop', seat: seatNumber, type, amount });
  }

  amountToCall(seatNumber = this.toAct) {
    if (seatNumber === null) return 0;
    return Math.max(0, this.currentBet - this.seats[seatNumber].streetCommitted);
  }

  legalActions(): LegalAction[] {
    if (this.terminal || this.toAct === null) return [];
    const seat = this.seats[this.toAct];
    if (seat.status !== 'active') return [];
    const toCall = this.amountToCall();
    const maximum = seat.streetCommitted + seat.stack;
    const actions: LegalAction[] = toCall > 0
      ? [
          { type: 'fold', amount: null, minAmount: null, maxAmount: null },
          { type: 'call', amount: Math.min(toCall, seat.stack), minAmount: null, maxAmount: null },
        ]
      : [{ type: 'check', amount: null, minAmount: null, maxAmount: null }];
    const opponentsCanAct = this.seats.some((opponent) => opponent.seat !== seat.seat && opponent.status === 'active');
    if (seat.stack > toCall && opponentsCanAct) {
      const minimum = this.currentBet === 0 ? this.bigBlind : this.currentBet + this.lastFullRaise;
      if (maximum >= minimum) actions.push({ type: 'raise-to', amount: null, minAmount: minimum, maxAmount: maximum });
      actions.push({ type: 'all-in', amount: maximum, minAmount: null, maxAmount: null });
    }
    return actions;
  }

  apply(action: PokerAction) {
    if (this.terminal || this.toAct === null) throw new Error('the hand is terminal');
    const seatNumber = this.toAct;
    const seat = this.seats[seatNumber];
    const toCall = this.amountToCall(seatNumber);
    const maximum = seat.streetCommitted + seat.stack;
    let recordAmount = 0;

    if (action.type === 'fold') {
      if (toCall <= 0) throw new Error('cannot fold when checking is available');
      seat.status = 'folded';
      this.pending.delete(seatNumber);
      this.actions.push({ street: this.street, seat: seatNumber, type: 'fold', amount: 0 });
      const remaining = this.seats.filter((item) => item.status !== 'folded');
      if (remaining.length === 1) this.awardFold(remaining[0].seat);
      else this.continueAfterAction(seatNumber);
      this.assertInvariants();
      return;
    }
    if (action.type === 'check') {
      if (toCall !== 0) throw new Error(`cannot check facing ${toCall}`);
      this.pending.delete(seatNumber);
    } else if (action.type === 'call') {
      if (toCall <= 0) throw new Error('cannot call when checking is available');
      recordAmount = Math.min(toCall, seat.stack);
      this.commit(seat, recordAmount);
      this.pending.delete(seatNumber);
    } else if (action.type === 'raise-to' || action.type === 'all-in') {
      if (seat.stack <= toCall) throw new Error('no chips available beyond a call');
      if (!this.seats.some((opponent) => opponent.seat !== seatNumber && opponent.status === 'active')) {
        throw new Error('cannot raise when no opponent can act');
      }
      const target = action.type === 'all-in' ? maximum : action.amount;
      if (!Number.isInteger(target)) throw new Error('raise-to requires an integer amount');
      if ((target as number) <= this.currentBet || (target as number) > maximum) throw new Error('invalid raise target');
      const minimum = this.currentBet === 0 ? this.bigBlind : this.currentBet + this.lastFullRaise;
      if (action.type === 'raise-to' && (target as number) < minimum) throw new Error(`minimum raise-to is ${minimum}`);
      const raiseSize = (target as number) - this.currentBet;
      recordAmount = target as number;
      this.commit(seat, (target as number) - seat.streetCommitted);
      if (raiseSize >= this.lastFullRaise) this.lastFullRaise = raiseSize;
      this.currentBet = target as number;
      this.pending = new Set(this.seats.filter((opponent) => opponent.seat !== seatNumber && opponent.status === 'active').map((opponent) => opponent.seat));
    } else {
      throw new Error(`unsupported action ${action.type}`);
    }
    this.actions.push({ street: this.street, seat: seatNumber, type: action.type, amount: recordAmount });
    this.continueAfterAction(seatNumber);
    this.assertInvariants();
  }

  private continueAfterAction(after: number) {
    const next = this.nextPending(after);
    if (next !== null) this.toAct = next;
    else this.closeBettingRound();
  }

  private closeBettingRound() {
    this.toAct = null;
    const active = this.seats.filter((seat) => seat.status === 'active');
    if (active.length <= 1 && this.seats.some((seat) => seat.status === 'all-in')) this.runoutAndShowdown();
    else if (this.street === 'river') this.showdown();
    else this.advanceStreet();
  }

  private advanceStreet() {
    this.seats.forEach((seat) => { seat.streetCommitted = 0; });
    this.currentBet = 0;
    this.lastFullRaise = this.bigBlind;
    if (this.street === 'preflop') {
      this.burnAndDeal(3);
      this.street = 'flop';
    } else if (this.street === 'flop') {
      this.burnAndDeal(1);
      this.street = 'turn';
    } else if (this.street === 'turn') {
      this.burnAndDeal(1);
      this.street = 'river';
    } else throw new Error(`cannot advance from ${this.street}`);
    this.pending = new Set(this.seats.filter((seat) => seat.status === 'active').map((seat) => seat.seat));
    this.toAct = this.nextPending(this.button);
    this.autoFinishIfNoDecision();
  }

  private burnAndDeal(count: number) {
    this.burned.push(this.draw());
    for (let index = 0; index < count; index += 1) this.board.push(this.draw());
  }

  private autoFinishIfNoDecision() {
    const active = this.seats.filter((seat) => seat.status === 'active');
    const hasAllIn = this.seats.some((seat) => seat.status === 'all-in');
    if (!this.terminal && hasAllIn && active.length <= 1) {
      if (active[0] && this.amountToCall(active[0].seat) > 0) {
        this.pending = new Set([active[0].seat]);
        this.toAct = active[0].seat;
      } else this.runoutAndShowdown();
    }
  }

  private runoutAndShowdown() {
    while (this.board.length < 5) this.burnAndDeal(this.board.length === 0 ? 3 : 1);
    this.showdown();
  }

  private showdown() {
    const live = this.seats.map((seat) => seat.status !== 'folded');
    const bestHands = this.seats.map((seat, index) => live[index] ? bestHand([...(seat.holeCards ?? []), ...this.board]) : null);
    const payouts = Array(this.playerCount).fill(0) as number[];
    const levels = [...new Set(this.seats.filter((seat) => seat.handCommitted > 0).map((seat) => seat.handCommitted))].sort((a, b) => a - b);
    let previous = 0;
    const allWinners = new Set<number>();
    for (const level of levels) {
      const contributors = this.seats.filter((seat) => seat.handCommitted >= level);
      const potSlice = (level - previous) * contributors.length;
      const eligible = contributors.filter((seat) => seat.status !== 'folded').map((seat) => seat.seat);
      if (eligible.length === 0) {
        const share = Math.floor(potSlice / contributors.length);
        contributors.forEach((seat) => { payouts[seat.seat] += share; });
        payouts[contributors[0].seat] += potSlice - share * contributors.length;
      } else {
        let winners = [eligible[0]];
        eligible.slice(1).forEach((seat) => {
          const comparison = compareHands([...(this.seats[seat].holeCards ?? []), ...this.board], [...(this.seats[winners[0]].holeCards ?? []), ...this.board]);
          if (comparison > 0) winners = [seat];
          else if (comparison === 0) winners.push(seat);
        });
        const share = Math.floor(potSlice / winners.length);
        winners.forEach((winner) => { payouts[winner] += share; allWinners.add(winner); });
        let odd = potSlice - share * winners.length;
        for (let offset = 1; offset <= this.playerCount && odd > 0; offset += 1) {
          const oddSeat = (this.button + offset) % this.playerCount;
          if (winners.includes(oddSeat)) { payouts[oddSeat] += 1; odd -= 1; }
        }
      }
      previous = level;
    }
    this.seats.forEach((seat, index) => {
      seat.stack += payouts[index];
      seat.handCommitted = 0;
      seat.streetCommitted = 0;
    });
    this.result = {
      reason: 'showdown',
      winners: [...allWinners].sort((a, b) => a - b),
      payouts,
      revealedHoleCards: this.seats.map((seat) => [...(seat.holeCards ?? [])]),
      bestHands: bestHands.map((hand) => hand ? { cards: hand.cards, category: hand.category, importance: hand.importance } : null),
    };
    this.markTerminal();
  }

  private awardFold(winner: number) {
    const pot = this.pot;
    const payouts = Array(this.playerCount).fill(0) as number[];
    payouts[winner] = pot;
    this.seats[winner].stack += pot;
    this.seats.forEach((seat) => { seat.handCommitted = 0; seat.streetCommitted = 0; });
    this.result = {
      reason: 'fold', winners: [winner], payouts,
      revealedHoleCards: this.seats.map((seat) => [...(seat.holeCards ?? [])]),
    };
    this.markTerminal();
  }

  private markTerminal() {
    this.street = 'terminal';
    this.toAct = null;
    this.pending.clear();
    this.currentBet = 0;
  }

  private description(seatNumber: number, category: string | null) {
    if (!category) return null;
    const hole = this.seats[seatNumber].holeCards ?? [];
    if (this.board.length === 0) {
      if (hole[0][0] === hole[1][0]) return `Pocket ${rankName[hole[0][0]]}`;
      return `${hole[0][0]}${hole[1][0]} ${hole[0][1] === hole[1][1] ? 'suited' : 'offsuit'}`;
    }
    return category.replaceAll('-', ' ').replace(/^./, (letter) => letter.toUpperCase());
  }

  observation(heroSeat: number): Observation {
    const holeCards = [...(this.seats[heroSeat].holeCards ?? [])];
    const best = bestHand([...holeCards, ...this.board]);
    const preflop = !best && this.board.length === 0 ? preflopHighlight(holeCards) : null;
    const category = best?.category ?? preflop?.category ?? null;
    return {
      schemaVersion: BrowserPokerHand.schemaVersion,
      seed: this.seed,
      button: this.button,
      street: this.street,
      board: [...this.board],
      pot: this.pot,
      smallBlind: this.smallBlind,
      bigBlind: this.bigBlind,
      currentBet: this.currentBet,
      amountToCall: this.amountToCall(heroSeat),
      toAct: this.toAct,
      heroSeat,
      holeCards,
      bestFive: best?.cards ?? [],
      bestFiveImportance: best?.importance ?? preflop?.importance ?? {},
      handCategory: category,
      handDescription: this.description(heroSeat, category),
      seats: this.seats.map(({ holeCards: _, ...seat }) => ({ ...seat })),
      actions: clone(this.actions),
      legalActions: this.toAct === heroSeat ? this.legalActions() : [],
      result: clone(this.result),
    };
  }

  serialize(): SerializedHand {
    return {
      schemaVersion: BrowserPokerHand.schemaVersion,
      seed: this.seed,
      button: this.button,
      startingStacks: [...this.startingStacks],
      smallBlind: this.smallBlind,
      bigBlind: this.bigBlind,
      deck: [...this.deck],
      burned: [...this.burned],
      board: [...this.board],
      street: this.street,
      currentBet: this.currentBet,
      lastFullRaise: this.lastFullRaise,
      toAct: this.toAct,
      pending: [...this.pending].sort((a, b) => a - b),
      seats: clone(this.seats),
      actions: clone(this.actions),
      result: clone(this.result),
    };
  }

  assertInvariants() {
    const cards = [...this.deck, ...this.burned, ...this.board, ...this.seats.flatMap((seat) => seat.holeCards ?? [])];
    if (cards.length !== 52 || new Set(cards).size !== 52) throw new Error('cards must be unique and account for the full deck');
    const total = this.seats.reduce((sum, seat) => sum + seat.stack + seat.handCommitted, 0);
    if (total !== this.startingStacks.reduce((sum, stack) => sum + stack, 0)) throw new Error('chip conservation failed');
    if (this.seats.some((seat) => seat.stack < 0 || seat.streetCommitted < 0 || seat.handCommitted < 0 || seat.streetCommitted > seat.handCommitted)) {
      throw new Error('invalid chip state');
    }
    if (this.terminal && (this.toAct !== null || this.pending.size > 0 || this.pot !== 0 || !this.result)) throw new Error('invalid terminal state');
    if (!this.terminal && this.toAct !== null && !this.pending.has(this.toAct)) throw new Error('acting seat must be pending');
  }
}

export function randomSeed() {
  const values = new Uint32Array(2);
  crypto.getRandomValues(values);
  return values[0] * 0x200000 + (values[1] >>> 11);
}
