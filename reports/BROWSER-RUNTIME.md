# Browser runtime architecture

Game Train uses one transport-neutral request contract with two execution modes:

- `browser` (default): poker rules, live hand state, and review history run in the browser. Local baseline providers require no server. Fullhouse, equity, range analysis, solving, and model experiments use the optional Python API.
- `server`: the existing Python service owns the full hand. This remains available for debugging and cross-runtime parity checks.

Set `NEXT_PUBLIC_PLAY_RUNTIME=server` to use the legacy mode. In development, the model API defaults to `http://localhost:8000`. Static production builds have no API by default and select the local check/call baseline. Set `NEXT_PUBLIC_API_URL` at build time to enable Fullhouse and analysis.

## Boundaries

`web/lib/runtime/contracts.ts` contains UI-facing game and provider contracts. `BrowserPlayRuntime` implements the Play routes without changing the UI. Calls it does not own are delegated to `remoteRequest`, so model-development features remain independent of the game loop.

The browser sends a complete hand snapshot to `POST /v1/strategy`. Python validates card uniqueness, chip conservation, turn ownership, and the terminal-state invariants before inference. The server does not retain that hand.

This boundary is intended to support future games: a new game runtime implements the same request interface, while its models can remain browser-local, remote, or mixed.

## GitHub Pages

`.github/workflows/pages.yml` builds and deploys the static client from `web/dist/pages`. Configure the repository variable `GAME_TRAIN_API_URL` if a public HTTPS model API is available. Without it, Play remains functional with local providers; server-backed panels are unavailable.

GitHub Pages uses `vite.pages.config.ts`, a client-only build that reuses the same React application and runtime modules. Relative asset paths support both `username.github.io` and project sites such as `username.github.io/game-trainer/` without coupling the build to a repository name. Local development continues to use vinext.

GitHub repository Pages must be set to **GitHub Actions** as its source. The workflow deploys pushes to `main` and can also be started manually.
