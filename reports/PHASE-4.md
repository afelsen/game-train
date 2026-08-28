# Phase 4: bet sizing and durable review

Status: complete for local development.

## Delivered

- Legal custom raise-to sizing with a slider, numeric entry, and half-pot, three-quarter-pot, and pot presets.
- Engine observation fields required to calculate legal pot-based sizing without exposing private state.
- SQLite hand summaries and event-by-event player-safe observation snapshots.
- Saved model strategy beside the hero action it informed.
- Review mode with recent-hand selection and previous/next replay controls.
- History list and detail API routes.
- Durable, restart-safe hand IDs and a configurable database location.

## Storage contract

The API writes to `data/game-trainer.sqlite3` by default. Set `GAME_TRAINER_DB_PATH` to use another path. The database contains:

- `hands`: one durable summary and authoritative final state per hand.
- `hand_events`: ordered action, player-safe observation, and optional strategy snapshots.

The database is intentionally local and ignored by Git. History queries use indexes for recent hands and ordered events; their query plans are covered by tests. A hosted version can keep the same API contract while moving persistence to a managed SQL store.

## API additions

- `GET /v1/history?limit=20`
- `GET /v1/history/{sessionId}`

Existing `POST /v1/hands/{sessionId}/actions` accepts any integer `amount` inside the engine-provided `raise-to` bounds.

## Verification

- 25 Python tests pass, including SQLite round-trip, index-plan, custom-raise, and replay API coverage.
- Application lint passes.
- Production Vinext build passes.

## Next recommendation

Phase 5 should turn the current training placeholder into decision drills. Sample spots from saved/reproducible hands, record the user's action before revealing advice, and grade only against a validated heads-up provider. Until that model is ready, feedback should compare action distributions without claiming solver-optimal scores.
