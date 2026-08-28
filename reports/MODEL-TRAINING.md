# Model Training

## Kuhn CFR foundation

The first Train Policy engine is a deterministic, full-tree tabular CFR implementation for two-player Kuhn poker. It exists to verify the training pipeline against a game with a known value before introducing sampling, neural approximation, or Hold'em abstractions.

The worker reads one `training-run-request/v1` JSON object on standard input and writes `training-run-event/v1` JSON Lines to standard output. Visual mode emits started, periodic progress, and complete events. Headless mode emits only the completed artifact. Mode and report cadence are excluded from the configuration identity, so they cannot change the trained strategy.

Run a headless example:

```sh
echo '{"schemaVersion":"1.0.0","game":"kuhn-poker","algorithm":"cfr","mode":"headless","iterations":50000,"seed":7,"reportEvery":1000}' | .venv/bin/python scripts/run_kuhn_trainer.py
```

The completed artifact contains all 12 information sets, average action probabilities, the player-zero game value, and exact NashConv exploitability computed by enumerating every pure best response. With seed 7 and 50,000 iterations, the current implementation reaches approximately `-0.055562`, close to Kuhn's known player-zero value of `-1/18`, with exploitability below `0.003`.

No style or “personality” parameter is accepted at this stage. Future alternative objectives must be explicit in the run contract and must not be described as equilibrium CFR when they change the optimized utility.

## Checkpoints

Every completed run now includes a versioned checkpoint containing regret sums, average-strategy sums, completed iterations, seed, and an integrity hash. Shuffle order is derived deterministically from the seed and absolute iteration number, so no runtime-specific random-state encoding is required.

A checkpoint may be supplied as the optional `checkpoint` field of a later request with the same seed and a greater or equal target iteration count. Integrity, game, algorithm, seed, and iteration bounds are validated before training resumes. Automated tests prove that a 2,000-iteration checkpoint resumed to 5,000 iterations produces exactly the same checkpoint, strategy, values, and artifact hash as an uninterrupted 5,000-iteration run.

## Next gate

Training runs are now exposed through a persistent job API backed by `data/training-jobs.sqlite3`:

- `POST /v1/training/jobs` starts a versioned run.
- `GET /v1/training/jobs` lists recent persistent runs.
- `POST /v1/training/jobs/{jobId}/register` promotes a completed policy into the versioned model registry.
- `GET /v1/training/models` lists registered policies and their exact evaluation results.
- `GET /v1/training/jobs/{jobId}` returns status and accumulated events.
- `POST /v1/training/jobs/{jobId}/cancel` terminates an active worker.
- `GET /v1/training/jobs/{jobId}/checkpoint` returns the latest durable checkpoint.
- `POST /v1/training/jobs/{jobId}/resume` creates a new run with the stored checkpoint and a higher iteration target.

Completed jobs and checkpoints remain readable after an API restart. Jobs interrupted by a restart are marked failed rather than remaining indefinitely active.

The Model Training → Train Policy interface exposes configurable iterations/seeds/report cadence, live exact exploitability, cancellation, checkpoint download, checkpoint resume, recent run history, and a representative final-policy preview. Completed policies can be saved into a persistent model registry and compared side by side by exploitability, game value, iterations, and information-set action frequencies. Every policy-training run reports chartable progress. The visual/headless distinction is reserved for Subgame Solver, where visual mode will render decisions on the poker table.

## Leduc CFR

The same job and checkpoint contract now supports two-player Leduc Hold'em using the pinned RLCard implementation and its standard six-card, two-round limit ruleset. Leduc checkpoints are stored as integrity-checked JSON, resume deterministically, and can be promoted into the model registry. Progress is evaluated as average payoff against the pinned pretrained RLCard CFR reference policy; it is deliberately not labeled exploitability.

Registered checkpoints are usable through `POST /v1/training/models/{modelId}/strategy`, which accepts an artifact information-set key and optional legal-action subset, then returns normalized policy probabilities. Game identifiers remain enforced so Leduc policies cannot be routed into the no-limit hold'em table.
