import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import GameRouteClient from '@/platform/game-route-client';
import '@/app/globals.css';

const root = document.getElementById('root');
if (!root) throw new Error('Game Train root element was not found');

createRoot(root).render(
  <StrictMode>
    <GameRouteClient />
  </StrictMode>,
);
