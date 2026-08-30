import type {
  HandPayload,
  HistoryDetail,
  HistoryItem,
  Provider,
  RuntimeRequest,
  Strategy,
  StrategyAction,
} from './contracts';
import { BrowserPokerHand, randomSeed, type PokerAction } from './poker-engine';

const LOCAL_PROVIDERS: Provider[] = [
  { id: 'check-call-hu', version: 'browser-1.0.0', experimental: false },
  { id: 'uniform-random-hu', version: 'browser-1.0.0', experimental: false },
];
const HISTORY_KEY = 'game-train.browser-history.v1';

type Session = {
  hand: BrowserPokerHand;
  botProvider: string;
  history: HistoryDetail;
  pendingStrategy: Strategy | null;
};

function parseBody(options?: RequestInit): Record<string, unknown> {
  if (!options?.body) return {};
  if (typeof options.body !== 'string') throw new Error('Browser runtime expects a JSON request body');
  return JSON.parse(options.body) as Record<string, unknown>;
}
function localStrategy(hand: BrowserPokerHand, providerId: string): Strategy {
  const legal = hand.legalActions();
  let actions: StrategyAction[];
  if (providerId === 'check-call-hu') {
    const action = legal.find((candidate) => candidate.type === 'check' || candidate.type === 'call');
    if (!action) throw new Error('No check/call action is available');
    actions = [{ abstractAction: 'check-call', probability: 1, legalAction: { type: action.type, amount: null } }];
  } else if (providerId === 'uniform-random-hu') {
    actions = legal.map((action) => ({
      abstractAction: action.type,
      probability: 1 / legal.length,
      legalAction: { type: action.type, amount: action.type === 'raise-to' ? action.minAmount : null },
    }));
  } else throw new Error(`Provider ${providerId} requires the optional model server`);
  return {
    provider: { modelId: providerId },
    status: 'ok',
    actions,
    modelActions: actions,
    diagnostics: { exactState: true, inferenceMs: 0, warnings: [], message: null },
  };
}

function chooseAction(strategy: Strategy, seed: number): PokerAction {
  const value = ((Math.imul(seed ^ (seed >>> 16), 0x45d9f3b) >>> 0) / 4294967296);
  let cumulative = 0;
  for (const candidate of strategy.actions) {
    cumulative += candidate.probability;
    if (value < cumulative && candidate.legalAction) return candidate.legalAction as PokerAction;
  }
  const fallback = [...strategy.actions].reverse().find((candidate) => candidate.legalAction)?.legalAction;
  if (!fallback) throw new Error('The selected model returned no legal action');
  return fallback as PokerAction;
}

export class BrowserPlayRuntime {
  private readonly sessions = new Map<string, Session>();

  constructor(private readonly remoteRequest: RuntimeRequest) {}

  private payload(sessionId: string): HandPayload {
    const session = this.getSession(sessionId);
    return { sessionId, botProvider: session.botProvider, observation: session.hand.observation(0) };
  }

  private getSession(sessionId: string) {
    const session = this.sessions.get(sessionId);
    if (!session) throw new Error(`Unknown browser hand: ${sessionId}`);
    return session;
  }

  private persistHistory() {
    if (typeof localStorage === 'undefined') return;
    const details = [...this.sessions.values()].map((session) => session.history);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(details.slice(-50)));
  }

  private storedHistory(): HistoryDetail[] {
    if (typeof localStorage === 'undefined') return [];
    try {
      return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]') as HistoryDetail[];
    } catch {
      return [];
    }
  }

  private record(session: Session, actorSeat: number | null, strategy: Strategy | null) {
    const action = actorSeat === null ? null : session.hand.actions.at(-1) ?? null;
    session.history.events.push({
      sequence: session.history.events.length,
      actorSeat,
      action,
      observation: session.hand.observation(0),
      strategy,
    });
    session.history.status = session.hand.terminal ? 'complete' : 'active';
    session.history.result = session.hand.result;
    this.persistHistory();
  }

  private async strategy(session: Session, providerId: string) {
    if (LOCAL_PROVIDERS.some((provider) => provider.id === providerId)) {
      return localStrategy(session.hand, providerId);
    }
    return this.remoteRequest<Strategy>('/v1/strategy', {
      method: 'POST',
      body: JSON.stringify({ providerId, hand: session.hand.serialize() }),
    });
  }

  async request<T>(path: string, options?: RequestInit): Promise<T> {
    const method = (options?.method ?? 'GET').toUpperCase();
    const url = new URL(path, 'https://browser.runtime');
    const parts = url.pathname.split('/').filter(Boolean);
    const body = parseBody(options);

    if (method === 'GET' && url.pathname === '/v1/providers') {
      let remote: Provider[] = [];
      try {
        remote = (await this.remoteRequest<{ providers: Provider[] }>('/v1/providers')).providers;
      } catch {
        // The browser game remains playable with local providers when no API is configured.
      }
      return { providers: [...new Map([...LOCAL_PROVIDERS, ...remote].map((provider) => [provider.id, provider])).values()] } as T;
    }

    if (method === 'POST' && url.pathname === '/v1/hands') {
      const startingStacks = Array.isArray(body.startingStacks) ? body.startingStacks as number[] : Array(6).fill(10_000);
      const seed = typeof body.seed === 'number' ? body.seed : randomSeed();
      const button = typeof body.button === 'number' ? body.button : 0;
      const botProvider = typeof body.botProvider === 'string' ? body.botProvider : 'check-call-hu';
      const hand = new BrowserPokerHand({ seed, button, startingStacks });
      const sessionId = `browser-${crypto.randomUUID()}`;
      const history: HistoryDetail = {
        sessionId,
        seed,
        status: 'active',
        startedAt: new Date().toISOString(),
        result: null,
        events: [],
      };
      const session: Session = { hand, botProvider, history, pendingStrategy: null };
      this.sessions.set(sessionId, session);
      this.record(session, null, null);
      return this.payload(sessionId) as T;
    }

    if (parts[0] === 'v1' && parts[1] === 'hands' && parts[2]) {
      const sessionId = parts[2];
      const session = this.getSession(sessionId);
      if (method === 'POST' && parts[3] === 'actions') {
        if (session.hand.toAct !== 0) throw new Error("It is not the hero's turn");
        const action = { type: body.type, amount: body.amount } as PokerAction;
        session.hand.apply(action);
        this.record(session, 0, session.pendingStrategy);
        session.pendingStrategy = null;
        return this.payload(sessionId) as T;
      }
      if (method === 'POST' && parts[3] === 'bot-action') {
        if (session.hand.terminal || session.hand.toAct === 0 || session.hand.toAct === null) throw new Error('No bot action is pending');
        const actor = session.hand.toAct;
        const strategy = await this.strategy(session, session.botProvider);
        session.hand.apply(chooseAction(strategy, session.hand.seed ^ (session.hand.actions.length << 16)));
        this.record(session, actor, null);
        return this.payload(sessionId) as T;
      }
      if (method === 'POST' && parts[3] === 'strategy') {
        if (session.hand.toAct !== 0) throw new Error('Strategy is available only on your turn');
        const providerId = String(body.providerId ?? session.botProvider);
        const strategy = await this.strategy(session, providerId);
        session.pendingStrategy = strategy;
        return strategy as T;
      }
      if (method === 'POST' && parts[3] === 'bot-provider') {
        session.botProvider = String(body.providerId);
        return { sessionId, botProvider: session.botProvider } as T;
      }
      if (method === 'GET' && parts.length === 3) return this.payload(sessionId) as T;
    }

    if (method === 'GET' && url.pathname === '/v1/history') {
      const details = this.storedHistory();
      const limit = Number(url.searchParams.get('limit') ?? 20);
      const hands: HistoryItem[] = details.slice(-limit).reverse().map(({ events: _, ...item }) => item);
      return { hands } as T;
    }
    if (method === 'GET' && parts[0] === 'v1' && parts[1] === 'history' && parts[2]) {
      const detail = this.storedHistory().find((item) => item.sessionId === parts[2]);
      if (!detail) throw new Error('Hand history was not found');
      return detail as T;
    }
    return this.remoteRequest<T>(path, options);
  }
}
