# Game Trainer: Poker v1 Plan

## 1. Outcome

Build an educational heads-up no-limit Texas Hold'em application in which a learner can:

1. Play against a bot.
2. Let a bot play either seat.
3. Request strategy assistance while playing.
4. Practice generated situations and receive feedback based on action probability and expected-value loss.
5. Compare multiple strategy providers on identical, replayable game states.

The architecture must support our own CFR/Deep-CFR model later without coupling the UI or poker rules engine to a particular checkpoint format.

## 2. Fixed v1 game definition

- Two-player no-limit Texas Hold'em cash game.
- 100 big-blind starting stacks.
- Small blind: 0.5 BB; big blind: 1 BB.
- No rake, antes, straddles, rebuy logic, or tournament utility.
- One hand at a time with alternating button.
- Bet sizes represented internally as exact chip amounts.
- Initial strategy action abstraction: fold, check/call, bet 50% pot, bet 100% pot, and all-in.
- Off-tree human bets remain legal in the game engine but must be explicitly translated before a model is queried.

These settings are part of the model contract, not merely UI defaults.

## 3. Architecture

### 3.1 Poker engine

The engine is the source of truth and must be independent of every model. It will provide:

- Deterministic seeded dealing and complete hand replay.
- Immutable public action history.
- Strict legal-action and minimum-raise validation.
- Showdown evaluation, folds, all-ins, refunds, and chip conservation.
- Separate public state and per-player observations to prevent hidden-card leakage.
- Serialization suitable for fixtures, saved exercises, and model evaluation.

Even though v1 is heads-up, the data representation should not make side pots or additional seats impossible later.

### 3.2 Strategy provider boundary

Every bot, solver, and trained checkpoint will implement a versioned interface with:

- Input: ruleset ID, public state, acting player's observation, action history, stacks, pot, legal actions, and optional ranges.
- Output: probabilities over abstract actions, mapped legal actions, optional action EVs, model metadata, inference time, and approximation diagnostics.
- Capability manifest: supported game, seats, streets, stack depths, action abstraction, encoder version, license, checkpoint checksum, and runtime requirements.

The router must return `unsupported` rather than silently advise on a state outside a provider's contract.

### 3.3 Application and deployment

- The browser UI can initially be served from localhost, but the client/server contract must also support hosted deployment.
- The authoritative game engine may run locally during development and server-side in a hosted version.
- Strategy providers are transport-neutral: in-process, isolated local worker, or authenticated server API.
- WebSocket or event-stream updates handle games and longer solver operations.
- Models remain behind backend adapters; the browser never loads Python pickle files or model-specific state.
- Solver/model workers are isolated from interactive game handling so long solves cannot freeze the table.
- Server-side inference is acceptable for GPU-backed models, large checkpoints, or solvers that are impractical to package locally.

### 3.4 Storage

Start with SQLite and filesystem artifacts during development, behind storage interfaces that can move to a hosted database/object store:

- Hands and deterministic replay seeds.
- Decisions and provider responses.
- Training attempts and EV loss.
- Model manifests, checksums, and benchmark results.
- Cached solver results keyed by the complete solve configuration.

## 4. Initial open-source comparison models

We will begin with two deliberately different providers.

### Model A: Fullhouse Bot Deep-CFR checkpoint

Repository: `advitrocks9/fullhouse-bot`

Why include it:

- Ships a compact `deep_cfr_model.npz` runtime artifact.
- Documents a 51-feature encoder and five abstract actions.
- Pure NumPy inference is practical locally.
- Represents the downloadable-policy path we ultimately want for our own model.

Audit before adoption:

- Confirm repository and checkpoint license/redistribution terms.
- Pin a commit and record file checksums.
- Reproduce its feature vector from documented runtime code.
- Determine whether its six-player training assumptions can validly accept a heads-up state. If not, keep it only as a controlled benchmark and do not expose its output as heads-up advice.
- Measure legality, determinism, latency, and action distributions on golden fixtures.

### Model B: RLCard pretrained Leduc CFR policy

Repository: `datamllab/rlcard`; model ID `leduc-holdem-cfr`.

Why include it:

- Mature MIT-licensed environment and a bundled pretrained CFR policy.
- Small enough to validate strategy plumbing, mixed-action sampling, replay, and exploitability-related tests.
- Provides a known end-to-end CFR reference before attempting full Hold'em training.

Limitation:

- Leduc is not Texas Hold'em. It will be a contract/test provider and an optional miniature teaching lab, not an opponent in the NLHE table.

### Local solving baseline

In addition to those downloaded artifacts, integrate an open-source heads-up postflop CFR solver (evaluate `TexasSolver` and `wasm-postflop`). This is generated computation rather than a pretrained model, but it supplies much more defensible labels for training exercises. License, callable interface, result format, convergence controls, and local resource use will decide which solver is selected.

## 5. Model audit gate

No provider may be called “optimal” or used to grade learners until it passes the applicable checks:

1. License and redistribution review.
2. Reproducible installation from a pinned revision.
3. Checkpoint checksum and model card.
4. Encoder/action-contract tests.
5. Illegal-action rate of zero after mapping.
6. Stable probabilities under deterministic inference.
7. Latency and memory measurements on the target machine.
8. Agreement testing against an independent solver on supported states.
9. Poker-strength evaluation using duplicate hands, bb/100 confidence intervals, and fixed opponents.
10. Explicit UI labeling of exact solves, approximate solves, pretrained policy output, and fallbacks.

## 6. Delivery phases

### Phase 0: Repository and technical spike

- Initialize the repository, formatter, test runner, and architecture decision records.
- Choose the TypeScript UI/backend boundary and the isolated Python/Rust model worker protocol.
- Create versioned schemas for cards, actions, observations, hands, strategy requests, responses, and model manifests.
- Download and pin the two comparison artifacts after verifying licenses.
- Produce a model compatibility and benchmark report.

Exit criterion: both artifacts load reproducibly through adapters, or a documented audit rejects and replaces an artifact.

### Phase 1: Authoritative heads-up engine

- Implement hand lifecycle and legal actions.
- Add a well-tested hand evaluator or wrap a permissively licensed one.
- Implement seeded replay and JSON fixtures.
- Add property tests for chip conservation, card uniqueness, legal transitions, minimum raises, and terminal states.
- Add simple random and rule-based bots.

Exit criterion: thousands of seeded hands complete without invariant violations and can be replayed byte-for-byte at the semantic state level.

### Phase 2: Provider framework

- Implement the provider interface, manifests, registry, action mapper, and capability checks.
- Add the Fullhouse checkpoint adapter subject to the heads-up compatibility result.
- Add the RLCard/Leduc reference adapter in the test lab.
- Persist provider requests/responses with timing and version metadata.

Exit criterion: the same NLHE fixture can be routed to every compatible provider and incompatible providers are rejected clearly.

### Phase 3: Play interface

- Build the table, betting controls, bot seats, hand history, and replay.
- Support human-vs-bot, bot-vs-bot, and bot assistance for the human seat.
- Display mixed strategies without forcing the highest-frequency action.
- Mark translated/off-tree advice and unsupported states.

Exit criterion: a complete heads-up session works locally and every decision is reproducible from stored state.

### Phase 4: Solver-backed training mode

- Integrate the selected postflop solver in a worker process.
- Define/capture ranges and solve configurations explicitly.
- Cache solved spots.
- Generate curated and random supported situations.
- Grade with EV loss when action EVs are available; otherwise show strategy frequencies without a false correctness score.
- Add spaced repetition based on the user's previous high-loss decisions.

Exit criterion: a user can complete a training session and inspect a reproducible solver-backed explanation for every graded decision.

### Phase 5: Our first trained policy

- Begin with Kuhn and Leduc CFR to validate our trainer against known game values/exploitability.
- Train a heads-up NLHE blueprint using an explicit action/card abstraction.
- Version the trainer, encoder, abstraction, weights, and evaluation suite as one inseparable release.
- Compare against the downloaded checkpoint, rule bots, and solver samples.
- Add online resolving only after the static blueprint is measurable and stable.

Exit criterion: our checkpoint beats agreed baselines with confidence intervals and meets predetermined solver-agreement/exploitability proxies. It remains labeled experimental until independently validated.

## 7. Training approach for our model

Use a staged path rather than jumping directly into full HUNL:

1. Tabular CFR/CFR+ on Kuhn poker.
2. Tabular or external-sampling MCCFR on Leduc.
3. Heads-up NLHE subgames with fixed ranges and action trees.
4. A coarse full-game blueprint using external-sampling Linear MCCFR or Deep CFR.
5. Depth-limited postflop resolving with range tracking and carefully defined leaf values.

Every stage must have a measurable evaluation target. Neural training loss alone is not evidence of poker strength.

## 8. Product language and safety boundary

- Describe outputs as approximate equilibrium strategies unless an exact/validated solve justifies stronger language.
- Keep the product isolated from poker clients: no screen reading, hand capture, overlays, automated input, or real-money integrations.
- Do not market a community checkpoint as GTO based on self-reported win rates.
- Explanations should distinguish mathematical inputs (pot odds, equity, range distributions) from pedagogical summaries.

## 9. Immediate next work package

1. Initialize the repository and baseline monorepo layout.
2. Write the JSON schemas, provider manifest format, and transport-neutral provider protocol first.
3. Audit Fullhouse Bot and RLCard licenses, checkpoints, and runtimes.
4. Build tiny adapter probes that load each artifact and return normalized action distributions.
5. Evaluate `TexasSolver` versus `wasm-postflop` for local integration.
6. Produce an evidence-backed comparison report and lock the v1 technical stack.
7. Then implement the deterministic heads-up poker engine.

## 10. Decisions deferred until the technical spike

- Exact frontend framework and whether the local backend is TypeScript, Python, or a split service.
- Fullhouse checkpoint suitability for heads-up play.
- TexasSolver versus `wasm-postflop` as the initial solver.
- Bet translation policy for human off-tree actions.
- Compute budget and hardware target for training our first NLHE blueprint.
