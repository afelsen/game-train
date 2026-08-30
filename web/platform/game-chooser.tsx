import { ArrowRight, Dices, Gamepad2, Spade } from 'lucide-react';
import { GameTitleSelector } from './game-title-selector';

const GAME_CHOICES = [
  {
    id: 'poker',
    title: 'Poker train',
    description:
      'Play six-max hold’em with live strategy, equity, and hand analysis.',
    detail: 'Play · Train · Model',
    icon: Spade,
  },
  {
    id: 'backgammon',
    title: 'Backgammon train',
    description:
      'Learn checker play on a dedicated board with move-by-move analysis.',
    detail: 'Foundation in progress',
    icon: Dices,
  },
] as const;

export default function GameChooser() {
  return (
    <main className="game-chooser app-shell">
      <header className="app-header chooser-header">
        <GameTitleSelector />
        <p>One place to learn optimal play.</p>
      </header>
      <section className="game-chooser-content">
        <div className="game-chooser-heading">
          <span className="eyebrow">Choose a game</span>
          <h1>Which train are you boarding?</h1>
          <p>
            Each car has its own board, teaching language, and strategy engines.
          </p>
        </div>
        <div className="train-scroll-region">
          <div
            className="train-scroll"
            role="region"
            aria-label="Game train"
            tabIndex={0}
          >
            <div className="train-consist">
              <div className="train-engine" aria-hidden="true">
                <img src="./illustrations/train-engine.png" alt="" />
              </div>
              {GAME_CHOICES.map((game) => {
                const Icon = game.icon;
                return (
                  <a
                    className={`game-choice-card train-car game-choice-${game.id}`}
                    href={`./${game.id}/`}
                    key={game.id}
                  >
                    <span className="train-car-roof" />
                    <span className="train-car-window" aria-hidden="true">
                      {game.id === 'poker' ? (
                        <span className="poker-car-art">
                          <i>♠</i>
                          <i>♥</i>
                          <i>♣</i>
                          <i>♦</i>
                        </span>
                      ) : (
                        <span className="backgammon-car-art">
                          {Array.from({ length: 8 }, (_, index) => (
                            <i key={index} />
                          ))}
                          <b />
                          <b />
                          <b />
                        </span>
                      )}
                    </span>
                    <span className="game-choice-copy">
                      <span className="game-choice-icon">
                        <Icon />
                      </span>
                      <span className="eyebrow">{game.detail}</span>
                      <h2>{game.title}</h2>
                      <p>{game.description}</p>
                      <span className="game-choice-action">
                        Open game <ArrowRight />
                      </span>
                    </span>
                    <span className="train-wheels" aria-hidden="true">
                      <i />
                      <i />
                    </span>
                  </a>
                );
              })}
              <article
                className="train-car next-game-car"
                aria-label="Future game car"
              >
                <span className="train-car-roof" />
                <span className="train-car-window next-car-window">
                  <Gamepad2 />
                </span>
                <span className="game-choice-copy">
                  <span className="eyebrow">Next stop</span>
                  <h2>Another game</h2>
                  <p>
                    The train keeps growing. More strategy games will board
                    here.
                  </p>
                  <span className="next-game-label">Coming later</span>
                </span>
                <span className="train-wheels" aria-hidden="true">
                  <i />
                  <i />
                </span>
              </article>
              <span className="train-caboose-space" aria-hidden="true" />
            </div>
          </div>
          <p className="train-scroll-hint">
            Scroll to explore the train <ArrowRight />
          </p>
        </div>
      </section>
    </main>
  );
}
