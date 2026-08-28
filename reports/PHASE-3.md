# Phase 3: playable browser vertical slice

Status: complete for local development.

## Delivered

- Supported Sites/Vinext React workspace with shadcn components.
- Responsive heads-up poker table focused on the current decision.
- Real cards, board, pot, stacks, dealer position, street, and legal actions from the authoritative Python engine.
- Human action submission with automatic check/call bot turns.
- New-hand flow with recorded deterministic seed.
- Terminal showdown with opponent-card reveal and payouts.
- Decision coach with recent action history.
- On-demand Fullhouse mixed-strategy display with experimental warnings.
- Loading, engine-offline, action-error, and terminal states.
- HTTP adapter with health, provider discovery, hand, action, and strategy endpoints.
- CORS restricted to the local web origin.
- Social preview and page metadata.

## Local architecture

```text
Browser :3000
    |
    | JSON over HTTP
    v
Python API :8000
    |
    +-- GameService (authoritative ownership)
    +-- Heads-up NLHE engine
    +-- Provider registry
          +-- check/call bot
          +-- uniform random bot
          +-- experimental Fullhouse adapter
```

The browser never receives the deck or the opponent's private cards before showdown. It receives only `HandState.observation(heroSeat)`.

## Running locally

Terminal 1:

```sh
.venv/bin/python scripts/run_api.py
```

Terminal 2:

```sh
cd web
pnpm dev
```

Then open `http://localhost:3000`.

Environment variables are documented in `web/.env.example`. The current UI is intentionally local; a hosted UI will need `NEXT_PUBLIC_API_URL` set to a deployed Python service with HTTPS and an updated CORS allowlist.

## Verification

- 23 Python tests pass, including three direct HTTP-application tests.
- Interactive check/call hand completes through the API and reveals showdown cards only at terminal state.
- Fullhouse strategy endpoint returns normalized legal actions.
- Web application lint passes for application source.
- Production Vinext build passes.
- Both local UI and API readiness checks pass.

## Current limitations

- The bot is deliberately the safe check/call baseline; Fullhouse is advice-only because its heads-up quality is unvalidated.
- Raise UI currently submits the engine's minimum legal raise. Custom sizing is next.
- Sessions are process-local and disappear when the API stops.
- Train and Review navigation are visible but disabled.
- No authentication, hosted API, or durable hand history yet.

## Exit recommendation

The next slice should add custom raise sizing, SQLite hand persistence, and hand replay/review. Training-mode grading should wait for the postflop solver adapter or our own validated heads-up model.

