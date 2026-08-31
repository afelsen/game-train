'use client';

import { ChevronDown, Dices, Spade, TrainFront } from 'lucide-react';

export type GameId = 'poker' | 'backgammon';

const GAMES: Array<{
  id: GameId;
  title: string;
  description: string;
  icon: typeof Spade;
}> = [
  {
    id: 'poker',
    title: 'poker train',
    description: 'Six-max hold’em',
    icon: Spade,
  },
  {
    id: 'backgammon',
    title: 'backgammon train',
    description: 'Checker play',
    icon: Dices,
  },
];

function gameHref(currentGame: GameId | undefined, targetGame: GameId) {
  return currentGame ? `../${targetGame}/` : `./${targetGame}/`;
}

export function GameTitleSelector({
  currentGame,
  subtitle,
}: {
  currentGame?: GameId;
  subtitle?: string;
}) {
  const selected = GAMES.find((game) => game.id === currentGame);

  return (
    <div className="game-brand-group">
      <a
        className="brand-home-link"
        href={currentGame ? '../' : './'}
        aria-label="Go to the game train home page"
      >
        <span className="brand-mark" aria-hidden="true">
          <TrainFront className="size-5" strokeWidth={1.8} />
        </span>
      </a>
      <details className="game-title-selector">
        <summary className="brand-lockup" aria-label="Choose a game">
          <span className="brand-copy">
            <span className="brand-name">
              {selected?.title ?? 'game train'}
            </span>
            <span className="brand-subtitle">
              {subtitle ?? selected?.description ?? 'Choose your game'}
            </span>
          </span>
          <ChevronDown className="game-title-chevron" aria-hidden="true" />
        </summary>
        <nav className="game-picker-menu" aria-label="Games">
          {GAMES.map((game) => {
            const Icon = game.icon;
            return (
              <a
                className={game.id === currentGame ? 'game-picker-active' : ''}
                href={gameHref(currentGame, game.id)}
                key={game.id}
              >
                <span className="game-picker-icon">
                  <Icon />
                </span>
                <span>
                  <strong>{game.title}</strong>
                  <small>{game.description}</small>
                </span>
                {game.id === currentGame && <i>Current</i>}
              </a>
            );
          })}
        </nav>
      </details>
    </div>
  );
}
