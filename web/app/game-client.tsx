'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
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
  TrainFront,
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
const PREFLOP_RANKS = 'AKQJT98765432'.split('');

function startingHandClass(cards: string[]) {
  if (cards.length !== 2) return '';
  const ordered = [...cards].sort(
    (left, right) =>
      PREFLOP_RANKS.indexOf(left[0]) - PREFLOP_RANKS.indexOf(right[0]),
  );
  if (ordered[0][0] === ordered[1][0]) return ordered[0][0].repeat(2);
  return `${ordered[0][0]}${ordered[1][0]}${ordered[0][1] === ordered[1][1] ? 's' : 'o'}`;
}

function matrixHandClass(row: number, column: number) {
  const rowRank = PREFLOP_RANKS[row];
  const columnRank = PREFLOP_RANKS[column];
  if (row === column) return rowRank.repeat(2);
  return row < column
    ? `${rowRank}${columnRank}s`
    : `${columnRank}${rowRank}o`;
}

function estimatedPreflopEquity(handClass: string) {
  const high = 12 - PREFLOP_RANKS.indexOf(handClass[0]);
  const low = 12 - PREFLOP_RANKS.indexOf(handClass[1]);
  const pair = high === low;
  const suited = handClass.endsWith('s');
  const gap = high - low;
  let strength = (high + low) / 24;
  if (pair) strength = 0.48 + high / 24;
  if (suited) strength += 0.08;
  if (gap <= 1) strength += 0.06;
  else if (gap >= 4) strength -= 0.06;
  return Math.max(0.02, Math.min(1, strength));
}
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
type VillainRange = {
  method: string;
  description: string;
  observedActions: number;
  effectiveCombos80: number;
  combos: Array<{ cards: string[]; weight: number }>;
  topClasses: Array<{ handClass: string; weight: number }>;
};

function VillainRangeMatrix({
  range,
  heroCards,
}: {
  range: VillainRange;
  heroCards: string[];
}) {
  const classWeights = useMemo(() => {
    const weights = new Map<string, number>();
    range.combos.forEach((combo) => {
      const handClass = startingHandClass(combo.cards);
      weights.set(handClass, (weights.get(handClass) ?? 0) + combo.weight);
    });
    return weights;
  }, [range]);
  const heroClass = startingHandClass(heroCards);
  const topRangeClasses = useMemo(
    () =>
      new Set(
        [...classWeights.entries()]
          .sort((left, right) => right[1] - left[1])
          .slice(0, 18)
          .map(([handClass]) => handClass),
      ),
    [classWeights],
  );

  return (
    <div className="range-matrix-scroll">
      <div
        className="range-matrix"
        role="grid"
        aria-label="Villain starting hand range matrix"
      >
        {PREFLOP_RANKS.flatMap((_, row) =>
          PREFLOP_RANKS.map((__, column) => {
            const handClass = matrixHandClass(row, column);
            const equity = estimatedPreflopEquity(handClass);
            const villainWeight = classWeights.get(handClass) ?? 0;
            const hue = 220 - equity * 212;
            const isHero = handClass === heroClass;
            const isTopRange = topRangeClasses.has(handClass) && !isHero;
            const tooltip = `${handClass} · ${(equity * 100).toFixed(0)}% relative equity · ${(villainWeight * 100).toFixed(2)}% of estimated Villain range${isHero ? ' · your hand' : isTopRange ? ' · top Villain range option' : ''}`;
            return (
              <div
                key={handClass}
                role="gridcell"
                className={`range-matrix-cell${isHero ? ' range-matrix-hero' : ''}${isTopRange ? ' range-matrix-villain' : ''}`}
                style={{
                  background: `hsl(${hue} 62% ${78 - equity * 30}%)`,
                }}
                data-tooltip={tooltip}
                title={tooltip}
                aria-label={`${handClass}, ${(equity * 100).toFixed(0)} percent relative equity, ${(villainWeight * 100).toFixed(2)} percent Villain range${isHero ? ', your hand' : ''}`}
              >
                <span>{handClass}</span>
                {(isHero || isTopRange) && <i aria-hidden="true" />}
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}
type HandChances = {
  method: 'exact' | 'sampled';
  samples: number;
  atLeast: Record<string, number>;
  exact: Record<string, number>;
  combinations: Record<string, number>;
  outs: Record<string, number>;
  baselineExact: Record<string, number>;
  baselineAtLeast: Record<string, number>;
  percentile75Exact: Record<string, number>;
  baselineSamples: number;
  baselineLabel: string;
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
type TrainingEvent = {
  event: 'started' | 'progress' | 'complete' | 'failed';
  iteration?: number;
  iterations?: number;
  gameValue?: number;
  exploitability?: number;
  referenceScore?: number;
  positiveRegret?: number;
  informationSets?: number;
  elapsedMs?: number;
  strategy?: Array<{
    informationSet: string;
    label?: string;
    actions: Record<string, number>;
  }>;
};
type TrainingJob = {
  jobId: string;
  status: 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';
  game: string;
  algorithm: string;
  mode: 'visual' | 'headless';
  events: TrainingEvent[];
  error: string | null;
  checkpointHash: string | null;
};
type TrainingJobSummary = Omit<TrainingJob, 'events'> & {
  iterations: number;
  seed: number;
};
type TrainingModel = {
  modelId: string;
  sourceJobId: string;
  name: string;
  game: string;
  algorithm: string;
  version: string;
  iterations: number;
  seed: number;
  gameValue?: number;
  exploitability?: number;
  referenceScore?: number;
  artifactHash: string;
  checkpointHash: string;
  strategy: Array<{
    informationSet: string;
    label?: string;
    actions: Record<string, number>;
  }>;
};
type RangeEstimatorEvent = {
  event: 'started' | 'progress' | 'complete' | 'failed';
  epoch?: number;
  epochs?: number;
  validationNll?: number;
  validationBrier?: number;
  validationTop1?: number;
  validationEce?: number;
};
type RangeEstimatorJob = {
  jobId: string;
  status: 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';
  events: RangeEstimatorEvent[];
  error: string | null;
};
type RangeEstimatorEval = {
  testExamples: number;
  testNll: number;
  testBrier: number;
  testTop1: number;
  testEce: number;
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
        <span className="card-face">
          <b>{card?.[0]}</b>
          <i>{card ? SUITS[card[1]] ?? card[1] : ''}</i>
        </span>
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
  const [workspace, setWorkspace] = useState<'solver' | 'policy' | 'range'>('solver'),
    [executionMode, setExecutionMode] = useState<'visual' | 'headless'>(
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
  if (workspace === 'policy') {
    return (
      <section className="solver-workspace">
        <div className="training-subnav" aria-label="Model training workspace">
          <span>Model Training</span>
          <button onClick={() => setWorkspace('solver')}>Subgame Solver</button>
          <button className="active">Train Policy</button>
          <button onClick={() => setWorkspace('range')}>Range Estimator</button>
        </div>
        <TrainPolicyLab request={request} />
      </section>
    );
  }
  if (workspace === 'range') {
    return (
      <section className="solver-workspace">
        <div className="training-subnav" aria-label="Model training workspace">
          <span>Model Training</span>
          <button onClick={() => setWorkspace('solver')}>Subgame Solver</button>
          <button onClick={() => setWorkspace('policy')}>Train Policy</button>
          <button className="active">Range Estimator</button>
        </div>
        <RangeEstimatorLab request={request} />
      </section>
    );
  }
  return (
    <section className="solver-workspace">
      <div className="training-subnav" aria-label="Model training workspace">
        <span>Model Training</span>
        <button className="active">Subgame Solver</button>
        <button onClick={() => setWorkspace('policy')}>Train Policy</button>
        <button onClick={() => setWorkspace('range')}>Range Estimator</button>
      </div>
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

function RangeEstimatorLab({ request }: { request: ApiRequest }) {
  const [seed, setSeed] = useState(20260828);
  const [hands, setHands] = useState(1000);
  const [epochs, setEpochs] = useState(20);
  const [learningRate, setLearningRate] = useState(0.02);
  const [job, setJob] = useState<RangeEstimatorJob | null>(null);
  const [evaluation, setEvaluation] = useState<RangeEstimatorEval | null>(null);
  const [view, setView] = useState<'train' | 'eval'>('train');
  const [error, setError] = useState<string | null>(null);
  const token = useRef(0);
  const running = job?.status === 'queued' || job?.status === 'running';
  const points = useMemo(
    () => (job?.events ?? []).filter((event) => event.epoch !== undefined).map((event) => ({
      epoch: event.epoch ?? 0,
      validationNll: event.validationNll ?? 0,
      validationBrier: event.validationBrier ?? 0,
      validationEce: event.validationEce ?? 0,
    })),
    [job],
  );
  const latest = points.at(-1);
  async function follow(initial: RangeEstimatorJob) {
    const currentToken = ++token.current;
    let current = initial;
    setJob(current);
    while (currentToken === token.current && (current.status === 'queued' || current.status === 'running')) {
      await new Promise((resolve) => setTimeout(resolve, 300));
      current = await request<RangeEstimatorJob>(`/v1/range-estimator/jobs/${current.jobId}`);
      setJob(current);
    }
  }
  async function start() {
    setError(null); setEvaluation(null); setView('train');
    try {
      await follow(await request<RangeEstimatorJob>('/v1/range-estimator/jobs', {
        method: 'POST', body: JSON.stringify({ schemaVersion: '1.0.0', seed, hands, epochs, learningRate, reportEvery: 1 }),
      }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Range estimator training failed'); }
  }
  async function evaluate() {
    if (!job || job.status !== 'complete') return;
    setError(null);
    try { setEvaluation(await request<RangeEstimatorEval>(`/v1/range-estimator/jobs/${job.jobId}/eval`)); setView('eval'); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Evaluation failed'); }
  }
  async function cancel() {
    if (!job) return; ++token.current;
    setJob(await request<RangeEstimatorJob>(`/v1/range-estimator/jobs/${job.jobId}/cancel`, { method: 'POST' }));
  }
  return (
    <div className="policy-lab">
      <div className="policy-heading">
        <div><span className="eyebrow">Range estimator · v1</span><h1>Train a blocker-aware Villain range model</h1><p>The trainer learns a posterior over only legal two-card combinations, then checks calibration on a held-out synthetic split.</p></div>
      </div>
      {error && <div className="error-banner"><TriangleAlert /><div><strong>Range estimator error</strong><span>{error}</span></div></div>}
      <div className="training-subnav range-estimator-subnav"><button className={view === 'train' ? 'active' : ''} onClick={() => setView('train')}>Train</button><button className={view === 'eval' ? 'active' : ''} disabled={!job || job.status !== 'complete'} onClick={() => void evaluate()}>Eval</button></div>
      {view === 'train' ? <div className="policy-grid range-estimator-grid">
        <aside className="policy-controls-card"><span className="eyebrow">Run configuration</span><h2>Masked combo scorer</h2>
          <label><span>Dataset seed</span><input type="number" value={seed} onChange={(event) => setSeed(Number(event.target.value))} /></label>
          <label><span>Synthetic hands</span><input type="number" min="100" max="100000" value={hands} onChange={(event) => setHands(Number(event.target.value))} /></label>
          <label><span>Epochs</span><input type="number" min="1" max="1000" value={epochs} onChange={(event) => setEpochs(Number(event.target.value))} /></label>
          <label><span>Learning rate</span><input type="number" min="0.001" max="1" step="0.001" value={learningRate} onChange={(event) => setLearningRate(Number(event.target.value))} /></label>
          {running ? <Button variant="outline" onClick={() => void cancel()}><Ban /> Cancel run</Button> : <Button onClick={() => void start()}><Play /> Start training</Button>}
        </aside>
        <article className="policy-progress-card"><div className="solver-card-heading"><div><span className="eyebrow">Live validation</span><h2>Generalization and calibration</h2></div>{job && <i className={`solver-status solver-status-${job.status}`}>{job.status}</i>}</div>
          {points.length ? <ChartContainer className="policy-chart" config={{ validationNll: { label: 'Validation NLL', color: '#1b6b4f' }, validationBrier: { label: 'Brier score', color: '#b0863e' }, validationEce: { label: 'Calibration error', color: '#b24c4c' } }}><LineChart data={points} margin={{ left: 4, right: 12, top: 12 }}><CartesianGrid vertical={false} /><XAxis dataKey="epoch" tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} width={48} /><ChartTooltip content={<ChartTooltipContent />} /><Line type="monotone" dataKey="validationNll" stroke="var(--color-validationNll)" strokeWidth={3} dot={false} /><Line type="monotone" dataKey="validationEce" stroke="var(--color-validationEce)" strokeWidth={2} dot={false} /></LineChart></ChartContainer> : <div className="policy-empty">Start a run to view epoch-by-epoch validation metrics.</div>}
          <div className="policy-metrics"><div><span>Epoch</span><strong>{latest?.epoch ?? '—'} / {epochs}</strong></div><div><span>Validation NLL</span><strong>{latest?.validationNll?.toFixed(3) ?? '—'}</strong></div><div><span>Brier score</span><strong>{latest?.validationBrier?.toFixed(4) ?? '—'}</strong></div><div><span>Calibration error</span><strong>{latest?.validationEce?.toFixed(4) ?? '—'}</strong></div></div>
        </article>
        <aside className="policy-history-card"><span className="eyebrow">What this measures</span><h2>Evaluation gate</h2><p className="text-sm leading-relaxed text-muted-foreground">NLL rewards assigning probability to the actual hidden combo. Brier and calibration error show whether confidence matches observed outcomes. Eval stays separate until a run completes.</p>{job?.status === 'complete' && <Button variant="outline" className="mt-4" onClick={() => void evaluate()}>Run held-out eval</Button>}</aside>
      </div> : <article className="policy-progress-card range-estimator-eval"><span className="eyebrow">Held-out evaluation</span><h2>Test split metrics</h2>{evaluation ? <div className="policy-metrics"><div><span>Test examples</span><strong>{evaluation.testExamples}</strong></div><div><span>Test NLL</span><strong>{evaluation.testNll.toFixed(3)}</strong></div><div><span>Brier score</span><strong>{evaluation.testBrier.toFixed(4)}</strong></div><div><span>Calibration error</span><strong>{evaluation.testEce.toFixed(4)}</strong></div></div> : <div className="policy-empty">Run a completed model on the held-out test split.</div>}</article>}
    </div>
  );
}

function TrainPolicyLab({ request }: { request: ApiRequest }) {
  const [trainingGame, setTrainingGame] = useState<
      'kuhn-poker' | 'leduc-holdem' | 'restricted-hu-nlhe-flop'
    >('kuhn-poker'),
    [iterations, setIterations] = useState(5000),
    [seed, setSeed] = useState(7),
    [reportEvery, setReportEvery] = useState(100),
    [resumeIterations, setResumeIterations] = useState(10000),
    [job, setJob] = useState<TrainingJob | null>(null),
    [history, setHistory] = useState<TrainingJobSummary[]>([]),
    [models, setModels] = useState<TrainingModel[]>([]),
    [leftModelId, setLeftModelId] = useState(''),
    [rightModelId, setRightModelId] = useState(''),
    [error, setError] = useState<string | null>(null);
  const pollToken = useRef(0);
  const running = job?.status === 'queued' || job?.status === 'running';
  const latest = job?.events.at(-1);
  const complete = [...(job?.events ?? [])]
    .reverse()
    .find((event) => event.event === 'complete');
  const points = useMemo(
    () =>
      (job?.events ?? [])
        .filter(
          (event) =>
            (event.event === 'progress' || event.event === 'complete') &&
            (event.exploitability !== undefined ||
              event.referenceScore !== undefined ||
              event.positiveRegret !== undefined),
        )
        .map((event) => ({
          iteration: event.iteration ?? event.iterations ?? 0,
          exploitability: event.exploitability ?? 0,
          referenceScore: event.referenceScore ?? 0,
          gameValue: event.gameValue ?? 0,
          positiveRegret: event.positiveRegret ?? 0,
          informationSets: event.informationSets ?? 0,
          elapsedMs: event.elapsedMs ?? 0,
        })),
    [job],
  );
  const strategy = complete?.strategy ?? [];

  const refreshHistory = useCallback(async () => {
    const result = await request<{ jobs: TrainingJobSummary[] }>(
      '/v1/training/jobs?limit=12',
    );
    setHistory(result.jobs);
  }, [request]);
  const refreshModels = useCallback(async () => {
    const result = await request<{ models: TrainingModel[] }>(
      '/v1/training/models',
    );
    setModels(result.models);
    setLeftModelId((current) => current || result.models[0]?.modelId || '');
    setRightModelId(
      (current) =>
        current || result.models[1]?.modelId || result.models[0]?.modelId || '',
    );
  }, [request]);

  useEffect(() => {
    void Promise.all([refreshHistory(), refreshModels()]).catch(() => {
      // The API may still be restarting; starting a run will surface errors.
    });
  }, [refreshHistory, refreshModels]);

  async function follow(initial: TrainingJob) {
    const token = ++pollToken.current;
    let current = initial;
    setJob(current);
    while (
      token === pollToken.current &&
      (current.status === 'queued' || current.status === 'running')
    ) {
      await new Promise((resolve) => setTimeout(resolve, 300));
      current = await request<TrainingJob>(
        `/v1/training/jobs/${current.jobId}`,
      );
      setJob(current);
    }
    await refreshHistory();
  }

  async function startTraining() {
    setError(null);
    try {
      const submitted = await request<TrainingJob>('/v1/training/jobs', {
        method: 'POST',
        body: JSON.stringify({
          schemaVersion: '1.0.0',
          game: trainingGame,
          algorithm:
            trainingGame === 'restricted-hu-nlhe-flop'
              ? 'external-sampling-mccfr'
              : 'cfr',
          mode: 'visual',
          iterations,
          seed,
          reportEvery,
        }),
      });
      await follow(submitted);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Training failed');
    }
  }

  async function cancelTraining() {
    if (!job) return;
    ++pollToken.current;
    try {
      setJob(
        await request<TrainingJob>(`/v1/training/jobs/${job.jobId}/cancel`, {
          method: 'POST',
        }),
      );
      await refreshHistory();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Cancel failed');
    }
  }

  async function resumeTraining() {
    if (!job) return;
    setError(null);
    try {
      const resumed = await request<TrainingJob>(
        `/v1/training/jobs/${job.jobId}/resume`,
        {
          method: 'POST',
          body: JSON.stringify({
            iterations: resumeIterations,
            mode: 'visual',
            reportEvery,
          }),
        },
      );
      setIterations(resumeIterations);
      await follow(resumed);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Resume failed');
    }
  }

  async function downloadCheckpoint() {
    if (!job) return;
    try {
      const checkpoint = await request<Record<string, unknown>>(
        `/v1/training/jobs/${job.jobId}/checkpoint`,
      );
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(checkpoint, null, 2)], {
          type: 'application/json',
        }),
      );
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${job.jobId}-checkpoint.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Checkpoint unavailable',
      );
    }
  }

  async function registerModel() {
    if (!job) return;
    setError(null);
    try {
      const registered = await request<TrainingModel>(
        `/v1/training/jobs/${job.jobId}/register`,
        { method: 'POST', body: JSON.stringify({}) },
      );
      await refreshModels();
      setLeftModelId(registered.modelId);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Registration failed',
      );
    }
  }

  async function selectJob(summary: TrainingJobSummary) {
    ++pollToken.current;
    setError(null);
    try {
      const selected = await request<TrainingJob>(
        `/v1/training/jobs/${summary.jobId}`,
      );
      setIterations(summary.iterations);
      setResumeIterations(Math.max(summary.iterations * 2, 1000));
      setSeed(summary.seed);
      setTrainingGame(
        summary.game === 'restricted-hu-nlhe-flop'
          ? 'restricted-hu-nlhe-flop'
          : summary.game === 'leduc-holdem'
            ? 'leduc-holdem'
            : 'kuhn-poker',
      );
      setJob(selected);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load run');
    }
  }

  const latestProgress =
    [...(job?.events ?? [])]
      .reverse()
      .find((event) => event.event === 'progress') ?? latest;
  const currentIteration =
    latestProgress?.iteration ?? latestProgress?.iterations ?? 0;
  const progressPercent = Math.min(100, (currentIteration / iterations) * 100);
  const iterationRate =
    latestProgress?.elapsedMs && latestProgress.elapsedMs > 0
      ? currentIteration / (latestProgress.elapsedMs / 1000)
      : null;
  const leftModel = models.find((model) => model.modelId === leftModelId);
  const rightModel = models.find((model) => model.modelId === rightModelId);
  const aggressiveAction =
    leftModel?.game === 'leduc-holdem'
      ? 'raise'
      : leftModel?.game === 'restricted-hu-nlhe-flop'
        ? 'bet-50'
        : 'bet';
  const trainingLabel =
    trainingGame === 'kuhn-poker'
      ? 'Kuhn Poker'
      : trainingGame === 'leduc-holdem'
        ? 'Leduc Hold’em'
        : 'Restricted Hold’em Flop';
  const progressMetric =
    trainingGame === 'kuhn-poker'
      ? 'exploitability'
      : trainingGame === 'leduc-holdem'
        ? 'referenceScore'
        : 'positiveRegret';
  const comparisonRows = leftModel
    ? leftModel.strategy.map((node) => {
        const other = rightModel?.strategy.find(
          (candidate) => candidate.informationSet === node.informationSet,
        );
        return {
          informationSet: node.informationSet,
          label: node.label ?? node.informationSet,
          left: node.actions[aggressiveAction] ?? 0,
          right: other?.actions[aggressiveAction] ?? 0,
        };
      })
    : [];
  return (
    <div className="policy-lab">
      <div className="policy-heading">
        <div>
          <span className="eyebrow">Validated CFR laboratory</span>
          <h1>Train a policy from scratch</h1>
          <p>
            Train validated small poker games, save their checkpoints, and use
            the resulting policies through the shared model registry.
          </p>
        </div>
      </div>
      {error && (
        <div className="error-banner">
          <TriangleAlert />
          <div>
            <strong>Training error</strong>
            <span>{error}</span>
          </div>
        </div>
      )}
      <div className="policy-grid">
        <aside className="policy-controls-card">
          <span className="eyebrow">Run configuration</span>
          <h2>
            {trainingLabel} · {trainingGame === 'restricted-hu-nlhe-flop' ? 'External-sampling MCCFR' : 'CFR'}
          </h2>
          <label>
            <span>Training game</span>
            <Select
              value={trainingGame}
              onValueChange={(value) => {
                const game = value as 'kuhn-poker' | 'leduc-holdem' | 'restricted-hu-nlhe-flop';
                setTrainingGame(game);
                setIterations(game === 'restricted-hu-nlhe-flop' ? 1000 : game === 'leduc-holdem' ? 100 : 5000);
                setReportEvery(game === 'restricted-hu-nlhe-flop' ? 25 : game === 'leduc-holdem' ? 10 : 100);
                setJob(null);
              }}
              disabled={running}
            >
              <SelectTrigger aria-label="Training game">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="kuhn-poker">Kuhn Poker</SelectItem>
                <SelectItem value="leduc-holdem">Leduc Hold’em</SelectItem>
                <SelectItem value="restricted-hu-nlhe-flop">Restricted Hold’em Flop</SelectItem>
              </SelectContent>
            </Select>
          </label>
          <label>
            <span>Iterations</span>
            <input
              type="number"
              min={1}
              max={1000000}
              value={iterations}
              onChange={(event) => setIterations(Number(event.target.value))}
              disabled={running}
            />
          </label>
          <label>
            <span>Random seed</span>
            <input
              type="number"
              value={seed}
              onChange={(event) => setSeed(Number(event.target.value))}
              disabled={running}
            />
          </label>
          <label>
            <span>Report every</span>
            <input
              type="number"
              min={1}
              max={iterations}
              value={reportEvery}
              onChange={(event) => setReportEvery(Number(event.target.value))}
              disabled={running}
            />
          </label>
          <p>
            {trainingGame === 'kuhn-poker'
              ? 'Exact exploitability is evaluated at each reporting interval.'
              : trainingGame === 'leduc-holdem'
                ? 'Leduc progress is evaluated against the pinned pretrained RLCard CFR reference.'
                : 'Trains the fixed T-9-6 two-tone flop abstraction. Positive cumulative regret is a diagnostic, not exploitability.'}
          </p>
          <Button onClick={() => void startTraining()} disabled={running}>
            <Play /> Start training
          </Button>
          {running && (
            <Button variant="outline" onClick={() => void cancelTraining()}>
              <Ban /> Cancel
            </Button>
          )}
        </aside>
        <article className="policy-progress-card">
          <div className="solver-card-heading">
            <div>
              <span className="eyebrow">Convergence</span>
              <h2>
                {trainingGame === 'kuhn-poker'
                  ? 'Exact exploitability'
                  : trainingGame === 'leduc-holdem'
                    ? 'Score versus reference policy'
                    : 'Positive cumulative regret'}
              </h2>
            </div>
            <span
              className={`solver-status solver-status-${job?.status ?? 'idle'}`}
            >
              {job?.status ?? 'idle'}
            </span>
          </div>
          {points.length ? (
            <ChartContainer
              className="policy-chart"
              config={{
                exploitability: { label: 'Exploitability', color: '#1b6b4f' },
                referenceScore: { label: 'Reference score', color: '#1b6b4f' },
                positiveRegret: { label: 'Positive regret', color: '#1b6b4f' },
              }}
            >
              <LineChart data={points} margin={{ left: 4, right: 12, top: 12 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="iteration" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} width={48} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Line
                  type="monotone"
                  dataKey={progressMetric}
                  stroke={`var(--color-${progressMetric})`}
                  strokeWidth={3}
                  dot={false}
                />
              </LineChart>
            </ChartContainer>
          ) : (
            <div className="policy-empty">
              Start a run to watch training progress.
            </div>
          )}
          <div className="training-progress-track">
            <span style={{ width: `${progressPercent}%` }} />
          </div>
          <div className="policy-metrics">
            <div>
              <span>Iteration</span>
              <strong>{currentIteration.toLocaleString()}</strong>
            </div>
            <div>
              <span>
                {trainingGame === 'kuhn-poker'
                  ? 'Exploitability'
                  : trainingGame === 'leduc-holdem'
                    ? 'Reference score'
                    : 'Positive regret'}
              </span>
              <strong>
                {trainingGame === 'kuhn-poker'
                  ? (latestProgress?.exploitability?.toFixed(5) ?? '—')
                  : trainingGame === 'leduc-holdem'
                    ? (latestProgress?.referenceScore?.toFixed(3) ?? '—')
                    : (latestProgress?.positiveRegret?.toFixed(2) ?? '—')}
              </strong>
            </div>
            <div>
              <span>
                {trainingGame === 'restricted-hu-nlhe-flop'
                  ? 'Information sets'
                  : 'Game value'}
              </span>
              <strong>
                {trainingGame === 'restricted-hu-nlhe-flop'
                  ? (latestProgress?.informationSets?.toLocaleString() ?? '—')
                  : (latestProgress?.gameValue?.toFixed(5) ?? '—')}
              </strong>
            </div>
            <div>
              <span>Iteration rate</span>
              <strong>
                {iterationRate !== null
                  ? `${iterationRate.toFixed(iterationRate >= 10 ? 0 : 1)}/s`
                  : '—'}
              </strong>
            </div>
            <div>
              <span>Elapsed</span>
              <strong>
                {latestProgress?.elapsedMs !== undefined
                  ? `${(latestProgress.elapsedMs / 1000).toFixed(2)}s`
                  : '—'}
              </strong>
            </div>
          </div>
          {job?.status === 'complete' && (
            <div className="checkpoint-actions">
              <Button variant="outline" onClick={() => void registerModel()}>
                <Plus /> Save as model
              </Button>
              <Button
                variant="outline"
                onClick={() => void downloadCheckpoint()}
              >
                <Database /> Download checkpoint
              </Button>
              <input
                aria-label="Resume through iteration"
                type="number"
                min={iterations + 1}
                value={resumeIterations}
                onChange={(event) =>
                  setResumeIterations(Number(event.target.value))
                }
              />
              <Button variant="outline" onClick={() => void resumeTraining()}>
                <RotateCcw /> Resume
              </Button>
            </div>
          )}
        </article>
        <aside className="policy-history-card">
          <span className="eyebrow">Persistent runs</span>
          <h2>Training history</h2>
          <div className="policy-history-list">
            {history.length ? (
              history.map((item) => (
                <button
                  key={item.jobId}
                  className={job?.jobId === item.jobId ? 'active' : ''}
                  onClick={() => void selectJob(item)}
                >
                  <span>
                    <b>{item.iterations.toLocaleString()} iterations</b>
                    <small>{item.mode}</small>
                  </span>
                  <i className={`solver-status solver-status-${item.status}`}>
                    {item.status}
                  </i>
                </button>
              ))
            ) : (
              <p>No runs yet. Your completed jobs will appear here.</p>
            )}
          </div>
          {strategy.length > 0 && (
            <div className="policy-strategy-preview">
              <span className="eyebrow">Final policy sample</span>
              {strategy.slice(0, 6).map((node) => (
                <div key={node.informationSet}>
                  <b>{node.informationSet}</b>
                  <span>
                    {(
                      (node.actions[
                        job?.game === 'leduc-holdem'
                          ? 'raise'
                          : job?.game === 'restricted-hu-nlhe-flop'
                            ? 'bet-50'
                            : 'bet'
                      ] ?? 0) * 100
                    ).toFixed(1)}
                    % {job?.game === 'leduc-holdem' ? 'raise' : job?.game === 'restricted-hu-nlhe-flop' ? 'half-pot bet' : 'bet'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
      <article className="model-registry-card">
        <div className="model-registry-heading">
          <div>
            <span className="eyebrow">Model registry</span>
            <h2>Compare saved policies</h2>
            <p>
              Lower exploitability is better. Kuhn’s equilibrium value is
              approximately −0.05556 for the first player.
            </p>
          </div>
          <div className="model-comparison-selectors">
            <Select
              value={leftModelId}
              onValueChange={(modelId) => {
                setLeftModelId(modelId);
                const game = models.find(
                  (model) => model.modelId === modelId,
                )?.game;
                const compatible = models.find((model) => model.game === game);
                if (
                  !models.some(
                    (model) =>
                      model.modelId === rightModelId && model.game === game,
                  )
                ) {
                  setRightModelId(compatible?.modelId ?? '');
                }
              }}
            >
              <SelectTrigger aria-label="First policy">
                <SelectValue placeholder="First policy" />
              </SelectTrigger>
              <SelectContent>
                {models
                  .filter(
                    (model) => !leftModel || model.game === leftModel.game,
                  )
                  .map((model) => (
                    <SelectItem key={model.modelId} value={model.modelId}>
                      {model.name}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
            <span>versus</span>
            <Select value={rightModelId} onValueChange={setRightModelId}>
              <SelectTrigger aria-label="Second policy">
                <SelectValue placeholder="Second policy" />
              </SelectTrigger>
              <SelectContent>
                {models.map((model) => (
                  <SelectItem key={model.modelId} value={model.modelId}>
                    {model.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        {leftModel && rightModel ? (
          <div className="model-comparison-grid">
            <ModelScoreCard model={leftModel} />
            <div className="model-policy-table">
              <div className="model-policy-header">
                <span>Information set</span>
                <span>{leftModel.name}</span>
                <span>{rightModel.name}</span>
                <span>Difference</span>
              </div>
              {comparisonRows.map((row) => (
                <div key={row.informationSet}>
                  <b title={row.informationSet}>{row.label}</b>
                  <span>
                    {(row.left * 100).toFixed(1)}% {aggressiveAction}
                  </span>
                  <span>
                    {(row.right * 100).toFixed(1)}% {aggressiveAction}
                  </span>
                  <i>{(Math.abs(row.left - row.right) * 100).toFixed(1)} pp</i>
                </div>
              ))}
            </div>
            <ModelScoreCard model={rightModel} />
          </div>
        ) : (
          <div className="model-registry-empty">
            Complete a training run and save it as a model to begin comparing
            policies.
          </div>
        )}
      </article>
    </div>
  );
}

function ModelScoreCard({ model }: { model: TrainingModel }) {
  return (
    <div className="model-score-card">
      <strong>{model.name}</strong>
      <dl>
        <div>
          <dt>{model.game === 'kuhn-poker' ? 'Exploitability' : 'Game'}</dt>
          <dd>
            {model.exploitability !== undefined
              ? model.exploitability.toFixed(5)
              : '—'}
          </dd>
        </div>
        <div>
          <dt>
            {model.game === 'kuhn-poker' ? 'Game value' : 'Reference score'}
          </dt>
          <dd>
            {model.gameValue !== undefined
              ? model.gameValue.toFixed(5)
              : (model.referenceScore?.toFixed(3) ?? '—')}
          </dd>
        </div>
        <div>
          <dt>Iterations</dt>
          <dd>{model.iterations.toLocaleString()}</dd>
        </div>
      </dl>
    </div>
  );
}

function HumanTrainingIntro() {
  return (
    <section className="human-training-workspace">
      <div className="human-training-heading">
        <span className="eyebrow">Human Training</span>
        <h1>Practice the decision before seeing the answer</h1>
        <p>
          This workspace will turn the reproducible solver spots into private
          decision drills. Model development and convergence tooling remain in
          Model Training.
        </p>
      </div>
      <div className="human-training-modes">
        <article>
          <span className="training-mode-number">01</span>
          <div>
            <h2>Generated situations</h2>
            <p>
              Work through curated or seeded-random spots, commit to an action,
              then reveal the mixed strategy and explanation.
            </p>
          </div>
          <small>Next milestone</small>
        </article>
        <article>
          <span className="training-mode-number">02</span>
          <div>
            <h2>Situation Lab</h2>
            <p>
              Enter cards and game state manually, then inspect ranges, equity,
              compatible model predictions, and solver analysis.
            </p>
          </div>
          <small>Roadmap</small>
        </article>
      </div>
      <div className="human-training-sequence">
        <span>Choose a spot</span>
        <i />
        <span>Make a decision</span>
        <i />
        <span>Reveal analysis</span>
        <i />
        <span>Track improvement</span>
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
    [mode, setMode] = useState<
      'play' | 'review' | 'human-training' | 'model-training'
    >('play');
  const [history, setHistory] = useState<HistoryItem[]>([]),
    [review, setReview] = useState<HistoryDetail | null>(null),
    [reviewStep, setReviewStep] = useState(0);
  const [raiseAmount, setRaiseAmount] = useState<number | null>(null),
    [showAllStrategy, setShowAllStrategy] = useState(false);
  const [highlightBestFive, setHighlightBestFive] = useState(true);
  const [showStrategy, setShowStrategy] = useState(true);
  const [useEstimatedRange, setUseEstimatedRange] = useState(false);
  const [showVillainRange, setShowVillainRange] = useState(false);
  const [expandVillainRange, setExpandVillainRange] = useState(false);
  const [actionAnimation, setActionAnimation] = useState<{
    id: number;
    action: ActionRecord;
  } | null>(null);
  const [equityState, setEquityState] = useState<{
    key: string;
    result: EquityResult;
  } | null>(null);
  const [villainRangeState, setVillainRangeState] = useState<{
    key: string;
    result: VillainRange;
  } | null>(null);
  const [handChanceState, setHandChanceState] = useState<{
    key: string;
    result: HandChances;
  } | null>(null);
  const initialized = useRef(false);
  const animationMarker = useRef({ sessionId: '', actionCount: 0 });
  const animationQueue = useRef<ActionRecord[]>([]);
  const animationActive = useRef(false);
  const animationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const animationId = useRef(0);
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
  useEffect(() => {
    if (mode !== 'play' || !hand || !observation) return;
    const marker = animationMarker.current;
    if (marker.sessionId !== hand.sessionId) {
      marker.sessionId = hand.sessionId;
      marker.actionCount = Math.min(2, observation.actions.length);
      animationQueue.current = [];
      animationActive.current = false;
      setActionAnimation(null);
      if (animationTimer.current) clearTimeout(animationTimer.current);
    }
    const newActions = observation.actions
      .slice(marker.actionCount)
      .filter((action) =>
        ['check', 'call', 'raise-to', 'fold'].includes(action.type),
      );
    marker.actionCount = observation.actions.length;
    animationQueue.current.push(...newActions);
    if (animationActive.current || !animationQueue.current.length) return;

    const playNext = () => {
      const action = animationQueue.current.shift();
      if (!action) {
        animationActive.current = false;
        setActionAnimation(null);
        return;
      }
      animationActive.current = true;
      setActionAnimation({ id: ++animationId.current, action });
      animationTimer.current = setTimeout(() => {
        setActionAnimation(null);
        animationTimer.current = setTimeout(playNext, 100);
      }, 1600);
    };
    playNext();
  }, [hand, mode, observation]);
  useEffect(
    () => () => {
      if (animationTimer.current) clearTimeout(animationTimer.current);
    },
    [],
  );
  const equityRequest = useMemo(
    () =>
      observation?.holeCards.length
        ? {
            key: `${observation.holeCards.join(',')}|${observation.board.join(',')}|${observation.actions.map((action) => `${action.seat}:${action.street}:${action.type}:${action.amount}`).join(';')}`,
            holeCards: observation.holeCards,
            board: observation.board,
            actions: observation.actions,
          }
        : null,
    [observation],
  );
  useEffect(() => {
    if (!equityRequest) return;
    let cancelled = false;
    request<VillainRange>('/v1/villain-range', {
      method: 'POST',
      body: JSON.stringify({
        holeCards: equityRequest.holeCards,
        board: equityRequest.board,
        actions: equityRequest.actions,
      }),
    })
      .then((result) => {
        if (!cancelled)
          setVillainRangeState({ key: equityRequest.key, result });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [equityRequest, request]);
  const villainRange =
    villainRangeState && villainRangeState.key === equityRequest?.key
      ? villainRangeState.result
      : null;
  useEffect(() => {
    if (!equityRequest) return;
    let cancelled = false;
    request<EquityResult>('/v1/equity', {
      method: 'POST',
      body: JSON.stringify({
        holeCards: equityRequest.holeCards,
        board: equityRequest.board,
        ...(useEstimatedRange && villainRange
          ? { opponentWeights: villainRange.combos }
          : {}),
      }),
    })
      .then((result) => {
        if (!cancelled) setEquityState({ key: equityRequest.key, result });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [equityRequest, request, useEstimatedRange, villainRange]);
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
  const opponentCards = terminal
    ? observation?.result?.revealedHoleCards?.[1]
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
            <TrainFront className="size-5" strokeWidth={1.8} />
          </span>
          <div>
            <p className="brand-name">game train</p>
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
            className={`mode-pill ${mode === 'human-training' ? 'mode-pill-active' : ''}`}
            onClick={() => setMode('human-training')}
          >
            Human Training
          </button>
          <button
            className={`mode-pill ${mode === 'model-training' ? 'mode-pill-active' : ''}`}
            onClick={() => setMode('model-training')}
          >
            Model Training
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
      {mode === 'model-training' ? (
        <SolverLab request={request} />
      ) : mode === 'human-training' ? (
        <HumanTrainingIntro />
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
            <p className="chance-title">Chance by river · exact final hand</p>
            <div className="villain-possibility-key">
              <i /> Possible for Villain by river
            </div>
            <ol>
              {HAND_RANKS.map(([id, label], index) => (
                <li
                  key={id}
                  className={[
                    highlightBestFive && observation?.handCategory === id
                      ? 'rank-active'
                      : '',
                    handChances &&
                    (handChances.exact[id] ?? 0) >
                      (handChances.percentile75Exact[id] ?? 0)
                      ? 'rank-above-baseline'
                      : '',
                    handChances &&
                    currentRankIndex >= 0 &&
                    index < currentRankIndex &&
                    (handChances.exact[id] ?? 0) < 0.01
                      ? 'rank-low-probability'
                      : '',
                  ].join(' ')}
                >
                  <span>{index + 1}</span>
                    <b>{label}</b>
                  {handChances &&
                    index <= 4 &&
                    (handChances.baselineExact[id] ?? 0) > 0 && (
                    <i
                      className="rank-villain-possible"
                      title={`A legal Villain hand can finish as ${label.toLowerCase()} by the river`}
                      aria-label={`Possible for Villain by the river: ${label}`}
                    />
                  )}
                  {currentRankIndex >= 0 && index < currentRankIndex && (
                    <em>
                      {observation?.board.length === 3 ||
                      observation?.board.length === 4 ? (
                        <span>
                          {handChances?.combinations[id] ?? '…'} combos
                        </span>
                      ) : null}
                      {handChances
                        ? chanceLabel(handChances.exact[id] ?? 0)
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
                {' · '}Gold tint = above {handChances.baselineLabel}
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
                {actionAnimation && actionAnimation.action.type !== 'fold' && (
                  <div
                    key={actionAnimation.id}
                    className={`chip-action-animation${actionAnimation.action.type === 'check' ? ' check-action-animation' : ''} ${actionAnimation.action.seat === 0 ? 'action-from-hero' : 'action-from-villain'}`}
                    aria-hidden="true"
                  >
                    {actionAnimation.action.type !== 'check' && (
                      <>
                        <span />
                        <span />
                        <span />
                      </>
                    )}
                    <b>
                      {actionAnimation.action.type === 'call'
                        ? 'Call'
                        : actionAnimation.action.type === 'check'
                          ? 'Check'
                          : 'Raise'}{' '}
                      {actionAnimation.action.type !== 'check' &&
                        chips(actionAnimation.action.amount)}
                    </b>
                  </div>
                )}
                {actionAnimation?.action.type === 'fold' && (
                  <div
                    key={actionAnimation.id}
                    className={`fold-action-animation ${actionAnimation.action.seat === 0 ? 'action-from-hero' : 'action-from-villain'}`}
                    aria-hidden="true"
                  >
                    <span>GT</span>
                    <span>GT</span>
                    <b>Fold</b>
                  </div>
                )}
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
                <span className="eyebrow">
                  Equity vs{' '}
                  {useEstimatedRange ? 'estimated range' : 'random hand'}
                </span>
                <strong>
                  {equity
                    ? `${(equity.equity * 100).toFixed(1)}%`
                    : equityRequest
                      ? 'Calculating…'
                      : 'Unavailable'}
                </strong>
              </div>
              <div className="range-equity-toggle">
                <span>Use Villain behavior</span>
                <Switch
                  size="sm"
                  checked={useEstimatedRange}
                  disabled={!villainRange}
                  onCheckedChange={setUseEstimatedRange}
                  aria-label="Use estimated Villain range for equity"
                />
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
              {villainRange && (
                <div className="villain-range-summary">
                  <div
                    className={`range-flip-card${showVillainRange ? ' is-flipped' : ''}${expandVillainRange ? ' is-expanded' : ''}`}
                    onClick={(event) => {
                      if (expandVillainRange && event.target === event.currentTarget) {
                        setExpandVillainRange(false);
                      }
                    }}
                  >
                    <div
                      className="range-flip-inner"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <button
                        type="button"
                        className="range-flip-face range-flip-front"
                        onClick={() => setShowVillainRange(true)}
                        aria-label="Reveal estimated Villain range matrix"
                        aria-hidden={showVillainRange}
                        tabIndex={showVillainRange ? -1 : 0}
                      >
                        <span className="eyebrow">Estimated Villain range</span>
                        <strong>{villainRange.effectiveCombos80}</strong>
                        <b>combos cover 80%</b>
                        <div className="range-class-list">
                          {villainRange.topClasses.slice(0, 4).map((item) => (
                            <span key={item.handClass}>{item.handClass}</span>
                          ))}
                        </div>
                        <small>Flip to view range</small>
                      </button>
                      <div
                        className="range-flip-face range-flip-back"
                        aria-hidden={!showVillainRange}
                      >
                        <div className="range-flip-heading">
                          <span>Villain range</span>
                          <div>
                            <button
                              type="button"
                              onClick={() => setExpandVillainRange((expanded) => !expanded)}
                              tabIndex={showVillainRange ? 0 : -1}
                            >
                              {expandVillainRange ? 'Minimize' : 'Expand'}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setShowVillainRange(false);
                                setExpandVillainRange(false);
                              }}
                              tabIndex={showVillainRange ? 0 : -1}
                            >
                              Flip back
                            </button>
                          </div>
                        </div>
                        <VillainRangeMatrix
                          range={villainRange}
                          heroCards={observation?.holeCards ?? []}
                        />
                        <div className="range-matrix-legend" aria-label="Range matrix legend">
                          <span><i className="equity-low" /> Low equity</span>
                          <span><i className="equity-high" /> High equity</span>
                          <span><i className="villain-likely" /> Villain range</span>
                          <span><i className="hero-hand" /> You</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </section>
          </aside>
        </section>
      )}
    </main>
  );
}
