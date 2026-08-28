# Game Trainer

An educational game simulator and strategy trainer. The first game is heads-up no-limit Texas Hold'em cash poker; backgammon can later use the same game/provider architecture.

See [PLAN.md](./PLAN.md) for the product and implementation plan.

## Current implementation

Phase 1 includes a deterministic authoritative heads-up NLHE hand engine under `game_trainer/poker`. Phase 2 adds strategy providers, action translation, and an authoritative game service. Phase 3 adds a playable local browser table under `web/`. Phase 4 adds custom bet sizing and SQLite-backed hand review. Their contracts are documented under `reports/`.

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
