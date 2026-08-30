import BackgammonClient from '@/games/backgammon/backgammon-client';
import type { Metadata } from 'next';

export const dynamic = 'force-static';
export const metadata: Metadata = {
  title: 'backgammon train',
  description: 'Learn Backgammon checker play with position and move analysis.',
};

export default function BackgammonPage() {
  return <BackgammonClient />;
}
