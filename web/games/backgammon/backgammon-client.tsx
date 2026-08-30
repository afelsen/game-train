'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CircleDot,
  Dices,
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
  type BackgammonPlayer,
  type BackgammonState,
} from './runtime/backgammon-engine';

const POINTS = Array.from({ length: 24 }, (_, index) => index + 1);

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

function BackgammonBoard({ state }: { state: BackgammonState }) {
  const activePoints = new Set(
    legalMoveSequences(state).flatMap((sequence) =>
      sequence.flatMap((move) => [move.from, move.to]),
    ),
  );
  return (
    <div className="backgammon-board" aria-label="Backgammon board">
      <div className="backgammon-points">
        {POINTS.map((point) => {
          const value = state.points[point - 1];
          const checkers = value
            ? {
                owner: value > 0 ? ('cream' as const) : ('ink' as const),
                count: Math.abs(value),
              }
            : null;
          return (
            <div
              className={`backgammon-point point-${point}${activePoints.has(point) ? ' point-legal' : ''}`}
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
    </div>
  );
}

export default function BackgammonClient() {
  const [state, setState] = useState(createInitialBackgammonState);
  const [message, setMessage] = useState(
    'Roll to begin. You move toward point 1.',
  );
  const [thinking, setThinking] = useState(false);
  const botTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const choices = useMemo(() => rankedSequences(state), [state]);
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

  function resetGame() {
    if (botTimer.current) clearTimeout(botTimer.current);
    setState(createInitialBackgammonState());
    setThinking(false);
    setMessage('Roll to begin. You move toward point 1.');
  }

  function runBot(start: BackgammonState) {
    setThinking(true);
    setMessage('Ink is rolling…');
    botTimer.current = setTimeout(() => {
      const rolled = { ...start, dice: rollDice() };
      const ranked = rankedSequences(rolled);
      const chosen = ranked[0]?.sequence ?? [];
      const moved = applyMoveSequence(rolled, chosen);
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

  function handleRoll() {
    if (
      state.turn !== 0 ||
      state.dice.length ||
      state.winner !== null ||
      thinking
    )
      return;
    const dice = rollDice();
    const rolled = { ...state, dice };
    const legal = legalMoveSequences(rolled);
    setState(rolled);
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

  function playSequence(sequence: BackgammonMove[]) {
    if (state.turn !== 0 || !state.dice.length || thinking) return;
    const moved = applyMoveSequence(state, sequence);
    const finished = nextTurn(moved);
    setState(finished);
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
          <div className="session-bar">
            <div>
              <span className="eyebrow">Play</span>
              <h1>You vs. Ink</h1>
            </div>
            <span className="backgammon-phase">
              <Dices />{' '}
              {thinking
                ? 'Ink thinking'
                : state.winner !== null
                  ? 'Game over'
                  : state.turn === 0
                    ? 'Your turn'
                    : 'Ink turn'}
            </span>
          </div>
          <BackgammonBoard state={state} />
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
                thinking
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
              {choices.slice(0, 8).map(({ sequence, score }, index) => (
                <button
                  key={sequenceLabel(sequence)}
                  onClick={() => playSequence(sequence)}
                >
                  <span>
                    <b>{index + 1}</b>
                    <strong>{sequenceLabel(sequence)}</strong>
                  </span>
                  <small>
                    {index === 0
                      ? 'Suggested'
                      : `${score >= 0 ? '+' : ''}${score} heuristic`}
                  </small>
                </button>
              ))}
            </div>
          ) : (
            <div className="advice-empty">
              <Lightbulb />
              <strong>
                {thinking
                  ? 'Ink is choosing a move'
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
              <b>2</b> Heuristic move ranking · active
            </span>
            <span className="engine-roadmap-p2">
              <b>3</b> WildBG evaluation · next
            </span>
          </div>
        </aside>
      </section>
    </main>
  );
}
