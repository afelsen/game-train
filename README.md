# Game Trainer

An educational game simulator and strategy trainer. The first game is heads-up no-limit Texas Hold'em cash poker; backgammon can later use the same game/provider architecture.

See [PLAN.md](./PLAN.md) for the product and implementation plan.

## Current implementation

Phase 1 includes a deterministic authoritative heads-up NLHE hand engine under `game_trainer/poker`. Phase 2 adds strategy providers, action translation, and an authoritative game service. Phase 3 adds a playable local browser table under `web/`. Phase 4 adds custom bet sizing, SQLite-backed hand review, and the first native postflop-solver worker. Their contracts are documented under `reports/`.

## Native solver worker

Build and verify the pinned local postflop solver:

```sh
scripts/build_solver_worker.sh
.venv/bin/python scripts/probe_solver_worker.py
```

Restart `scripts/run_api.py` after building. `GET /v1/health` will then report `"solver":"available"`. Submit visual or headless jobs to `POST /v1/solver/jobs`; visual jobs retain periodic progress snapshots, while headless jobs retain only the final result. The web app's Train tab can run, visualize, bypass the cache for, and cancel these solves. See `reports/SOLVER-POC.md` for the current scope and licensing notes.

Training spots are available from `GET /v1/training/spots`. Use `source=curated` for maintained teaching positions or `source=random&seed=<integer>&count=<1-20>` for deterministic generated turn spots.

Run the complete checks with:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Run the playable local version in two terminals:

```sh
.venv/bin/python scripts/run_api.py
```

```sh
cd web
pnpm dev
```

Then open `http://localhost:3000`. Hand history is saved to `data/game-trainer.sqlite3`; override the location with `GAME_TRAINER_DB_PATH`.

## Initial product boundary

- Educational simulation only; no real-money client integration or automation.
- Heads-up cash game, initially 100 big-blind effective stacks, no rake or antes.
- Local execution where practical, with server-side model inference and solving supported when compute or packaging requires it.
- Provider-neutral strategy API so downloaded policies, local solvers, and our own trained models can be compared using the same states and actions.
