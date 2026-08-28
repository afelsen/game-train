# Native postflop solver proof of concept

Status: worker and transport contract implemented on `codex/solver-poc`.

## Outcome

The pinned `b-inary/postflop-solver` source builds as a separate Rust executable and solves a reproducible heads-up turn spot locally. The worker reads one versioned JSON request on standard input and emits JSON Lines events on standard output. The Python API starts it out of process, so the web application does not load native solver state into its own process.

Two modes use the same solve configuration and produce the same final result:

- `visual` emits `started`, periodic `progress`, and `complete` events for a future training visualization.
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
- `GET /v1/health` reports whether the native worker binary was found when the API started.

Jobs and events are currently process-local. Durable caching, cancellation, streaming transport, curated/random spot generation, and the browser visualization remain Phase 4 work.

## Compatibility and licensing

The pinned solver is AGPL-3.0-or-later. Keep the solver component and its corresponding source available as required, and perform a dedicated license review before any hosted deployment. The current Rust toolchain requires the explicit `-A dangerous-implicit-autorefs` compatibility allowance for the pinned upstream revision; the build script contains that flag without modifying vendored source.

## Strategy-reference follow-up

The Phase 4 plan now includes an equity calculator. It should support exact enumeration when tractable and deterministic sampling otherwise, and clearly label inputs, method, sample count, and uncertainty. This is scheduled after the worker pipeline so it does not interrupt the current solver integration.
