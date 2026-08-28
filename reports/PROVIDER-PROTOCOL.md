# Strategy provider protocol v1

The poker engine and UI communicate only with a provider gateway. A provider implementation may run in the gateway process, in an isolated local worker, or on a remote server.

## Design rules

- JSON request and response bodies use the schemas in `schemas/`.
- Monetary values are integer chips. Never send floating-point chip amounts.
- Cards use rank plus lowercase suit, for example `As` and `Td`.
- A request contains only the acting player's private observation. Opponent hole cards must never cross the provider boundary.
- Every provider checks its capability manifest before inference.
- Unsupported states produce a normal `unsupported` response, not an invented fallback strategy.
- Probabilities must be finite, non-negative, and sum to one within `1e-6` across returned legal abstract actions.
- Solver results are reproducible only when ranges, board, pot, stack, action tree, rake, convergence target, iteration cap, solver revision, and numeric mode are all part of the cache key.

## HTTP surface

### `GET /v1/providers`

Returns the available model manifests. It contains no secrets or runtime paths.

### `POST /v1/strategy`

Accepts `strategy-request.schema.json` and returns `strategy-response.schema.json`. Use this for static policies and cached/fast solves.

### `POST /v1/solve-jobs`

Creates a longer-running solve. The body extends the strategy request with solver-only configuration:

```json
{
  "strategyRequest": {},
  "ranges": {"oop": "...", "ip": "..."},
  "tree": {
    "flopBetSizes": [0.5, 1.0],
    "turnBetSizes": [0.5, 1.0],
    "riverBetSizes": [0.5, 1.0],
    "includeAllIn": true
  },
  "limits": {
    "maxIterations": 1000,
    "targetExploitabilityPotFraction": 0.005,
    "maxMemoryBytes": 4294967296,
    "timeoutMs": 120000
  }
}
```

Returns `202 Accepted` with an opaque job ID. The server validates ranges and estimates memory before queueing.

### `GET /v1/solve-jobs/{jobId}`

Returns `queued`, `running`, `complete`, `failed`, or `cancelled`, plus progress diagnostics. A completed job embeds a strategy response and a solver result reference.

`POST /v1/solver/jobs/{jobId}/cancel` moves an active job to `cancelled` and terminates its worker process. Completed solves are cached durably by a canonical configuration key that excludes presentation-only visual mode and progress-report frequency.

### `DELETE /v1/solve-jobs/{jobId}`

Requests cancellation. Cancellation is idempotent.

## Isolation and security

- Do not deserialize user-supplied pickle, NumPy object arrays, bincode, or solver-tree files.
- Provider artifacts are installed by operators and verified against manifest hashes.
- Remote endpoints require authentication, request-size limits, timeouts, concurrency quotas, and rate limits.
- Solver workers get explicit CPU and memory limits.
- The gateway redacts filesystem paths and stack traces from API responses.
- Cache entries are scoped by provider revision and full solve configuration.

## Deployment modes

| Mode | Suitable providers | Notes |
|---|---|---|
| In process | Small NumPy policies | Lowest latency; a model failure can affect the gateway. |
| Local worker | Python policies and native solvers | Default development mode; process isolation and cancellation. |
| Remote provider | GPU models and expensive solvers | Same JSON contract; add authentication, quotas, observability, and license/source compliance. |
