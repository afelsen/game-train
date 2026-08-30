'use client';

import {
  CircleDot,
  Construction,
  Dices,
  Gauge,
  Lightbulb,
  Settings2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GameTitleSelector } from '@/platform/game-title-selector';
import { createInitialBackgammonState } from './runtime/backgammon-engine';

const POINTS = Array.from({ length: 24 }, (_, index) => index + 1);
const INITIAL_STATE = createInitialBackgammonState();

function BackgammonBoardPreview() {
  return (
    <div className="backgammon-board" aria-label="Backgammon board preview">
      <div className="backgammon-points">
        {POINTS.map((point) => {
          const value = INITIAL_STATE.points[point - 1];
          const checkers = value
            ? {
                owner: value > 0 ? ('cream' as const) : ('ink' as const),
                count: Math.abs(value),
              }
            : null;
          return (
            <div className={`backgammon-point point-${point}`} key={point}>
              {checkers && (
                <span className={`checker-stack checker-${checkers.owner}`}>
                  {Array.from(
                    { length: Math.min(checkers.count, 5) },
                    (_, index) => (
                      <i key={index} />
                    ),
                  )}
                  {checkers.count > 1 && <b>{checkers.count}</b>}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="backgammon-bar">
        <span>BAR</span>
      </div>
      <div className="board-preview-note">
        <Dices />
        <strong>Board foundation</strong>
        <span>Legal movement and dice are the next implementation step.</span>
      </div>
    </div>
  );
}

export default function BackgammonClient() {
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
            <span className="status-dot status-planned" />
            Foundation
          </span>
          <Button variant="ghost" size="icon" aria-label="Settings" disabled>
            <Settings2 />
          </Button>
        </div>
      </header>

      <section className="backgammon-workspace">
        <aside className="backgammon-panel position-panel">
          <span className="eyebrow">Position</span>
          <h2>Opening position</h2>
          <div className="position-stat">
            <span>Your pip count</span>
            <strong>167</strong>
          </div>
          <div className="position-stat">
            <span>Opponent</span>
            <strong>167</strong>
          </div>
          <div className="position-stat">
            <span>Phase</span>
            <strong>Contact</strong>
          </div>
          <div className="position-concept">
            <CircleDot />
            <div>
              <strong>All checkers home</strong>
              <span>No checkers are on the bar or borne off.</span>
            </div>
          </div>
        </aside>

        <section className="backgammon-center">
          <div className="session-bar">
            <div>
              <span className="eyebrow">Play</span>
              <h1>Standard game</h1>
            </div>
            <span className="backgammon-phase">
              <Construction /> Rules engine next
            </span>
          </div>
          <BackgammonBoardPreview />
          <div
            className="backgammon-controls"
            aria-label="Backgammon controls preview"
          >
            <span>
              <i>3</i>
              <i>1</i>
            </span>
            <p>Roll the dice, then move every legal checker sequence.</p>
            <Button disabled>Roll dice</Button>
          </div>
        </section>

        <aside className="backgammon-panel advice-panel">
          <div className="backgammon-panel-heading">
            <div>
              <span className="eyebrow">Advice</span>
              <h2>Move analysis</h2>
            </div>
            <Gauge />
          </div>
          <div className="advice-empty">
            <Lightbulb />
            <strong>Game-specific by design</strong>
            <p>
              This panel will rank complete checker sequences by equity—not
              reuse Poker’s action mix.
            </p>
          </div>
          <div className="engine-roadmap">
            <span>
              <b>1</b> Local rules engine
            </span>
            <span>
              <b>2</b> WildBG evaluation
            </span>
            <span className="engine-roadmap-p2">
              <b>3</b> Our model · P2
            </span>
          </div>
        </aside>
      </section>
    </main>
  );
}
