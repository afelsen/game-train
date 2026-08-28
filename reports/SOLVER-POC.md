# Native postflop solver proof of concept

Status: worker and transport contract implemented on `codex/solver-poc`.

## Outcome

The pinned `b-inary/postflop-solver` source builds as a separate Rust executable and solves a reproducible heads-up turn spot locally. The worker reads one versioned JSON request on standard input and emits JSON Lines events on standard output. The Python API starts it out of process, so the web application does not load native solver state into its own process.

Two modes use the same solve configuration and produce the same final result:

- `visual` emits `started`, periodic `progress`, and `complete` events for the Train-tab convergence visualization.
- `headless` suppresses intermediate events and emits only `complete` for batch generation and benchmarks.

The cache identity deliberately excludes mode and progress frequency. Switching visualization on or off therefore cannot create a different strategy artifact.

## Reproducible probe

The fixture `turn-td9d6h-qc.json` solves a fixed turn state for at most 100 iterations. On the initial Apple Silicon development run it used 12,323,112 bytes of uncompressed solver memory, completed in roughly 0.25 seconds, and reported exploitability of approximately 0.836 chips. Timing is informational and will vary by machine.

Run:

```sh
scripts/build_solver_worker.sh
python3 scripts/probe_solver_worker.py
```

The probe validates every event against `schemas/solver-job-event.schema.json` and asserts that visual and headless final results match after excluding elapsed time and the requested mode.

## HTTP contract

- `POST /v1/solver/jobs` validates and queues a solve, returning HTTP 202 and a job ID.
- `GET /v1/solver/jobs/{jobId}` returns status and accumulated events.
- `POST /v1/solver/jobs/{jobId}/cancel` terminates a queued or running worker.
- `GET /v1/health` reports whether the native worker binary was found when the API started.

Jobs, requests, and progress events are stored in `data/solver-jobs.sqlite3`. Completed results are cached by the full solve configuration while deliberately excluding visual/headless mode and reporting frequency. Cache hits receive a new job ID and an immediate completion event; existing job IDs remain inspectable after an API restart. Jobs interrupted by a restart are marked failed rather than left permanently running.

The web application exposes this pipeline in its separate Train tab. Visual mode plots exploitability snapshots and the final root action mix; headless mode runs the identical solve contract without retaining intermediate snapshots. The user can reuse cached solves or deliberately bypass the cache to observe a fresh convergence run, and can cancel an active job. Polling is the current transport.

The Train tab also loads stable curated exercises and can generate deterministic random turn spots. `GET /v1/training/spots?source=curated` returns the maintained set; `source=random&seed=42&count=2` creates replayable unseen spots. Every returned item contains its complete solver request, source metadata, and seed where applicable. Automated tests validate the request schema and card uniqueness, and native smoke runs confirm that the current curated and seeded samples are accepted by the pinned solver. Golden-result cross-checking remains the next Phase 4 gate.

## Compatibility and licensing

The pinned solver is AGPL-3.0-or-later. Keep the solver component and its corresponding source available as required, and perform a dedicated license review before any hosted deployment. The current Rust toolchain requires the explicit `-A dangerous-implicit-autorefs` compatibility allowance for the pinned upstream revision; the build script contains that flag without modifying vendored source.

## Strategy-reference follow-up

The Phase 4 plan now includes an equity calculator. It should support exact enumeration when tractable and deterministic sampling otherwise, and clearly label inputs, method, sample count, and uncertainty. This is scheduled after the worker pipeline so it does not interrupt the current solver integration.
