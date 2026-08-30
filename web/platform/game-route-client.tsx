'use client';

import GameClient from '@/app/game-client';
import BackgammonClient from '@/games/backgammon/backgammon-client';
import GameChooser from './game-chooser';

export default function GameRouteClient() {
  const segments = window.location.pathname.split('/').filter(Boolean);
  if (segments.includes('backgammon')) return <BackgammonClient />;
  if (segments.includes('poker')) return <GameClient />;
  return <GameChooser />;
}
