'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  Beer,
  Check,
  ChevronDown,
  CircleDot,
  Eye,
  EyeOff,
  Gauge,
  Lightbulb,
  RotateCcw,
  Settings2,
  Trophy,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GameTitleSelector } from '@/platform/game-title-selector';
import {
  applyMoveSequence,
  createInitialBackgammonState,
  legalMoveSequences,
  type BackgammonMove,
  type BackgammonDestination,
  type BackgammonPlayer,
  type BackgammonPoint,
  type BackgammonState,
} from './runtime/backgammon-engine';
import {
  evaluateWildBgState,
  rankWithWildBg,
  warmWildBg,
  type WildBgEvaluation,
  type WildBgPositionEvaluation,
} from './runtime/wildbg';

// Conventional board orientation: the opponent's outer/home boards run across
// the top, while our points return from 12 to 1 across the bottom.
const DISPLAY_POINTS = [
  13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 12, 11, 10, 9, 8, 7, 6, 5, 4,
  3, 2, 1,
];

function rollDice() {
  return [1 + Math.floor(Math.random() * 6), 1 + Math.floor(Math.random() * 6)];
}

function pipCount(state: BackgammonState, player: BackgammonPlayer) {
  return state.points.reduce((total, value, index) => {
    const owns = player === 0 ? value > 0 : value < 0;
    if (!owns) return total;
    const distance = player === 0 ? index + 1 : 24 - index;
    return total + Math.abs(value) * distance;
  }, state.bar[player] * 25);
}

function moveLabel(move: BackgammonMove) {
  return `${move.from === 'bar' ? 'Bar' : move.from}/${move.to === 'off' ? 'Off' : move.to}${move.hit ? '*' : ''}`;
}

function sequenceLabel(sequence: BackgammonMove[]) {
  return sequence.length
    ? sequence.map(moveLabel).join(' · ')
    : 'No legal move';
}

function sameMove(left: BackgammonMove, right: BackgammonMove) {
  return (
    left.from === right.from &&
    left.to === right.to &&
    left.die === right.die &&
    left.hit === right.hit
  );
}

function uniqueFirstMoves(sequences: BackgammonMove[][]) {
  const unique = new Map<string, BackgammonMove>();
  sequences.forEach(([move]) => {
    if (move) unique.set(moveLabel(move), move);
  });
  return [...unique.values()];
}

function scoreSequence(state: BackgammonState, sequence: BackgammonMove[]) {
  const after = applyMoveSequence(state, sequence);
  const player = state.turn;
  const rival = player === 0 ? 1 : 0;
  return (
    pipCount(state, player) -
    pipCount(after, player) +
    sequence.filter((move) => move.hit).length * 8 +
    (after.off[player] - state.off[player]) * 12 -
    after.bar[player] * 10 +
    after.bar[rival] * 4
  );
}

function rankedSequences(state: BackgammonState) {
  const uniqueByOutcome = new Map<string, BackgammonMove[]>();
  legalMoveSequences(state).forEach((sequence) => {
    const after = applyMoveSequence(state, sequence);
    const key = JSON.stringify([
      after.points,
      after.bar,
      after.off,
      after.winner,
    ]);
    if (!uniqueByOutcome.has(key)) uniqueByOutcome.set(key, sequence);
  });
  return [...uniqueByOutcome.values()]
    .map((sequence) => ({ sequence, score: scoreSequence(state, sequence) }))
    .sort((left, right) => right.score - left.score);
}

const DIE_PIPS: Record<number, number[]> = {
  1: [5],
  2: [1, 9],
  3: [1, 5, 9],
  4: [1, 3, 7, 9],
  5: [1, 3, 5, 7, 9],
  6: [1, 3, 4, 6, 7, 9],
};

function DieFace({ value }: { value: number }) {
  const pips = new Set(DIE_PIPS[value] ?? DIE_PIPS[5]);
  return (
    <i className="die-face" aria-label={`${value}`}>
      {Array.from({ length: 9 }, (_, index) => (
        <b className={pips.has(index + 1) ? 'pip-visible' : ''} key={index} />
      ))}
    </i>
  );
}

function nextTurn(state: BackgammonState): BackgammonState {
  if (state.winner !== null) return { ...state, dice: [] };
  return {
    ...state,
    turn: state.turn === 0 ? 1 : 0,
    dice: [],
    moveNumber: state.moveNumber + 1,
  };
}

function boardCoordinates(
  point: BackgammonPoint | BackgammonDestination,
  player: BackgammonPlayer,
) {
  if (point === 'bar') return { x: 17.5, y: 110 };
  if (point === 'off') return { x: player === 0 ? 84 : 52, y: 110 };
  const index = DISPLAY_POINTS.indexOf(point);
  return {
    x: ((index % 12) + 0.5) * (100 / 12),
    y: index < 12 ? 9 : 91,
  };
}

function stackCoordinates(
  state: BackgammonState,
  point: BackgammonPoint | BackgammonDestination,
  player: BackgammonPlayer,
  landing = false,
) {
  if (point === 'bar' || point === 'off')
    return boardCoordinates(point, player);
  const index = DISPLAY_POINTS.indexOf(point);
  const value = state.points[point - 1];
  const ownsPoint = player === 0 ? value > 0 : value < 0;
  const checkerCount = Math.min(
    5,
    (ownsPoint ? Math.abs(value) : 0) + (landing ? 1 : 0),
  );
  const offset = Math.max(0, checkerCount - 1) * 6.8;
  return {
    x: ((index % 12) + 0.5) * (100 / 12),
    y: index < 12 ? 5.5 + offset : 94.5 - offset,
  };
}

function BackgammonBoard({
  state,
  preview,
  animatedMove,
  rolling,
  selectableMoves,
  selectedOrigin,
  onPointClick,
  onRoll,
  canRoll,
  message,
  shownDice,
  onPlayAgain,
}: {
  state: BackgammonState;
  preview: BackgammonMove[] | null;
  animatedMove: { move: BackgammonMove; player: BackgammonPlayer } | null;
  rolling: boolean;
  selectableMoves: BackgammonMove[];
  selectedOrigin: BackgammonPoint | null;
  onPointClick: (point: BackgammonPoint | BackgammonDestination) => void;
  onRoll: () => void;
  canRoll: boolean;
  message: string;
  shownDice: { player: BackgammonPlayer; values: number[] } | null;
  onPlayAgain: () => void;
}) {
  const selectableOrigins = new Set(selectableMoves.map((move) => move.from));
  const selectableDestinations = new Set(
    selectableMoves
      .filter((move) => selectedOrigin !== null && move.from === selectedOrigin)
      .map((move) => move.to),
  );
  const previewOrigins = new Set(preview?.map((move) => move.from) ?? []);
  const previewSourceCounts = new Map<BackgammonPoint, number>();
  preview?.forEach((move) => {
    if (move.from !== 'bar') {
      previewSourceCounts.set(
        move.from,
        (previewSourceCounts.get(move.from) ?? 0) + 1,
      );
    }
  });
  const previewSteps: Array<{
    move: BackgammonMove;
    from: { x: number; y: number };
    to: { x: number; y: number };
  }> = [];
  let previewState = state;
  preview?.forEach((move) => {
    const from = stackCoordinates(previewState, move.from, state.turn);
    const after = applyMoveSequence(previewState, [move]);
    const to = stackCoordinates(after, move.to, state.turn);
    previewSteps.push({ move, from, to });
    previewState = after;
  });
  return (
    <div className="backgammon-board-shell">
      <div className="backgammon-board" aria-label="Backgammon board">
        <div className="backgammon-surface">
          <div className="backgammon-points">
            {DISPLAY_POINTS.map((point) => {
              const value = state.points[point - 1];
              const checkers = value
                ? {
                    owner: value > 0 ? ('cream' as const) : ('ink' as const),
                    count: Math.abs(value),
                  }
                : null;
              return (
                <div
                  className={`backgammon-point point-${point}${selectableOrigins.has(point) ? ' point-selectable-origin' : ''}${selectedOrigin === point ? ' point-selected-origin' : ''}${selectableDestinations.has(point) ? ' point-selectable-destination' : ''}${previewOrigins.has(point) ? ' point-preview-origin' : ''}${animatedMove?.move.from === point ? ' point-moving-origin' : ''}`}
                  key={point}
                  aria-label={`Point ${point}${checkers ? `, ${checkers.count} ${checkers.owner} checker${checkers.count === 1 ? '' : 's'}` : ', empty'}`}
                >
                  <span className="point-number">{point}</span>
                  {checkers && (
                    <span className={`checker-stack checker-${checkers.owner}`}>
                      {Array.from(
                        { length: Math.min(checkers.count, 5) },
                        (_, index) => {
                          const renderedCheckerCount = Math.min(
                            checkers.count,
                            5,
                          );
                          const previewedFromStack = Math.min(
                            previewSourceCounts.get(point) ?? 0,
                            renderedCheckerCount,
                          );
                          const isPreviewSource =
                            index >= renderedCheckerCount - previewedFromStack;
                          return (
                            <i
                              className={
                                isPreviewSource
                                  ? 'preview-source-checker'
                                  : undefined
                              }
                              key={index}
                            />
                          );
                        },
                      )}
                      {checkers.count > 5 && <b>{checkers.count}</b>}
                    </span>
                  )}
                  {(selectableOrigins.has(point) ||
                    selectableDestinations.has(point)) && (
                    <button
                      className="backgammon-point-target"
                      onClick={() => onPointClick(point)}
                      aria-label={
                        selectableDestinations.has(point)
                          ? `Move checker to point ${point}`
                          : `Select checker on point ${point}`
                      }
                    />
                  )}
                </div>
              );
            })}
          </div>
          <div className="backgammon-bar">
            <span>BAR</span>
          </div>
          {preview && (
            <svg
              className="backgammon-move-preview"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <defs>
                <marker
                  id="preview-arrow"
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="4"
                  markerHeight="4"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" />
                </marker>
              </defs>
              {previewSteps.map(({ move, from, to }, index) => {
                return (
                  <g key={`${moveLabel(move)}-${index}`}>
                    <line
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      markerEnd="url(#preview-arrow)"
                    />
                  </g>
                );
              })}
            </svg>
          )}
          {previewSteps.map(({ move, to }, index) => (
            <i
              className="backgammon-preview-checker preview-cream"
              key={`ghost-${moveLabel(move)}-${index}`}
              style={{ left: `${to.x}%`, top: `${to.y}%` }}
            />
          ))}
          {animatedMove &&
            (() => {
              const from = stackCoordinates(
                state,
                animatedMove.move.from,
                animatedMove.player,
              );
              const after = applyMoveSequence(state, [animatedMove.move]);
              const to = stackCoordinates(
                after,
                animatedMove.move.to,
                animatedMove.player,
              );
              return (
                <i
                  className={`backgammon-flying-checker ${animatedMove.player === 0 ? 'flying-cream' : 'flying-ink'}`}
                  style={
                    {
                      '--move-from-x': `${from.x}%`,
                      '--move-from-y': `${from.y}%`,
                      '--move-to-x': `${to.x}%`,
                      '--move-to-y': `${to.y}%`,
                    } as CSSProperties
                  }
                />
              );
            })()}
          {(rolling || shownDice) && (
            <span
              className={`board-dice board-dice-player-${rolling ? state.turn : (shownDice?.player ?? 0)} ${rolling ? 'board-dice-rolling' : ''}`}
            >
              {(rolling ? [5, 3] : (shownDice?.values ?? [])).map(
                (die, index) => (
                  <DieFace key={index} value={die} />
                ),
              )}
            </span>
          )}
          {canRoll && !rolling && !state.dice.length && (
            <button className="board-roll-button" onClick={onRoll}>
              <Gauge /> Roll dice
            </button>
          )}
          <p className="sr-only" aria-live="polite">
            {message}
          </p>
          {state.winner !== null && (
            <div
              className="backgammon-game-over"
              role="dialog"
              aria-modal="true"
            >
              <Trophy aria-hidden="true" />
              <span>Game over</span>
              <h2>{state.winner === 0 ? 'You won!' : 'Ink won'}</h2>
              <p>
                {state.winner === 0
                  ? 'All fifteen cream checkers made it home.'
                  : 'Ink bore off all fifteen checkers first.'}
              </p>
              <Button onClick={onPlayAgain}>Play again</Button>
            </div>
          )}
        </div>
      </div>
      <div className="backgammon-utility-row">
        <div className="checker-jail">
          <span className="utility-label">The Bar</span>
          <span className="jailed-checkers">
            {state.bar[1] > 0 && (
              <span className="jailed-checker-team">
                {Array.from(
                  { length: Math.min(state.bar[1], 3) },
                  (_, index) => (
                    <i className="utility-checker checker-ink" key={index}>
                      <Beer aria-hidden="true" />
                      {index === 2 && state.bar[1] > 3 && (
                        <b>+{state.bar[1] - 3}</b>
                      )}
                    </i>
                  ),
                )}
              </span>
            )}
            {state.bar[0] > 0 && (
              <span className="jailed-checker-team">
                {Array.from(
                  { length: Math.min(state.bar[0], 3) },
                  (_, index) => (
                    <i className="utility-checker checker-cream" key={index}>
                      <Beer aria-hidden="true" />
                      {index === 2 && state.bar[0] > 3 && (
                        <b>+{state.bar[0] - 3}</b>
                      )}
                    </i>
                  ),
                )}
              </span>
            )}
          </span>
          {selectableOrigins.has('bar') && (
            <button
              className={`jail-select-target${selectedOrigin === 'bar' ? ' jail-selected' : ''}`}
              onClick={() => onPointClick('bar')}
              aria-label="Select checker on the bar"
            />
          )}
        </div>
        <div className="bear-off-return">
          <span className="utility-label">Return tray</span>
          <div className="return-lane return-lane-ink">
            <span>Ink</span>
            <b>{state.off[1]}</b>
            <em>
              {Array.from({ length: state.off[1] }, (_, index) => (
                <i key={index} />
              ))}
            </em>
          </div>
          <div className="return-lane return-lane-cream">
            <span>You</span>
            <b>{state.off[0]}</b>
            <em>
              {Array.from({ length: state.off[0] }, (_, index) => (
                <i key={index} />
              ))}
            </em>
          </div>
          {selectableDestinations.has('off') && (
            <button
              className="bear-off-target"
              onClick={() => onPointClick('off')}
              aria-label="Bear off selected checker"
            >
              Bear off
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function BackgammonClient() {
  const [state, setState] = useState(createInitialBackgammonState);
  const [message, setMessage] = useState(
    'Roll to begin. You move toward point 1.',
  );
  const [thinking, setThinking] = useState(false);
  const [rolling, setRolling] = useState(false);
  const [shownDice, setShownDice] = useState<{
    player: BackgammonPlayer;
    values: number[];
  } | null>(null);
  const [preview, setPreview] = useState<BackgammonMove[] | null>(null);
  const [manualOptions, setManualOptions] = useState<BackgammonMove[][]>([]);
  const [manualMode, setManualMode] = useState(false);
  const [selectedOrigin, setSelectedOrigin] = useState<BackgammonPoint | null>(
    null,
  );
  const [animatedMove, setAnimatedMove] = useState<{
    move: BackgammonMove;
    player: BackgammonPlayer;
  } | null>(null);
  const [engineStatus, setEngineStatus] = useState<
    'loading' | 'ready' | 'fallback'
  >('loading');
  const [wildChoices, setWildChoices] = useState<WildBgEvaluation[] | null>(
    null,
  );
  const [positionEval, setPositionEval] =
    useState<WildBgPositionEvaluation | null>(null);
  const [evalHistory, setEvalHistory] = useState<
    Array<{ move: number; equity: number; winChance: number }>
  >([]);
  const [adviceEnabled, setAdviceEnabled] = useState(true);
  const [evalExpanded, setEvalExpanded] = useState(false);
  const [adviceExpanded, setAdviceExpanded] = useState(false);
  const [touchAdvice, setTouchAdvice] = useState(false);
  const [selectedAdviceIndex, setSelectedAdviceIndex] = useState<number | null>(
    null,
  );
  const botTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heuristicChoices = useMemo(() => rankedSequences(state), [state]);
  const choices = manualMode
    ? []
    : (wildChoices ?? (engineStatus === 'fallback' ? heuristicChoices : []));
  const selectableMoves = uniqueFirstMoves(manualOptions);
  const phase =
    state.off[0] + state.off[1] > 0
      ? 'Bear-off'
      : state.bar[0] + state.bar[1] > 0
        ? 'Hit race'
        : 'Contact';
  const evalPercent = positionEval
    ? Math.max(0, Math.min(100, ((positionEval.equity + 3) / 6) * 100))
    : 50;
  const chartPoints = evalHistory.length
    ? evalHistory
        .map((entry, index) => {
          const x =
            evalHistory.length === 1
              ? 50
              : (index / (evalHistory.length - 1)) * 100;
          const y = 50 - Math.max(-3, Math.min(3, entry.equity)) * (42 / 3);
          return `${x},${y}`;
        })
        .join(' ')
    : '0,50 100,50';
  const latestChartPoint = evalHistory.length
    ? {
        x: evalHistory.length === 1 ? 50 : 100,
        y:
          50 -
          Math.max(
            -3,
            Math.min(3, evalHistory[evalHistory.length - 1].equity),
          ) *
            (42 / 3),
      }
    : null;

  useEffect(
    () => () => {
      if (botTimer.current) clearTimeout(botTimer.current);
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    warmWildBg()
      .then(() => {
        if (!cancelled) setEngineStatus('ready');
      })
      .catch((error) => {
        console.error('WildBG failed to load', error);
        if (!cancelled) setEngineStatus('fallback');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const media = window.matchMedia('(pointer: coarse), (max-width: 700px)');
    const update = () => setTouchAdvice(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setWildChoices(null);
    if (
      thinking ||
      manualMode ||
      state.turn !== 0 ||
      !state.dice.length ||
      state.winner !== null
    ) {
      return () => {
        cancelled = true;
      };
    }
    const sequences = legalMoveSequences(state);
    rankWithWildBg(state, sequences)
      .then((ranked) => {
        if (!cancelled) {
          setWildChoices(ranked);
          setEngineStatus('ready');
        }
      })
      .catch((error) => {
        console.error('WildBG failed to rank moves', error);
        if (!cancelled) setEngineStatus('fallback');
      });
    return () => {
      cancelled = true;
    };
  }, [state, thinking, manualMode]);

  useEffect(() => {
    let cancelled = false;
    const evaluatedMove = state.moveNumber;
    evaluateWildBgState(state, 0)
      .then((evaluation) => {
        if (!cancelled) {
          setPositionEval(evaluation);
          setEvalHistory((history) => {
            const entry = {
              move: evaluatedMove,
              equity: evaluation.equity,
              winChance: evaluation.winChance,
            };
            const existing = history.findIndex(
              (item) => item.move === evaluatedMove,
            );
            if (existing === -1) return [...history, entry];
            const next = [...history];
            next[existing] = entry;
            return next;
          });
        }
      })
      .catch(() => {
        if (!cancelled) setPositionEval(null);
      });
    return () => {
      cancelled = true;
    };
  }, [state]);

  async function pause(milliseconds: number) {
    await new Promise((resolve) => setTimeout(resolve, milliseconds));
  }

  async function animateSequence(
    start: BackgammonState,
    sequence: BackgammonMove[],
  ) {
    let current = start;
    for (const move of sequence) {
      setAnimatedMove({ move, player: current.turn });
      await pause(420);
      current = applyMoveSequence(current, [move]);
      setState(current);
      setAnimatedMove(null);
      await pause(90);
    }
    return current;
  }

  function resetGame() {
    if (botTimer.current) clearTimeout(botTimer.current);
    setState(createInitialBackgammonState());
    setWildChoices(null);
    setPreview(null);
    setManualOptions([]);
    setManualMode(false);
    setSelectedOrigin(null);
    setAnimatedMove(null);
    setRolling(false);
    setShownDice(null);
    setThinking(false);
    setPositionEval(null);
    setEvalHistory([]);
    setSelectedAdviceIndex(null);
    setMessage('Roll to begin. You move toward point 1.');
  }

  function runBot(start: BackgammonState) {
    setThinking(true);
    setMessage('Ink is rolling…');
    botTimer.current = setTimeout(async () => {
      setRolling(true);
      await pause(700);
      const rolled = { ...start, dice: rollDice() };
      setState(rolled);
      setShownDice({ player: 1, values: rolled.dice });
      setRolling(false);
      let ranked: Array<{ sequence: BackgammonMove[] }>;
      try {
        ranked = await rankWithWildBg(rolled, legalMoveSequences(rolled));
        setEngineStatus('ready');
      } catch (error) {
        console.error('WildBG bot evaluation failed', error);
        ranked = rankedSequences(rolled);
        setEngineStatus('fallback');
      }
      const chosen = ranked[0]?.sequence ?? [];
      const moved = await animateSequence(rolled, chosen);
      const finished = nextTurn(moved);
      setState(finished);
      setManualOptions([]);
      setManualMode(false);
      setSelectedOrigin(null);
      setThinking(false);
      setMessage(
        moved.winner === 1
          ? 'Ink wins the game.'
          : `Ink rolled ${rolled.dice.join('–')} and played ${sequenceLabel(chosen)}. Your turn.`,
      );
    }, 900);
  }

  async function handleRoll() {
    if (
      state.turn !== 0 ||
      state.dice.length ||
      state.winner !== null ||
      thinking
    )
      return;
    setRolling(true);
    setMessage('Rolling…');
    await pause(700);
    const dice = rollDice();
    const rolled = { ...state, dice };
    const legal = legalMoveSequences(rolled);
    setState(rolled);
    setShownDice({ player: 0, values: dice });
    setManualOptions(legal);
    setManualMode(false);
    setSelectedOrigin(null);
    setRolling(false);
    setMessage(
      legal[0]?.length
        ? `You rolled ${dice.join('–')}. Choose a complete legal move.`
        : `You rolled ${dice.join('–')}, but cannot move.`,
    );
    if (!legal[0]?.length) {
      botTimer.current = setTimeout(() => {
        const passed = nextTurn(rolled);
        setState(passed);
        runBot(passed);
      }, 700);
    }
  }

  async function playSequence(sequence: BackgammonMove[]) {
    if (state.turn !== 0 || !state.dice.length || thinking) return;
    setPreview(null);
    setSelectedAdviceIndex(null);
    setManualOptions([]);
    setSelectedOrigin(null);
    setThinking(true);
    const moved = await animateSequence(state, sequence);
    const finished = nextTurn(moved);
    setState(finished);
    setThinking(false);
    setMessage(
      moved.winner === 0
        ? 'You win the game.'
        : `You played ${sequenceLabel(sequence)}.`,
    );
    if (moved.winner === null) runBot(finished);
  }

  async function playManualMove(move: BackgammonMove) {
    if (thinking || state.turn !== 0) return;
    setThinking(true);
    setManualMode(true);
    setWildChoices(null);
    setPreview(null);
    setSelectedAdviceIndex(null);
    const remaining = manualOptions
      .filter(([first]) => first && sameMove(first, move))
      .map((sequence) => sequence.slice(1));
    const moved = await animateSequence(state, [move]);
    setSelectedOrigin(null);

    if (
      moved.winner !== null ||
      remaining.every((sequence) => !sequence.length)
    ) {
      const finished = nextTurn(moved);
      setState(finished);
      setManualOptions([]);
      setManualMode(false);
      setThinking(false);
      setMessage(
        moved.winner === 0
          ? 'You win the game.'
          : `You played ${moveLabel(move)}.`,
      );
      if (moved.winner === null) runBot(finished);
      return;
    }

    setManualOptions(remaining);
    setThinking(false);
    setMessage(`Played ${moveLabel(move)}. Select your next checker.`);
  }

  function handleBoardPoint(point: BackgammonPoint | BackgammonDestination) {
    if (thinking || state.turn !== 0 || !state.dice.length) return;
    if (selectedOrigin !== null) {
      const destination = selectableMoves.find(
        (move) => move.from === selectedOrigin && move.to === point,
      );
      if (destination) {
        void playManualMove(destination);
        return;
      }
    }
    if (
      point !== 'off' &&
      selectableMoves.some((move) => move.from === point)
    ) {
      setSelectedOrigin(point);
      setManualMode(true);
      setWildChoices(null);
      setMessage(
        point === 'bar'
          ? 'Choose a highlighted entry point.'
          : `Checker on ${point} selected. Choose a highlighted destination.`,
      );
    }
  }

  function handleAdviceChoice(index: number) {
    const choice = choices[index];
    if (!choice) return;
    if (touchAdvice) {
      setSelectedAdviceIndex(index);
      setPreview(choice.sequence);
      return;
    }
    void playSequence(choice.sequence);
  }

  function confirmAdviceChoice() {
    if (selectedAdviceIndex === null) return;
    const choice = choices[selectedAdviceIndex];
    if (choice) void playSequence(choice.sequence);
  }

  return (
    <main className="app-shell" data-game="backgammon">
      <header className="app-header">
        <GameTitleSelector
          currentGame="backgammon"
          subtitle="Standard checker play"
        />
        <nav className="mode-switch" aria-label="Application mode">
          <button className="mode-pill mode-pill-active">Play</button>
          <button className="mode-pill" disabled>
            Learn
          </button>
          <button className="mode-pill" disabled>
            Train
          </button>
          <button className="mode-pill" disabled>
            Model
          </button>
        </nav>
        <div className="header-actions">
          <span className="local-badge">
            <span className="status-dot" /> Local rules
          </span>
          <Button variant="ghost" size="icon" aria-label="Settings" disabled>
            <Settings2 />
          </Button>
        </div>
      </header>

      <section className="backgammon-workspace">
        <aside
          className={`backgammon-panel position-panel${evalExpanded ? ' mobile-panel-expanded' : ''}`}
        >
          <div className="mobile-panel-summary">
            <div>
              <span className="eyebrow">Eval</span>
              <h2>
                {positionEval
                  ? `${Math.round(positionEval.winChance * 100)}% win · ${positionEval.equity >= 0 ? '+' : ''}${positionEval.equity.toFixed(2)}`
                  : 'Evaluating…'}
              </h2>
            </div>
            <button
              className="backgammon-panel-toggle"
              onClick={() => setEvalExpanded((expanded) => !expanded)}
              aria-expanded={evalExpanded}
              aria-label={`${evalExpanded ? 'Collapse' : 'Expand'} evaluation`}
            >
              <ChevronDown />
            </button>
          </div>
          <div className="mobile-panel-body">
            <div
              className="backgammon-eval-bar"
              aria-label="Current position equity"
            >
              <span className="eval-ink">Ink</span>
              <i />
              <b style={{ left: `${evalPercent}%` }} />
              <span className="eval-you">You</span>
            </div>
            <div className="backgammon-eval-chart">
              <div>
                <span>Evaluation history</span>
                <b>{evalHistory.length} positions</b>
              </div>
              <svg
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                role="img"
                aria-label="Evaluation throughout this game"
              >
                <line x1="0" y1="50" x2="100" y2="50" />
                <polyline points={chartPoints} />
                {latestChartPoint && (
                  <circle
                    cx={latestChartPoint.x}
                    cy={latestChartPoint.y}
                    r="2"
                  />
                )}
              </svg>
              <span className="chart-you">You</span>
              <span className="chart-ink">Ink</span>
            </div>
            <div className="position-stat">
              <span>Position</span>
              <strong>
                {state.winner === null
                  ? phase
                  : state.winner === 0
                    ? 'You won'
                    : 'Ink won'}
              </strong>
            </div>
            <div className="position-stat">
              <span>Your pip count</span>
              <strong>{pipCount(state, 0)}</strong>
            </div>
            <div className="position-stat">
              <span>Ink pip count</span>
              <strong>{pipCount(state, 1)}</strong>
            </div>
            <div className="position-stat">
              <span>Turn</span>
              <strong>{state.turn === 0 ? 'You' : 'Ink'}</strong>
            </div>
            <div className="position-stat">
              <span>Move</span>
              <strong>{state.moveNumber + 1}</strong>
            </div>
            <div className="position-concept">
              <CircleDot />
              <div>
                <strong>
                  {state.bar[0]
                    ? 'Enter from the bar first'
                    : 'You move clockwise'}
                </strong>
                <span>Cream checkers travel from point 24 toward point 1.</span>
              </div>
            </div>
          </div>
        </aside>

        <section className="backgammon-center">
          <BackgammonBoard
            state={state}
            preview={preview}
            animatedMove={animatedMove}
            rolling={rolling}
            selectableMoves={selectableMoves}
            selectedOrigin={selectedOrigin}
            onPointClick={handleBoardPoint}
            onRoll={() => void handleRoll()}
            canRoll={
              state.turn === 0 && state.winner === null && !thinking && !rolling
            }
            message={message}
            shownDice={shownDice}
            onPlayAgain={resetGame}
          />
          <Button
            variant="outline"
            className="backgammon-reset"
            onClick={resetGame}
          >
            <RotateCcw /> New game
          </Button>
        </section>

        <aside
          className={`backgammon-panel advice-panel${adviceExpanded ? ' mobile-panel-expanded' : ''}`}
        >
          <div className="backgammon-panel-heading">
            <div>
              <span className="eyebrow">Advice</span>
              <h2>
                {adviceEnabled && choices[0]
                  ? `${sequenceLabel(choices[0].sequence)} · ${'equity' in choices[0] ? `${Math.round(choices[0].winChance * 100)}%` : 'Suggested'}`
                  : adviceEnabled
                    ? 'Legal moves'
                    : 'Advice off'}
              </h2>
            </div>
            <div className="panel-heading-actions">
              <button
                className={`advice-power${adviceEnabled ? ' advice-power-on' : ''}`}
                onClick={() => {
                  setAdviceEnabled((enabled) => !enabled);
                  setPreview(null);
                  setSelectedAdviceIndex(null);
                }}
                aria-pressed={adviceEnabled}
                aria-label={`${adviceEnabled ? 'Hide' : 'Show'} advice`}
              >
                {adviceEnabled ? <Eye /> : <EyeOff />}
                <span>{adviceEnabled ? 'On' : 'Off'}</span>
              </button>
              <button
                className="backgammon-panel-toggle"
                onClick={() => setAdviceExpanded((expanded) => !expanded)}
                aria-expanded={adviceExpanded}
                aria-label={`${adviceExpanded ? 'Collapse' : 'Expand'} advice`}
              >
                <ChevronDown />
              </button>
            </div>
          </div>
          <div className="mobile-panel-body">
            {!adviceEnabled ? (
              <div className="advice-empty advice-disabled">
                <EyeOff />
                <strong>Advice is hidden</strong>
                <p>Turn it back on whenever you want move suggestions.</p>
              </div>
            ) : state.turn === 0 && state.dice.length && choices.length ? (
              <div className="backgammon-move-list">
                {choices.slice(0, 8).map((choice, index) => (
                  <button
                    className={
                      selectedAdviceIndex === index ? 'move-selected' : ''
                    }
                    key={sequenceLabel(choice.sequence)}
                    onClick={() => handleAdviceChoice(index)}
                    onMouseEnter={() => setPreview(choice.sequence)}
                    onMouseLeave={() => {
                      if (!touchAdvice) setPreview(null);
                    }}
                    onFocus={() => setPreview(choice.sequence)}
                    onBlur={() => {
                      if (!touchAdvice) setPreview(null);
                    }}
                  >
                    <span>
                      <b>{index + 1}</b>
                      <strong>{sequenceLabel(choice.sequence)}</strong>
                    </span>
                    <small>
                      {index === 0 ? 'Suggested · ' : ''}
                      {'equity' in choice
                        ? `${Math.round(choice.winChance * 100)}% · ${choice.equity >= 0 ? '+' : ''}${choice.equity.toFixed(2)}`
                        : `${choice.score >= 0 ? '+' : ''}${choice.score} fallback`}
                    </small>
                  </button>
                ))}
                {touchAdvice && selectedAdviceIndex !== null && (
                  <Button
                    className="confirm-advice-move"
                    onClick={confirmAdviceChoice}
                  >
                    <Check /> Confirm move
                  </Button>
                )}
              </div>
            ) : (
              <div className="advice-empty">
                <Lightbulb />
                <strong>
                  {thinking
                    ? state.turn === 0
                      ? 'Playing your move'
                      : 'Ink is choosing a move'
                    : manualMode
                      ? selectedOrigin === null
                        ? 'Select a highlighted checker'
                        : 'Select a highlighted destination'
                      : state.turn === 0 && state.dice.length
                        ? 'WildBG is ranking your moves'
                        : 'Roll to see your options'}
                </strong>
                <p>
                  Every listed option is a complete legal sequence using the
                  maximum playable dice.
                </p>
              </div>
            )}
            <div className="engine-roadmap">
              <span>
                <b>1</b> Rules engine · active
              </span>
              <span>
                <b>2</b> WildBG neural evaluator ·{' '}
                {engineStatus === 'loading'
                  ? 'loading'
                  : engineStatus === 'ready'
                    ? 'active'
                    : 'fallback'}
              </span>
              <span>
                <b>3</b> Contact + race networks · active
              </span>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}
