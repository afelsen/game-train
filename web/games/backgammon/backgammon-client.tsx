'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  CircleDot,
  Gauge,
  Lightbulb,
  RotateCcw,
  Settings2,
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
  rankWithWildBg,
  warmWildBg,
  type WildBgEvaluation,
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
  return legalMoveSequences(state)
    .map((sequence) => ({ sequence, score: scoreSequence(state, sequence) }))
    .sort((left, right) => right.score - left.score);
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
  if (point === 'bar') return { x: 50, y: player === 0 ? 82 : 18 };
  if (point === 'off') return { x: 97, y: player === 0 ? 91 : 9 };
  const index = DISPLAY_POINTS.indexOf(point);
  return {
    x: ((index % 12) + 0.5) * (100 / 12),
    y: index < 12 ? 9 : 91,
  };
}

function BackgammonBoard({
  state,
  preview,
  animatedMove,
  rolling,
}: {
  state: BackgammonState;
  preview: BackgammonMove[] | null;
  animatedMove: { move: BackgammonMove; player: BackgammonPlayer } | null;
  rolling: boolean;
}) {
  const activePoints = new Set(
    legalMoveSequences(state).flatMap((sequence) =>
      sequence.flatMap((move) => [move.from, move.to]),
    ),
  );
  const previewOrigins = new Set(preview?.map((move) => move.from) ?? []);
  return (
    <div className="backgammon-board" aria-label="Backgammon board">
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
              className={`backgammon-point point-${point}${activePoints.has(point) ? ' point-legal' : ''}${previewOrigins.has(point) ? ' point-preview-origin' : ''}${animatedMove?.move.from === point ? ' point-moving-origin' : ''}`}
              key={point}
              aria-label={`Point ${point}${checkers ? `, ${checkers.count} ${checkers.owner} checker${checkers.count === 1 ? '' : 's'}` : ', empty'}`}
            >
              <span className="point-number">{point}</span>
              {checkers && (
                <span className={`checker-stack checker-${checkers.owner}`}>
                  {Array.from(
                    { length: Math.min(checkers.count, 5) },
                    (_, index) => (
                      <i key={index} />
                    ),
                  )}
                  {checkers.count > 5 && <b>{checkers.count}</b>}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="backgammon-bar">
        {state.bar[1] > 0 && (
          <b className="bar-checker bar-ink">{state.bar[1]}</b>
        )}
        <span>BAR</span>
        {state.bar[0] > 0 && (
          <b className="bar-checker bar-cream">{state.bar[0]}</b>
        )}
      </div>
      <div className="borne-off borne-off-ink">
        <span>Ink off</span>
        <b>{state.off[1]}</b>
      </div>
      <div className="borne-off borne-off-cream">
        <span>You off</span>
        <b>{state.off[0]}</b>
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
          {preview.map((move, index) => {
            const from = boardCoordinates(move.from, state.turn);
            const to = boardCoordinates(move.to, state.turn);
            return (
              <g key={`${moveLabel(move)}-${index}`}>
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  markerEnd="url(#preview-arrow)"
                />
                <circle cx={to.x} cy={to.y} r="2.2" />
              </g>
            );
          })}
        </svg>
      )}
      {animatedMove &&
        (() => {
          const from = boardCoordinates(
            animatedMove.move.from,
            animatedMove.player,
          );
          const to = boardCoordinates(
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
      {(rolling || state.dice.length > 0) && (
        <span className={`board-dice ${rolling ? 'board-dice-rolling' : ''}`}>
          {(rolling ? ['?', '?'] : state.dice).map((die, index) => (
            <i key={index}>{die}</i>
          ))}
        </span>
      )}
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
  const [preview, setPreview] = useState<BackgammonMove[] | null>(null);
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
  const botTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heuristicChoices = useMemo(() => rankedSequences(state), [state]);
  const choices =
    wildChoices ?? (engineStatus === 'fallback' ? heuristicChoices : []);
  const phase =
    state.off[0] + state.off[1] > 0
      ? 'Bear-off'
      : state.bar[0] + state.bar[1] > 0
        ? 'Hit race'
        : 'Contact';

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
    let cancelled = false;
    setWildChoices(null);
    if (
      thinking ||
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
  }, [state, thinking]);

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
    setAnimatedMove(null);
    setRolling(false);
    setThinking(false);
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
        <aside className="backgammon-panel position-panel">
          <span className="eyebrow">Position</span>
          <h2>
            {state.winner === null
              ? phase
              : state.winner === 0
                ? 'You won'
                : 'Ink won'}
          </h2>
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
          <Button
            variant="outline"
            className="backgammon-reset"
            onClick={resetGame}
          >
            <RotateCcw /> New game
          </Button>
        </aside>

        <section className="backgammon-center">
          <BackgammonBoard
            state={state}
            preview={preview}
            animatedMove={animatedMove}
            rolling={rolling}
          />
          <div className="backgammon-controls" aria-label="Backgammon controls">
            <span
              className="backgammon-dice"
              aria-label={
                state.dice.length
                  ? `Dice ${state.dice.join(' and ')}`
                  : 'Dice not rolled'
              }
            >
              {(state.dice.length ? state.dice : ['–', '–']).map(
                (die, index) => (
                  <i key={index}>{die}</i>
                ),
              )}
            </span>
            <p>{message}</p>
            <Button
              onClick={handleRoll}
              disabled={
                state.turn !== 0 ||
                Boolean(state.dice.length) ||
                state.winner !== null ||
                thinking ||
                rolling
              }
            >
              Roll dice
            </Button>
          </div>
        </section>

        <aside className="backgammon-panel advice-panel">
          <div className="backgammon-panel-heading">
            <div>
              <span className="eyebrow">Advice</span>
              <h2>Legal moves</h2>
            </div>
            <Gauge />
          </div>
          {state.turn === 0 && state.dice.length && choices.length ? (
            <div className="backgammon-move-list">
              {choices.slice(0, 8).map((choice, index) => (
                <button
                  key={sequenceLabel(choice.sequence)}
                  onClick={() => playSequence(choice.sequence)}
                  onMouseEnter={() => setPreview(choice.sequence)}
                  onMouseLeave={() => setPreview(null)}
                  onFocus={() => setPreview(choice.sequence)}
                  onBlur={() => setPreview(null)}
                >
                  <span>
                    <b>{index + 1}</b>
                    <strong>{sequenceLabel(choice.sequence)}</strong>
                  </span>
                  <small>
                    {index === 0
                      ? 'Suggested'
                      : 'equity' in choice
                        ? `${Math.round(choice.winChance * 100)}% win · ${choice.equity >= 0 ? '+' : ''}${choice.equity.toFixed(2)}`
                        : `${choice.score >= 0 ? '+' : ''}${choice.score} fallback`}
                  </small>
                </button>
              ))}
            </div>
          ) : (
            <div className="advice-empty">
              <Lightbulb />
              <strong>
                {thinking
                  ? state.turn === 0
                    ? 'Playing your move'
                    : 'Ink is choosing a move'
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
        </aside>
      </section>
    </main>
  );
}
