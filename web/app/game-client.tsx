'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Ban,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Database,
  History,
  LoaderCircle,
  Minus,
  Play,
  Plus,
  RotateCcw,
  Settings2,
  TriangleAlert,
} from 'lucide-react';
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const SUITS: Record<string, string> = { c: '♣', d: '♦', h: '♥', s: '♠' };
const MODEL_NAMES: Record<string, string> = {
  'check-call-hu': 'Check / call baseline',
  'uniform-random-hu': 'Uniform random baseline',
  'fullhouse-deep-cfr-experimental-hu': 'Fullhouse checkpoint',
};
const HAND_RANKS = [
  ['straight-flush', 'Straight flush'],
  ['four-of-a-kind', 'Four of a kind'],
  ['full-house', 'Full house'],
  ['flush', 'Flush'],
  ['straight', 'Straight'],
  ['three-of-a-kind', 'Three of a kind'],
  ['two-pair', 'Two pair'],
  ['one-pair', 'One pair'],
  ['high-card', 'High card'],
] as const;
type LegalAction = {
  type: 'fold' | 'check' | 'call' | 'raise-to' | 'all-in';
  amount: number | null;
  minAmount: number | null;
  maxAmount: number | null;
};
type Seat = {
  seat: number;
  stack: number;
  streetCommitted: number;
  handCommitted: number;
  status: string;
};
type ActionRecord = {
  street: string;
  seat: number;
  type: string;
  amount: number;
};
type BestHand = {
  cards: string[];
  category: string;
  importance: Record<string, number>;
};
type Observation = {
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
  result: null | {
    reason: string;
    winners: number[];
    payouts: number[];
    revealedHoleCards?: string[][];
    bestHands?: Array<BestHand | null>;
  };
};
type HandPayload = {
  sessionId: string;
  botProvider: string;
  observation: Observation;
};
type StrategyAction = {
  abstractAction: string;
  probability: number;
  available?: boolean;
  legalAction: { type: string; amount: number | null } | null;
};
type Strategy = {
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
type Provider = { id: string; version: string; experimental: boolean };
type HistoryItem = {
  sessionId: string;
  seed: number;
  status: string;
  startedAt: string;
  result: null | { reason: string; winners: number[]; payouts: number[] };
};
type HistoryDetail = HistoryItem & {
  events: Array<{
    sequence: number;
    actorSeat: number | null;
    action: null | ActionRecord;
    observation: Observation;
    strategy: Strategy | null;
  }>;
};
type EquityResult = {
  method: 'exact' | 'sampled';
  samples: number;
  wins: number;
  ties: number;
  losses: number;
  equity: number;
  standardError: number;
  opponentRange: string;
};
type HandChances = {
  method: 'exact' | 'sampled';
  samples: number;
  atLeast: Record<string, number>;
};
type SolverEvent = {
  event: 'started' | 'progress' | 'complete' | 'failed';
  iteration?: number;
  iterations?: number;
  exploitability?: number;
  actions?: Array<{ action: string; probability: number }>;
};
type SolverJob = {
  jobId: string;
  status: 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';
  mode: 'visual' | 'headless';
  cacheHit: boolean;
  events: SolverEvent[];
  error: string | null;
};
type ApiRequest = <T>(path: string, options?: RequestInit) => Promise<T>;
type SolverRequest = typeof SOLVER_DEMO;
type TrainingSpot = {
  id: string;
  title: string;
  teachingFocus: string;
  source: 'curated' | 'seeded-random';
  seed: number | null;
  request: SolverRequest;
};

const chips = (value: number) =>
  `${(value / 100).toFixed(value % 100 ? 1 : 0)} BB`;
const modelName = (id: string) => MODEL_NAMES[id] ?? id;
function actionLabel(action: LegalAction) {
  if (action.type === 'call') return `Call ${chips(action.amount ?? 0)}`;
  if (action.type === 'all-in') return 'All-in';
  return action.type[0].toUpperCase() + action.type.slice(1);
}
function strategyLabel(action: StrategyAction) {
  if (
    action.legalAction?.type === 'raise-to' &&
    action.legalAction.amount !== null
  )
    return `Raise to ${chips(action.legalAction.amount)}`;
  return action.abstractAction.replaceAll('-', ' ');
}
function raiseStops(
  minimum: number,
  maximum: number,
  bigBlind: number,
  targets: number[],
) {
  const values = new Set<number>([minimum, maximum, ...targets]);
  for (const multiple of [2, 2.5, 3, 4, 5, 7.5, 10, 15, 20, 30, 50, 75, 100]) {
    const value = Math.round(multiple * bigBlind);
    if (value > minimum && value < maximum) values.add(value);
  }
  return [...values].sort((a, b) => a - b);
}
function PlayingCard({
  card,
  hidden = false,
  importance = 0,
  highlight = 'hero',
}: {
  card?: string;
  hidden?: boolean;
  importance?: number;
  highlight?: 'hero' | 'villain';
}) {
  const value = card ? `${card[0]}${SUITS[card[1]] ?? card[1]}` : '';
  const red = value.includes('♦') || value.includes('♥');
  return (
    <div
      className={`playing-card ${hidden ? 'card-back' : ''} ${importance === 3 ? (highlight === 'villain' ? 'villain-best-card' : 'best-card') : ''} ${red ? 'text-[#d9594c]' : 'text-[#15251f]'}`}
      aria-label={hidden ? 'Hidden card' : value}
    >
      {hidden ? (
        <span className="card-back-mark">GT</span>
      ) : (
        <span>{value}</span>
      )}
    </div>
  );
}

const SOLVER_DEMO = {
  schemaVersion: '1.0.0',
  oopRange: '66+,A8s+,A5s-A4s,AJo+,K9s+,KQo,QTs+,JTs,96s+,85s+,75s+,65s+,54s',
  ipRange:
    'QQ-22,AQs-A2s,ATo+,K5s+,KJo+,Q8s+,J8s+,T7s+,96s+,86s+,75s+,64s+,53s+',
  flop: 'Td9d6h',
  turn: 'Qc',
  startingPot: 200,
  effectiveStack: 900,
  betSizes: '60%, e, a',
  raiseSizes: '2.5x',
  maxIterations: 100,
  targetExploitability: 1,
  reportEvery: 10,
};

function SolverLab({ request }: { request: ApiRequest }) {
  const [executionMode, setExecutionMode] = useState<'visual' | 'headless'>(
      'visual',
    ),
    [reuseCache, setReuseCache] = useState(false),
    [job, setJob] = useState<SolverJob | null>(null),
    [error, setError] = useState<string | null>(null),
    [spots, setSpots] = useState<TrainingSpot[]>([]),
    [activeSpot, setActiveSpot] = useState<TrainingSpot>({
      id: 'demo',
      title: 'Dynamic diamond turn',
      teachingFocus: 'Range interaction on a connected, two-tone board',
      source: 'curated',
      seed: null,
      request: SOLVER_DEMO,
    });
  const runToken = useRef(0);
  useEffect(() => {
    let active = true;
    void request<{ spots: TrainingSpot[] }>('/v1/training/spots?source=curated')
      .then((result) => {
        if (!active || !result.spots.length) return;
        setSpots(result.spots);
        setActiveSpot(result.spots[0]);
      })
      .catch(() => {
        // The fixed demo remains usable while an older API process restarts.
      });
    return () => {
      active = false;
    };
  }, [request]);
  const progress = useMemo(
    () =>
      job?.events
        .filter(
          (event) =>
            (event.event === 'progress' || event.event === 'complete') &&
            event.exploitability !== undefined,
        )
        .map((event) => ({
          iteration: event.iteration ?? event.iterations ?? 0,
          exploitability: event.exploitability ?? 0,
        })) ?? [],
    [job],
  );
  const latest = job?.events.at(-1),
    latestActions = [...(latest?.actions ?? [])].sort(
      (a, b) => b.probability - a.probability,
    ),
    running = job?.status === 'queued' || job?.status === 'running';
  async function runSolve() {
    const token = ++runToken.current;
    setError(null);
    setJob(null);
    try {
      let current = await request<SolverJob>('/v1/solver/jobs', {
        method: 'POST',
        body: JSON.stringify({
          ...SOLVER_DEMO,
          ...activeSpot.request,
          mode: executionMode,
          bypassCache: !reuseCache,
        }),
      });
      setJob(current);
      while (
        token === runToken.current &&
        (current.status === 'queued' || current.status === 'running')
      ) {
        await new Promise((resolve) => setTimeout(resolve, 250));
        current = await request<SolverJob>(`/v1/solver/jobs/${current.jobId}`);
        setJob(current);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Solver job failed');
    }
  }
  async function cancelSolve() {
    if (!job) return;
    ++runToken.current;
    setJob(
      await request<SolverJob>(`/v1/solver/jobs/${job.jobId}/cancel`, {
        method: 'POST',
      }),
    );
  }
  async function generateSpot() {
    setError(null);
    const seed = Math.floor(Math.random() * Number.MAX_SAFE_INTEGER);
    try {
      const result = await request<{ spots: TrainingSpot[] }>(
        `/v1/training/spots?source=random&seed=${seed}`,
      );
      if (result.spots[0]) {
        setSpots((current) => [...current, result.spots[0]]);
        setActiveSpot(result.spots[0]);
        setJob(null);
      }
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Spot generation failed',
      );
    }
  }
  const boardCards =
    `${activeSpot.request.flop}${activeSpot.request.turn}`.match(/../g) ?? [];
  const boardLabel = boardCards
    .map((card) => `${card[0]}${SUITS[card[1]] ?? card[1]}`)
    .join(' ');
  return (
    <section className="solver-workspace">
      <div className="solver-lab-heading">
        <div>
          <span className="eyebrow">Phase 4 · solver lab</span>
          <h1>Watch a strategy converge</h1>
          <p>{activeSpot.teachingFocus}.</p>
        </div>
        <div className="solver-run-controls">
          <Select
            value={activeSpot.id}
            onValueChange={(id) => {
              const selected = spots.find((spot) => spot.id === id);
              if (selected) {
                setActiveSpot(selected);
                setJob(null);
              }
            }}
            disabled={running}
          >
            <SelectTrigger aria-label="Training spot">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {spots.map((spot) => (
                <SelectItem key={spot.id} value={spot.id}>
                  {spot.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={() => void generateSpot()}
            disabled={running}
          >
            Random spot
          </Button>
          <div className="solver-mode-toggle">
            <button
              className={executionMode === 'visual' ? 'active' : ''}
              onClick={() => setExecutionMode('visual')}
              disabled={running}
            >
              Visual
            </button>
            <button
              className={executionMode === 'headless' ? 'active' : ''}
              onClick={() => setExecutionMode('headless')}
              disabled={running}
            >
              Headless
            </button>
          </div>
          <div className="cache-control">
            <Switch
              aria-label="Reuse cached solver result"
              checked={reuseCache}
              onCheckedChange={setReuseCache}
              disabled={running}
            />
            <span>Reuse cache</span>
          </div>
          <Button onClick={() => void runSolve()} disabled={running}>
            <Play />
            Run solve
          </Button>
          {running && (
            <Button variant="outline" onClick={() => void cancelSolve()}>
              <Ban />
              Cancel
            </Button>
          )}
        </div>
      </div>
      {error && (
        <div className="error-banner">
          <TriangleAlert />
          <div>
            <strong>Solver unavailable</strong>
            <span>{error}</span>
          </div>
        </div>
      )}
      <div className="solver-grid">
        <article className="solver-chart-card">
          <div className="solver-card-heading">
            <div>
              <span className="eyebrow">Convergence</span>
              <h2>Exploitability by iteration</h2>
            </div>
            <strong>
              {latest?.exploitability !== undefined
                ? latest.exploitability.toFixed(3)
                : '—'}
            </strong>
          </div>
          {executionMode === 'visual' ? (
            progress.length ? (
              <ChartContainer
                className="solver-chart"
                config={{
                  exploitability: { label: 'Exploitability', color: '#1b6b4f' },
                }}
              >
                <LineChart
                  data={progress}
                  margin={{ left: 4, right: 12, top: 12, bottom: 0 }}
                >
                  <CartesianGrid vertical={false} />
                  <XAxis
                    dataKey="iteration"
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis tickLine={false} axisLine={false} width={42} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Line
                    type="monotone"
                    dataKey="exploitability"
                    stroke="var(--color-exploitability)"
                    strokeWidth={3}
                    dot={{ r: 3 }}
                  />
                </LineChart>
              </ChartContainer>
            ) : (
              <div className="solver-empty">
                Run a fresh visual solve to stream convergence points.
              </div>
            )
          ) : (
            <div className="solver-empty">
              Headless mode suppresses intermediate reporting and returns only
              the final strategy.
            </div>
          )}
        </article>
        <article className="solver-actions-card">
          <div className="solver-card-heading">
            <div>
              <span className="eyebrow">Root strategy</span>
              <h2>Action mix</h2>
            </div>
            <span
              className={`solver-status solver-status-${job?.status ?? 'idle'}`}
            >
              {job?.status ?? 'idle'}
            </span>
          </div>
          <div className="solver-action-list">
            {latestActions.length ? (
              latestActions.map((action) => (
                <div key={action.action}>
                  <div>
                    <span>{action.action.replace(/\((\d+)\)/, ' $1')}</span>
                    <b>{(action.probability * 100).toFixed(1)}%</b>
                  </div>
                  <div>
                    <span style={{ width: `${action.probability * 100}%` }} />
                  </div>
                </div>
              ))
            ) : (
              <p>Action probabilities appear as the worker reports them.</p>
            )}
          </div>
          {job && (
            <div className="solver-job-meta">
              <span>
                {job.cacheHit ? (
                  <>
                    <Database />
                    Cache hit
                  </>
                ) : executionMode === 'visual' ? (
                  `${progress.length} snapshots`
                ) : (
                  'No progress snapshots'
                )}
              </span>
              <span>{job.jobId}</span>
            </div>
          )}
        </article>
        <aside className="solver-config-card">
          <span className="eyebrow">Solve configuration</span>
          <h2>{activeSpot.title}</h2>
          <dl>
            <div>
              <dt>Board</dt>
              <dd>{boardLabel}</dd>
            </div>
            <div>
              <dt>Pot</dt>
              <dd>{chips(activeSpot.request.startingPot)}</dd>
            </div>
            <div>
              <dt>Effective stack</dt>
              <dd>{chips(activeSpot.request.effectiveStack)}</dd>
            </div>
            <div>
              <dt>Tree</dt>
              <dd>60%, geometric, all-in</dd>
            </div>
            <div>
              <dt>Target</dt>
              <dd>≤ 1.0 exploitability</dd>
            </div>
            <div>
              <dt>Limit</dt>
              <dd>100 iterations</dd>
            </div>
          </dl>
          <p>
            Visual and headless modes use the same solve identity and final
            strategy.
          </p>
        </aside>
      </div>
    </section>
  );
}

export default function GameClient() {
  const [hand, setHand] = useState<HandPayload | null>(null),
    [strategy, setStrategy] = useState<Strategy | null>(null),
    [providers, setProviders] = useState<Provider[]>([]);
  const [opponentProvider, setOpponentProvider] = useState('check-call-hu'),
    [trainerProvider, setTrainerProvider] = useState(
      'fullhouse-deep-cfr-experimental-hu',
    );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [mode, setMode] = useState<'play' | 'review' | 'train'>('play');
  const [history, setHistory] = useState<HistoryItem[]>([]),
    [review, setReview] = useState<HistoryDetail | null>(null),
    [reviewStep, setReviewStep] = useState(0);
  const [raiseAmount, setRaiseAmount] = useState<number | null>(null),
    [showAllStrategy, setShowAllStrategy] = useState(false);
  const [highlightBestFive, setHighlightBestFive] = useState(true);
  const [showStrategy, setShowStrategy] = useState(true);
  const [equityState, setEquityState] = useState<{
    key: string;
    result: EquityResult;
  } | null>(null);
  const [handChanceState, setHandChanceState] = useState<{
    key: string;
    result: HandChances;
  } | null>(null);
  const initialized = useRef(false);
  const request = useCallback(
    async <T,>(path: string, options?: RequestInit): Promise<T> => {
      const headers = new Headers(options?.headers);
      headers.set('Content-Type', 'application/json');
      const response = await fetch(`${API}${path}`, { ...options, headers });
      const data: unknown = await response.json();
      if (!response.ok) {
        const message =
          typeof data === 'object' && data !== null && 'error' in data
            ? String(data.error)
            : `Request failed (${response.status})`;
        throw new Error(message);
      }
      return data as T;
    },
    [],
  );
  const newHand = useCallback(
    async (
      provider = opponentProvider,
      options?: { stacks?: [number, number]; button?: number },
    ) => {
      setBusy(true);
      setError(null);
      setStrategy(null);
      setShowAllStrategy(false);
      try {
        setHand(
          await request<HandPayload>('/v1/hands', {
            method: 'POST',
            body: JSON.stringify({
              botProvider: provider,
              ...(options?.stacks ? { startingStacks: options.stacks } : {}),
              ...(options?.button !== undefined
                ? { button: options.button }
                : {}),
            }),
          }),
        );
        setRaiseAmount(null);
      } catch (reason) {
        setError(
          reason instanceof Error ? reason.message : 'Could not start a hand',
        );
      } finally {
        setBusy(false);
      }
    },
    [opponentProvider, request],
  );
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const timeout = setTimeout(() => {
      void Promise.all([
        newHand(),
        request<{ providers: Provider[] }>('/v1/providers').then((result) =>
          setProviders(result.providers),
        ),
      ]);
    });
    return () => clearTimeout(timeout);
  }, [newHand, request]);
  useEffect(() => {
    if (
      !showStrategy ||
      mode !== 'play' ||
      !hand ||
      hand.observation.street === 'terminal' ||
      hand.observation.toAct !== 0
    )
      return;
    let cancelled = false;
    request<Strategy>(`/v1/hands/${hand.sessionId}/strategy`, {
      method: 'POST',
      body: JSON.stringify({ providerId: trainerProvider }),
    })
      .then((result) => {
        if (!cancelled) {
          setStrategy(result);
          setShowAllStrategy(false);
        }
      })
      .catch((reason) => {
        if (!cancelled)
          setError(
            reason instanceof Error ? reason.message : 'Strategy unavailable',
          );
      });
    return () => {
      cancelled = true;
    };
  }, [showStrategy, hand, mode, request, trainerProvider]);
  async function act(action: LegalAction, amount?: number) {
    if (!hand) return;
    setBusy(true);
    setError(null);
    setStrategy(null);
    setShowAllStrategy(false);
    try {
      const body = {
        type: action.type,
        ...(action.type === 'raise-to'
          ? { amount: amount ?? action.minAmount }
          : {}),
      };
      setHand(
        await request<HandPayload>(`/v1/hands/${hand.sessionId}/actions`, {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      );
      setRaiseAmount(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Action failed');
    } finally {
      setBusy(false);
    }
  }
  async function selectOpponent(provider: string) {
    const previous = opponentProvider;
    setOpponentProvider(provider);
    if (!hand) return;
    try {
      await request<{ sessionId: string; botProvider: string }>(
        `/v1/hands/${hand.sessionId}/bot-provider`,
        {
          method: 'POST',
          body: JSON.stringify({ providerId: provider }),
        },
      );
    } catch (reason) {
      setOpponentProvider(previous);
      setError(
        reason instanceof Error
          ? reason.message
          : 'Could not change the Villain model',
      );
    }
  }
  async function dealNextHand() {
    if (!observation) return;
    const stacks = observation.seats.map((seat) => seat.stack) as [
      number,
      number,
    ];
    if (stacks.some((stack) => stack <= 0)) {
      setError('A player is out of chips; reset to begin a new 100 BB match');
      return;
    }
    await newHand(opponentProvider, { stacks, button: 1 - observation.button });
  }
  async function resetMatch() {
    setMode('play');
    await newHand(opponentProvider, { button: 0 });
  }
  async function openReview() {
    setMode('review');
    setBusy(true);
    setError(null);
    try {
      const result = await request<{ hands: HistoryItem[] }>(
        '/v1/history?limit=30',
      );
      setHistory(result.hands);
      if (result.hands[0]) await selectHistory(result.hands[0].sessionId);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'History unavailable',
      );
    } finally {
      setBusy(false);
    }
  }
  async function selectHistory(sessionId: string) {
    const detail = await request<HistoryDetail>(`/v1/history/${sessionId}`);
    setReview(detail);
    setReviewStep(Math.max(0, detail.events.length - 1));
    setStrategy(null);
  }
  const reviewEvent = review?.events[reviewStep],
    observation =
      mode === 'review' ? reviewEvent?.observation : hand?.observation;
  const equityRequest = useMemo(
    () =>
      observation?.holeCards.length
        ? {
            key: `${observation.holeCards.join(',')}|${observation.board.join(',')}`,
            holeCards: observation.holeCards,
            board: observation.board,
          }
        : null,
    [observation],
  );
  useEffect(() => {
    if (!equityRequest) return;
    let cancelled = false;
    request<EquityResult>('/v1/equity', {
      method: 'POST',
      body: JSON.stringify({
        holeCards: equityRequest.holeCards,
        board: equityRequest.board,
      }),
    })
      .then((result) => {
        if (!cancelled) setEquityState({ key: equityRequest.key, result });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [equityRequest, request]);
  useEffect(() => {
    if (!equityRequest) return;
    let cancelled = false;
    request<HandChances>('/v1/hand-chances', {
      method: 'POST',
      body: JSON.stringify({
        holeCards: equityRequest.holeCards,
        board: equityRequest.board,
      }),
    })
      .then((result) => {
        if (!cancelled) setHandChanceState({ key: equityRequest.key, result });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [equityRequest, request]);
  const equity =
    equityState && equityState.key === equityRequest?.key
      ? equityState.result
      : null;
  const handChances =
    handChanceState && handChanceState.key === equityRequest?.key
      ? handChanceState.result
      : null;
  const hero = observation?.seats[0],
    opponent = observation?.seats[1],
    terminal = observation?.street === 'terminal';
  const heroWon = terminal && observation?.result?.winners.includes(0),
    opponentWon = terminal && observation?.result?.winners.includes(1),
    tie = heroWon && opponentWon;
  const opponentCards =
    terminal && observation?.result?.reason === 'showdown'
      ? observation.result.revealedHoleCards?.[1]
      : undefined;
  const villainImportance =
    opponentWon && !tie
      ? (observation?.result?.bestHands?.[1]?.importance ?? {})
      : {};
  const recentActions = useMemo(
    () => observation?.actions.slice(-4).reverse() ?? [],
    [observation],
  );
  const activeStrategy = showStrategy
    ? mode === 'review'
      ? (reviewEvent?.strategy ?? null)
      : strategy
    : null;
  const sortedStrategy = useMemo(
    () =>
      [...(activeStrategy?.modelActions ?? activeStrategy?.actions ?? [])].sort(
        (a, b) => b.probability - a.probability,
      ),
    [activeStrategy],
  );
  const visibleStrategy = showAllStrategy
    ? sortedStrategy
    : sortedStrategy.slice(0, 3);
  const legalRaise =
    mode === 'play'
      ? observation?.legalActions.find((item) => item.type === 'raise-to')
      : undefined;
  const clampedRaise = legalRaise
    ? Math.max(
        legalRaise.minAmount ?? 0,
        Math.min(
          raiseAmount ?? legalRaise.minAmount ?? 0,
          legalRaise.maxAmount ?? 0,
        ),
      )
    : 0;
  const raiseStep = Math.max(1, Math.round((observation?.bigBlind ?? 100) / 2));
  const stepRaise = (direction: -1 | 1) => {
    if (!legalRaise) return;
    const minimum = legalRaise.minAmount ?? 0,
      maximum = legalRaise.maxAmount ?? 0;
    setRaiseAmount(
      Math.max(
        minimum,
        Math.min(clampedRaise + direction * raiseStep, maximum),
      ),
    );
  };
  const potTarget = (fraction: number) =>
    legalRaise
      ? Math.max(
          legalRaise.minAmount ?? 0,
          Math.min(
            Math.round(
              (observation?.currentBet ?? 0) +
                ((observation?.pot ?? 0) + (observation?.amountToCall ?? 0)) *
                  fraction,
            ),
            legalRaise.maxAmount ?? 0,
          ),
        )
      : 0;
  const sizingStops = legalRaise
    ? raiseStops(
        legalRaise.minAmount ?? 0,
        legalRaise.maxAmount ?? 0,
        observation?.bigBlind ?? 100,
        [potTarget(0.5), potTarget(0.75), potTarget(1)],
      )
    : [];
  const activeStop = sizingStops.reduce(
    (best, value, index) =>
      Math.abs(value - clampedRaise) <
      Math.abs(sizingStops[best] - clampedRaise)
        ? index
        : best,
    0,
  );
  const cardImportance = highlightBestFive
    ? (observation?.bestFiveImportance ?? {})
    : {};
  const currentRankIndex = HAND_RANKS.findIndex(
    ([id]) => id === observation?.handCategory,
  );
  const chanceLabel = (probability: number) =>
    probability > 0 && probability < 0.001
      ? '<0.1%'
      : `${(probability * 100).toFixed(probability < 0.1 ? 1 : 0)}%`;
  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <span className="brand-mark">
            <Activity className="size-4" />
          </span>
          <div>
            <p className="brand-name">Game Trainer</p>
            <p className="brand-subtitle">Heads-up no-limit hold’em</p>
          </div>
        </div>
        <nav className="mode-switch" aria-label="Application mode">
          <button
            className={`mode-pill ${mode === 'play' ? 'mode-pill-active' : ''}`}
            onClick={() => setMode('play')}
          >
            Play
          </button>
          <button
            className={`mode-pill ${mode === 'train' ? 'mode-pill-active' : ''}`}
            onClick={() => setMode('train')}
          >
            Train
          </button>
          <button
            className={`mode-pill ${mode === 'review' ? 'mode-pill-active' : ''}`}
            onClick={() => void openReview()}
          >
            Review
          </button>
        </nav>
        <div className="header-actions">
          <span className="local-badge">
            <span className={`status-dot ${error ? 'status-error' : ''}`} />
            {error ? 'Engine offline' : 'Local engine'}
          </span>
          <Button variant="ghost" size="icon" aria-label="Settings" disabled>
            <Settings2 />
          </Button>
        </div>
      </header>
      {mode === 'review' && (
        <section className="history-strip">
          <div>
            <History className="size-4" />
            <strong>Saved hands</strong>
          </div>
          <div className="history-list">
            {history.map((item) => (
              <button
                key={item.sessionId}
                className={
                  review?.sessionId === item.sessionId ? 'history-active' : ''
                }
                onClick={() => void selectHistory(item.sessionId)}
              >
                <b>Seed {item.seed}</b>
                <span>
                  {item.status === 'terminal'
                    ? item.result?.winners.includes(0)
                      ? 'Won'
                      : 'Complete'
                    : 'In progress'}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}
      {mode === 'train' ? (
        <SolverLab request={request} />
      ) : (
        <section className="workspace">
          <aside className="hand-ranks">
            <div className="hand-ranks-heading">
              <div>
                <span className="eyebrow">Poker hands</span>
                <h2>Hand rankings</h2>
              </div>
              <Switch
                size="sm"
                aria-label="Highlight your best five cards"
                checked={highlightBestFive}
                onCheckedChange={setHighlightBestFive}
              />
            </div>
            <p className="chance-title">Chance by river · hand or better</p>
            <ol>
              {HAND_RANKS.map(([id, label], index) => (
                <li
                  key={id}
                  className={
                    highlightBestFive && observation?.handCategory === id
                      ? 'rank-active'
                      : ''
                  }
                >
                  <span>{index + 1}</span>
                  <b>{label}</b>
                  {currentRankIndex >= 0 && index < currentRankIndex && (
                    <em>
                      {handChances
                        ? chanceLabel(handChances.atLeast[id] ?? 0)
                        : '…'}
                    </em>
                  )}
                </li>
              ))}
            </ol>
            {handChances && (
              <p className="chance-method">
                {handChances.method === 'exact'
                  ? 'Exact runouts'
                  : `${handChances.samples.toLocaleString()} sampled runouts`}{' '}
                · Villain cards unknown
              </p>
            )}
            {observation?.handCategory ? (
              <div className="current-hand">
                <span>Your current hand</span>
                <strong>
                  {observation.handDescription ??
                    HAND_RANKS.find(
                      ([id]) => id === observation.handCategory,
                    )?.[1]}
                </strong>
                <small>
                  {
                    HAND_RANKS.find(
                      ([id]) => id === observation.handCategory,
                    )?.[1]
                  }
                </small>
              </div>
            ) : (
              <div className="current-hand current-hand-empty">
                <span>Your current hand</span>
                <strong>Available on the flop</strong>
              </div>
            )}
          </aside>
          <div className="table-column">
            <div className="session-bar">
              <div>
                <span className="eyebrow">
                  {mode === 'review' ? 'Hand replay' : 'Cash game'} ·{' '}
                  {observation
                    ? `${chips(observation.seats[0].stack + observation.seats[0].handCommitted)} / ${chips(observation.seats[1].stack + observation.seats[1].handCommitted)} · Seed ${observation.seed}`
                    : ''}
                </span>
                <h1>
                  {mode === 'review'
                    ? 'Review the action line'
                    : tie
                      ? 'Split pot'
                      : heroWon
                        ? 'You win'
                        : opponentWon
                          ? 'Villain wins'
                          : 'Choose your action'}
                </h1>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void resetMatch()}
                disabled={busy}
              >
                <RotateCcw />
                Reset
              </Button>
            </div>
            {error && (
              <div className="error-banner">
                <TriangleAlert className="size-4" />
                <div>
                  <strong>Can’t reach the game engine</strong>
                  <span>
                    {error}. Start the local API on port 8000, then try again.
                  </span>
                </div>
              </div>
            )}
            <div className="poker-table-wrap">
              <div className="poker-table">
                <div className="felt-grain" />
                <div
                  className={`seat opponent-seat ${opponentWon ? 'winning-seat' : ''}`}
                >
                  <div className="seat-meta">
                    <span className="avatar">V</span>
                    <div>
                      <Select
                        value={opponentProvider}
                        onValueChange={(value) =>
                          void selectOpponent(value as string)
                        }
                      >
                        <SelectTrigger
                          className="opponent-model-trigger"
                          aria-label="Villain model"
                        >
                          <SelectValue>
                            {modelName(opponentProvider)}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {providers.map((provider) => (
                            <SelectItem key={provider.id} value={provider.id}>
                              {modelName(provider.id)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <small>
                        Villain · {opponent ? chips(opponent.stack) : '—'}
                      </small>
                    </div>
                    {opponentWon && <span className="winner-chip">Winner</span>}
                    {opponent?.streetCommitted ? (
                      <span className="seat-bet">
                        Bet {chips(opponent.streetCommitted)}
                      </span>
                    ) : null}
                  </div>
                  <div className="hole-cards">
                    {opponentCards ? (
                      opponentCards.map((card) => (
                        <PlayingCard
                          card={card}
                          importance={villainImportance[card] ?? 0}
                          highlight="villain"
                          key={card}
                        />
                      ))
                    ) : (
                      <>
                        <PlayingCard hidden />
                        <PlayingCard hidden />
                      </>
                    )}
                  </div>
                  {observation?.button === 1 && (
                    <span className="dealer-chip">D</span>
                  )}
                </div>
                <div className="pot-label">
                  <span>Pot</span>
                  <strong>{observation ? chips(observation.pot) : '—'}</strong>
                </div>
                <div className="board-cards">
                  {observation?.board.map((card) =>
                    villainImportance[card] === 3 ? (
                      <PlayingCard
                        card={card}
                        importance={3}
                        highlight="villain"
                        key={card}
                      />
                    ) : (
                      <PlayingCard
                        card={card}
                        importance={cardImportance[card] ?? 0}
                        key={card}
                      />
                    ),
                  )}
                  {Array.from({
                    length: Math.max(0, 5 - (observation?.board.length ?? 0)),
                  }).map((_, index) => (
                    <div className="card-slot" key={index} />
                  ))}
                </div>
                <div className="street-label">
                  {observation?.street ?? 'Loading'}
                </div>
                <div
                  className={`seat hero-seat ${heroWon ? 'winning-seat' : ''}`}
                >
                  <div className="hole-cards">
                    {observation?.holeCards.map((card) => (
                      <PlayingCard
                        card={card}
                        importance={cardImportance[card] ?? 0}
                        key={card}
                      />
                    )) ?? (
                      <>
                        <div className="card-slot" />
                        <div className="card-slot" />
                      </>
                    )}
                  </div>
                  <div className="seat-meta">
                    <span className="avatar hero-avatar">You</span>
                    <div>
                      <b>
                        {tie ? 'Split pot' : heroWon ? 'Winner' : 'Your hand'}
                      </b>
                      <small>{hero ? chips(hero.stack) : '—'}</small>
                    </div>
                    {hero?.streetCommitted ? (
                      <span className="seat-bet">
                        Bet {chips(hero.streetCommitted)}
                      </span>
                    ) : null}
                  </div>
                  {observation?.button === 0 && (
                    <span className="dealer-chip hero-dealer">D</span>
                  )}
                </div>
                {terminal && (
                  <div
                    className={`result-banner ${heroWon ? 'result-win' : ''}`}
                  >
                    <strong>
                      {tie
                        ? 'Pot split'
                        : heroWon
                          ? 'You won the hand'
                          : 'Villain won the hand'}
                    </strong>
                    <span>
                      {observation?.result?.reason} ·{' '}
                      {observation?.result?.payouts.map(chips).join(' / ')}
                    </span>
                  </div>
                )}
                {busy && (
                  <div className="table-loading">
                    <LoaderCircle className="size-5 animate-spin" />
                    Thinking…
                  </div>
                )}
              </div>
            </div>
            <div className="decision-dock">
              <div className="decision-copy">
                <span className="pulse-ring" />
                <div>
                  <strong>
                    {mode === 'review'
                      ? `Action ${reviewStep} of ${Math.max(0, (review?.events.length ?? 1) - 1)}`
                      : terminal
                        ? `Hand complete · ${observation?.result?.reason}`
                        : 'Your turn'}
                  </strong>
                  <small>
                    {mode === 'review'
                      ? reviewEvent?.action
                        ? `Player ${(reviewEvent.actorSeat ?? 0) + 1} · ${reviewEvent.action.type.replaceAll('-', ' ')}`
                        : 'Ready to act'
                      : terminal
                        ? `Payouts ${observation?.result?.payouts.map(chips).join(' / ')}`
                        : `To call ${chips(observation?.amountToCall ?? 0)} · Pot ${chips(observation?.pot ?? 0)}`}
                  </small>
                </div>
              </div>
              {mode === 'play' && legalRaise && (
                <div className="raise-compact">
                  <div className="raise-presets">
                    <button onClick={() => setRaiseAmount(potTarget(0.5))}>
                      ½
                    </button>
                    <button onClick={() => setRaiseAmount(potTarget(0.75))}>
                      ¾
                    </button>
                    <button onClick={() => setRaiseAmount(potTarget(1))}>
                      Pot
                    </button>
                  </div>
                  <div className="raise-slider">
                    <Slider
                      aria-label="Raise size"
                      min={0}
                      max={Math.max(0, sizingStops.length - 1)}
                      step={1}
                      value={[activeStop]}
                      onValueChange={(value) =>
                        setRaiseAmount(
                          sizingStops[
                            typeof value === 'number' ? value : value[0]
                          ],
                        )
                      }
                    />
                    <div className="raise-scale">
                      <span>{chips(sizingStops[0] ?? 0)}</span>
                      <span>{chips(sizingStops.at(-1) ?? 0)}</span>
                    </div>
                  </div>
                  <fieldset
                    className="raise-stepper"
                    aria-label="Raise amount in half-big-blind steps"
                  >
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Decrease raise by half a big blind"
                      disabled={clampedRaise <= (legalRaise.minAmount ?? 0)}
                      onClick={() => stepRaise(-1)}
                    >
                      <Minus />
                    </Button>
                    <output aria-live="polite">{chips(clampedRaise)}</output>
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Increase raise by half a big blind"
                      disabled={clampedRaise >= (legalRaise.maxAmount ?? 0)}
                      onClick={() => stepRaise(1)}
                    >
                      <Plus />
                    </Button>
                  </fieldset>
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={() => void act(legalRaise, clampedRaise)}
                  >
                    Raise
                  </Button>
                </div>
              )}
              <div className="decision-actions">
                {mode === 'review' ? (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={reviewStep === 0}
                      onClick={() =>
                        setReviewStep((value) => Math.max(0, value - 1))
                      }
                    >
                      <ChevronLeft />
                      Previous
                    </Button>
                    <Button
                      size="sm"
                      disabled={
                        !review || reviewStep >= review.events.length - 1
                      }
                      onClick={() =>
                        setReviewStep((value) =>
                          Math.min((review?.events.length ?? 1) - 1, value + 1),
                        )
                      }
                    >
                      Next
                      <ChevronRight />
                    </Button>
                  </>
                ) : terminal ? (
                  <Button
                    size="sm"
                    onClick={() => void dealNextHand()}
                    disabled={
                      (observation?.seats.some((seat) => seat.stack <= 0) ??
                        false) ||
                      busy
                    }
                  >
                    Deal next hand
                  </Button>
                ) : (
                  observation?.legalActions
                    .filter(
                      (action) =>
                        action.type !== 'raise-to' && action.type !== 'all-in',
                    )
                    .map((action) => (
                      <Button
                        key={action.type}
                        variant={
                          action.type === 'fold' ? 'outline' : 'secondary'
                        }
                        size="sm"
                        disabled={busy}
                        onClick={() => void act(action)}
                      >
                        {actionLabel(action)}
                      </Button>
                    ))
                )}
              </div>
            </div>
          </div>
          <aside className="coach-panel">
            <div className="coach-heading coach-heading-first">
              <div>
                <span className="eyebrow">Strategy reference</span>
                <h2>{activeStrategy ? 'Action mix' : 'Strategy hidden'}</h2>
              </div>
            </div>
            <div className="model-control">
              <span>Advice model</span>
              <Select
                value={trainerProvider}
                onValueChange={(value) => {
                  setTrainerProvider(value as string);
                  setStrategy(null);
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>{modelName(trainerProvider)}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.id} value={provider.id}>
                      {modelName(provider.id)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="auto-strategy">
              <div>
                <strong>Show strategy</strong>
                <span>Show or hide action advice</span>
              </div>
              <Switch
                aria-label="Show strategy advice"
                checked={showStrategy}
                onCheckedChange={setShowStrategy}
              />
            </div>
            {activeStrategy ? (
              <div className="strategy-list">
                {visibleStrategy.map((item) => (
                  <div
                    className={`strategy-item ${item.available === false ? 'strategy-unavailable' : ''}`}
                    key={`${item.abstractAction}-${item.legalAction?.type}-${item.legalAction?.amount}`}
                  >
                    <div>
                      <span>
                        {strategyLabel(item)}
                        {item.available === false ? ' · unavailable' : ''}
                      </span>
                      <b>
                        {(item.probability * 100).toFixed(
                          item.probability < 0.01 ? 1 : 0,
                        )}
                        %
                      </b>
                    </div>
                    <div className="strategy-track">
                      <span style={{ width: `${item.probability * 100}%` }} />
                    </div>
                  </div>
                ))}
                {sortedStrategy.length > 3 && (
                  <button
                    className="strategy-expand"
                    onClick={() => setShowAllStrategy((value) => !value)}
                  >
                    {showAllStrategy ? (
                      <>
                        <ChevronUp />
                        Show top 3
                      </>
                    ) : (
                      <>
                        <ChevronDown />
                        Show all {sortedStrategy.length} model actions
                      </>
                    )}
                  </button>
                )}
                <p className="strategy-meta">
                  {modelName(activeStrategy.provider.modelId)} ·{' '}
                  {activeStrategy.diagnostics.inferenceMs.toFixed(1)} ms
                </p>
              </div>
            ) : showStrategy ? (
              <div className="coach-empty">
                <div className="metric-grid">
                  <div>
                    <span>Pot</span>
                    <strong>
                      {observation ? chips(observation.pot) : '—'}
                    </strong>
                  </div>
                  <div>
                    <span>Street</span>
                    <strong className="capitalize">
                      {observation?.street ?? '—'}
                    </strong>
                  </div>
                </div>
                <div className="range-block">
                  <div className="range-row">
                    <span>Last action</span>
                    <b>
                      {recentActions[0]?.type.replaceAll('-', ' ') ??
                        'Blinds posted'}
                    </b>
                  </div>
                  <div className="action-history">
                    {recentActions.map((item, index) => (
                      <span key={`${item.seat}-${item.type}-${index}`}>
                        P{item.seat + 1} · {item.type.replaceAll('-', ' ')}{' '}
                        {item.amount ? chips(item.amount) : ''}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
            <section className="equity-card" aria-label="Equity calculator">
              <div>
                <span className="eyebrow">Equity vs random hand</span>
                <strong>
                  {equity
                    ? `${(equity.equity * 100).toFixed(1)}%`
                    : equityRequest
                      ? 'Calculating…'
                      : 'Unavailable'}
                </strong>
              </div>
              {equity && (
                <>
                  <div className="equity-track">
                    <span style={{ width: `${equity.equity * 100}%` }} />
                  </div>
                  <p>
                    {equity.method === 'exact'
                      ? `Exact · ${equity.samples.toLocaleString()} outcomes`
                      : `Sampled · ${equity.samples.toLocaleString()} deals · ±${(1.96 * equity.standardError * 100).toFixed(1)}%`}
                  </p>
                </>
              )}
            </section>
          </aside>
        </section>
      )}
    </main>
  );
}
