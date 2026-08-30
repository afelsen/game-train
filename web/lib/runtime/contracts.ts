export type ActionType = 'fold' | 'check' | 'call' | 'raise-to' | 'all-in';

export type LegalAction = {
  type: ActionType;
  amount: number | null;
  minAmount: number | null;
  maxAmount: number | null;
};

export type Seat = {
  seat: number;
  stack: number;
  streetCommitted: number;
  handCommitted: number;
  status: 'active' | 'folded' | 'all-in';
  holeCards?: string[];
};

export type ActionRecord = {
  street: string;
  seat: number;
  type: string;
  amount: number;
};

export type BestHand = {
  cards: string[];
  category: string;
  importance: Record<string, number>;
};

export type HandResult = {
  reason: string;
  winners: number[];
  payouts: number[];
  revealedHoleCards?: string[][];
  bestHands?: Array<BestHand | null>;
};

export type Observation = {
  schemaVersion?: string;
  seed: number;
  button: number;
  street: string;
  board: string[];
  pot: number;
  smallBlind: number;
  bigBlind: number;
  currentBet: number;
  amountToCall: number;
  toAct: number | null;
  heroSeat: number;
  holeCards: string[];
  bestFive: string[];
  bestFiveImportance: Record<string, number>;
  handCategory: string | null;
  handDescription: string | null;
  seats: Seat[];
  actions: ActionRecord[];
  legalActions: LegalAction[];
  result: HandResult | null;
};

export type HandPayload = {
  sessionId: string;
  botProvider: string;
  observation: Observation;
};

export type SerializedHand = {
  schemaVersion: string;
  seed: number;
  button: number;
  startingStacks: number[];
  smallBlind: number;
  bigBlind: number;
  deck: string[];
  burned: string[];
  board: string[];
  street: string;
  currentBet: number;
  lastFullRaise: number;
  toAct: number | null;
  pending: number[];
  seats: Seat[];
  actions: ActionRecord[];
  result: HandResult | null;
};

export type StrategyAction = {
  abstractAction: string;
  probability: number;
  available?: boolean;
  legalAction: { type: string; amount: number | null } | null;
};

export type Strategy = {
  provider: { modelId: string };
  status: string;
  actions: StrategyAction[];
  modelActions?: StrategyAction[];
  diagnostics: {
    exactState: boolean;
    inferenceMs: number;
    warnings: string[];
    message: string | null;
  };
};

export type Provider = {
  id: string;
  version: string;
  experimental: boolean;
};

export type HistoryItem = {
  sessionId: string;
  seed: number;
  status: string;
  startedAt: string;
  result: HandResult | null;
};

export type HistoryDetail = HistoryItem & {
  events: Array<{
    sequence: number;
    actorSeat: number | null;
    action: ActionRecord | null;
    observation: Observation;
    strategy: Strategy | null;
  }>;
};

export type RuntimeRequest = <T>(path: string, options?: RequestInit) => Promise<T>;
