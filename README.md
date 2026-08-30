# game train

An educational game simulator and strategy trainer. The first game is six-max no-limit Texas Hold'em cash poker; backgammon can later use the same game/provider architecture.

See [PLAN.md](./PLAN.md) for the product and implementation plan.

## Current implementation

The current Play MVP includes a deterministic authoritative two-to-six-player NLHE engine under `game_trainer/poker`, a six-seat browser table under `web/`, and the pretrained six-player Fullhouse checkpoint as the shared bot policy. Strategy providers, action translation, hand review, training experiments, and the postflop-solver worker use the same authoritative game service. Their contracts are documented under `reports/`.

## Native solver worker

Build and verify the pinned local postflop solver:

```sh
scripts/build_solver_worker.sh
.venv/bin/python scripts/probe_solver_worker.py
```

Restart `scripts/run_api.py` after building. `GET /v1/health` will then report `"solver":"available"`. Submit visual or headless jobs to `POST /v1/solver/jobs`; visual jobs retain periodic progress snapshots, while headless jobs retain only the final result. The web app's Train tab can run, visualize, bypass the cache for, and cancel these solves. See `reports/SOLVER-POC.md` for the current scope and licensing notes.

Training spots are available from `GET /v1/training/spots`. Use `source=curated` for maintained teaching positions or `source=random&seed=<integer>&count=<1-20>` for deterministic generated turn spots.

Run `.venv/bin/python scripts/verify_solver_goldens.py` to compare fresh native solves with the versioned curated reproducibility baselines. Independent-solver evidence and its current limitations are documented in `reports/SOLVER-POC.md`.

The first model-training worker implements tabular CFR for Kuhn poker through versioned JSON Lines contracts. See `reports/MODEL-TRAINING.md` for the request format, mathematical validation, and checkpoint gate.

The local API persists model-training runs separately in `data/training-jobs.sqlite3`. It supports job status, cancellation, checkpoint retrieval, and resuming a completed checkpoint to a larger iteration target.

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
- Six-max cash game with 100 big-blind starting stacks, no rake or antes.
- Local execution where practical, with server-side model inference and solving supported when compute or packaging requires it.
- Provider-neutral strategy API so downloaded policies, local solvers, and our own trained models can be compared using the same states and actions.
