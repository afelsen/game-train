import { ArrowRight, Dices, Spade } from 'lucide-react';
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
            Each game has its own board, teaching language, and strategy
            engines.
          </p>
        </div>
        <div className="game-choice-grid">
          {GAME_CHOICES.map((game) => {
            const Icon = game.icon;
            return (
              <a
                className={`game-choice-card game-choice-${game.id}`}
                href={`./${game.id}/`}
                key={game.id}
              >
                <span className="game-choice-icon">
                  <Icon />
                </span>
                <span className="eyebrow">{game.detail}</span>
                <h2>{game.title}</h2>
                <p>{game.description}</p>
                <span className="game-choice-action">
                  Open game <ArrowRight />
                </span>
              </a>
            );
          })}
        </div>
      </section>
    </main>
  );
}
