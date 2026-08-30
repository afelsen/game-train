import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import GameRouteClient from '@/platform/game-route-client';
import '@/app/globals.css';

if (typeof document !== 'undefined') {
  const root = document.getElementById('root');
  if (!root) throw new Error('Game Train root element was not found');

  createRoot(root).render(
    <StrictMode>
      <GameRouteClient />
    </StrictMode>,
  );
}

// Vinext also discovers files in `pages/`. Keeping this harmless default
// export lets its server-side route scan complete while Vite uses the module
// above as the static GitHub Pages entry.
export default function StaticPagesEntry() {
  return null;
}
