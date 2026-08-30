import GameClient from '../game-client';
import type { Metadata } from 'next';

export const dynamic = 'force-static';
export const metadata: Metadata = {
  title: 'poker train',
  description:
    'Practice six-max no-limit hold’em with strategy and equity analysis.',
};

export default function PokerPage() {
  return <GameClient />;
}
