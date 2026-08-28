# game train: Poker v1 Plan

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

### Phase 4: Human Training

- Integrate the selected postflop solver in a worker process.
- Present decision drills separately from model-development tools under a dedicated Human Training tab.
- Place the learner in a curated or seeded-random supported situation and require an action before revealing strategy.
- Offer two execution modes over the same solve contract: visual mode streams convergence and strategy snapshots; headless mode minimizes reporting overhead.
- Define/capture ranges and solve configurations explicitly.
- Cache solved spots.
- Maintain the exact/sampled equity calculator in the strategy reference, with method and sampling uncertainty shown explicitly.
- Add a simple Bayesian/behavioral Villain-range estimator that updates from observed actions; let equity calculations toggle between its predicted range and a uniformly random legal hand.
- Generate curated and random supported situations.
- Support both generated drills and a manual Situation Lab where the learner enters hole cards, board, stacks, pot, and action history to receive estimated ranges, equity, and compatible model predictions.
- Grade with EV loss when action EVs are available; otherwise show strategy frequencies without a false correctness score.
- Add spaced repetition based on the user's previous high-loss decisions.

Exit criterion: a user can complete a training session and inspect a reproducible solver-backed explanation for every graded decision.

### Phase 5: Model Training and our first trained policy

- Add a dedicated Model Training tab, separate from Human Training and normal play.
- Move the current convergence workspace into a Subgame Solver view within Model Training.
- Add a Train Policy view for configuring, starting, cancelling, resuming, and evaluating CFR-family training runs.
- Begin with Kuhn and Leduc CFR to validate our trainer against known game values/exploitability.
- Train a heads-up NLHE blueprint using an explicit action/card abstraction.
- Version the trainer, encoder, abstraction, weights, and evaluation suite as one inseparable release.
- Compare against the downloaded checkpoint, rule bots, and solver samples.
- Add online resolving only after the static blueprint is measurable and stable.
- Allow advanced users to modify objective terms, utility/risk adjustments, sampling distributions, and other exposed training parameters that can produce emergent styles such as aggressive or tight play. Do not impose personality labels or claim equilibrium play when a modified objective intentionally changes the game being optimized.

Exit criterion: our checkpoint beats agreed baselines with confidence intervals and meets predetermined solver-agreement/exploitability proxies. It remains labeled experimental until independently validated.

## 7. Training approach for our model

Use a staged path rather than jumping directly into full HUNL:

1. Tabular CFR/CFR+ on Kuhn poker.
2. Tabular or external-sampling MCCFR on Leduc.
3. Heads-up NLHE subgames with fixed ranges and action trees.
4. A coarse full-game blueprint using external-sampling Linear MCCFR or Deep CFR.
5. Depth-limited postflop resolving with range tracking and carefully defined leaf values.

Every stage must have a measurable evaluation target. Neural training loss alone is not evidence of poker strength.

### 7.1 Product separation

The application will expose four distinct primary experiences:

1. **Play:** play poker against a selected strategy provider, optionally with advice.
2. **Human Training:** practice hidden decisions, reveal solver-backed feedback afterward, and track mistakes and spaced repetition.
3. **Model Training:** develop CFR-family policies, inspect convergence, manage checkpoints, and run solver experiments.
4. **Review:** replay completed hands and inspect previous decisions.

The current Train workspace is a per-situation postflop solver, not a general pretrained model. It will be renamed Subgame Solver and moved under Model Training.

### 7.2 Offline policy training versus live solving

Use both workflows behind the same strategy-provider contract:

- **Offline training:** CFR/CFR+/MCCFR or Deep CFR traverses many game states in advance. Save tabular regret/average-strategy artifacts or neural checkpoints for fast inference in Play and Human Training.
- **Live subgame solving:** solve one explicit range-versus-range situation at request time, cache the result, and use it for analysis, label generation, and validation of the pretrained policy.
- **Hybrid path:** use a saved blueprint for immediate decisions and optional live postflop resolving for supported high-value situations.

Full heads-up no-limit Hold'em is too large for an unabstracted tabular CFR table. The production path must therefore use explicit card/action abstraction, sampling, neural approximation, subgame decomposition, or a combination of them.

### 7.3 Model Training controls and visualization

The Train Policy view will expose only parameters applicable to the selected algorithm and game:

- Game and ruleset: Kuhn, Leduc, restricted NLHE subgame, and later abstracted HUNL.
- Algorithm: CFR, CFR+, external-sampling MCCFR, Linear MCCFR, or Deep CFR as implemented.
- Iteration count, random seed, discount/learning parameters, action abstraction, worker count, evaluation cadence, and checkpoint cadence.
- Start, pause/cancel, resume from checkpoint, and headless versus visual execution.
- Immutable run manifest containing source revision, encoder, abstraction, parameters, seed, and artifact checksums.

Visual mode will show, where meaningful:

- Exploitability or a clearly labeled best-response proxy.
- Cumulative/average regret and strategy change over time.
- Iterations and traversals per second, elapsed time, and memory use.
- Deep-CFR value/advantage loss and replay-buffer statistics.
- Checkpoint events, evaluation results, and strategy snapshots for representative information states.

Headless mode will use the identical training configuration while minimizing retained progress events. Neither mode may change the resulting checkpoint identity.

### 7.4 Staged Model Training delivery

1. Implement tabular CFR for Kuhn poker and verify convergence to the known game value and equilibrium family.
2. Add a visual information-state explorer so every Kuhn regret and average-strategy update can be inspected.
3. Add checkpoint save/resume, deterministic seeds, run manifests, and comparison of two runs.
4. Implement Leduc using tabular CFR+ or external-sampling MCCFR and compare against the RLCard reference policy.
5. Train fixed-range NLHE subgames and compare their strategies and EVs against the validated postflop solver.
6. Design and train the first abstracted HUNL blueprint; expose it to Play only after provider-contract and evaluation gates pass.

### 7.5 Future game and table expansion

- Generalize the poker engine and observation contract from heads-up to tables of two through six players.
- Add seat management, blinds/button rotation, multiway action order, side pots, all-in eligibility, and per-player hidden observations.
- Replace heads-up-only range and equity assumptions with joint/multiway calculations and clearly labeled approximations.
- Require new provider capability manifests and evaluation suites; heads-up checkpoints must never be silently routed into multiway states.

The first Model Training milestone exits when a user can configure a Kuhn CFR run, watch it converge, save/resume its state, and reproduce its final strategy from the run manifest.

## 8. Product language and safety boundary

- Describe outputs as approximate equilibrium strategies unless an exact/validated solve justifies stronger language.
- Keep the product isolated from poker clients: no screen reading, hand capture, overlays, automated input, or real-money integrations.
- Do not market a community checkpoint as GTO based on self-reported win rates.
- Explanations should distinguish mathematical inputs (pot odds, equity, range distributions) from pedagogical summaries.
- The “Your current hand” reference should use precise contextual poker terminology, including pocket pair, paired board, overpair, top/middle/bottom pair, and set versus trips, based on hole-card and board composition.
- Replace the free-form chip amount editor with compact minus/plus controls that step by 0.5 big blinds and clamp to legal minimum, maximum, and all-in amounts.
- Add next-street out counts beside hand-ranking improvement percentages, with outs defined and deduplicated from the known deck.
- Animate chip movement for bets, raises, and calls so action, contribution, and pot changes remain perceptible; respect reduced-motion preferences and never delay engine state updates.
- Visually distinguish hand-ranking probabilities that are above a defensible baseline for the same street/known-card context, and expose the comparison baseline rather than implying a universal average.
- In the educational interface, reveal Villain's folded hole cards by default, with a future realism/privacy toggle if needed.

## 9. Immediate next work package

1. Split the current Train navigation into Human Training and Model Training; move the existing solver lab into Model Training → Subgame Solver.
2. Add a persistent training-job API around the Kuhn worker with cancellation and checkpoint retrieval.
3. Add the Model Training → Train Policy controls and visual/headless progress views.
4. Continue translating richer curated action trees into the independent solver before adding Human Training EV-loss grading.

## 10. Remaining decisions

- Bet translation policy for human off-tree actions.
- Compute budget and hardware target for training our first NLHE blueprint.
- Whether to replace the working polling transport with server-sent events or WebSocket updates.
- Hosted deployment and AGPL compliance review for the selected solver.
