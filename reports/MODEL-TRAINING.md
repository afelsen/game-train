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

## Next gate

Add a versioned checkpoint containing regret sums, average-strategy sums, completed iterations, and deterministic random state. Saving and resuming must produce the same final artifact as an uninterrupted run before the trainer is connected to the Model Training UI.
