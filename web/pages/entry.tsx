import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import GameClient from '@/app/game-client';
import '@/app/globals.css';

const root = document.getElementById('root');
if (!root) throw new Error('Game Train root element was not found');

createRoot(root).render(
  <StrictMode>
    <GameClient />
  </StrictMode>,
);
