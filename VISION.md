# game train product vision

## Purpose

game train is an educational platform for learning, practicing, and analyzing strategy games. Poker is the first implementation and backgammon is an intended expansion, but the product is organized around reusable learning experiences rather than around a single game's screens.

The product must clearly separate advice for a learner from analysis of the models that produce that advice. It may use pretrained policies, lightweight local solves, server-side solvers, or our own trained checkpoints behind the same versioned provider boundary.

## Product structure

A game selector sits above four consistent primary tabs. Selecting a game changes the rules engine, available models, exercises, terminology, and analysis tools while preserving the same overall navigation.

1. **Learn** — structured explanations, references, guided lessons, and concept exploration for the selected game.
2. **Play** — normal play against humans or bots, optional strategy assistance, hand/game history, and access to replay/review for completed games.
3. **Train** — human practice: random situations, curated drills, manual situation entry, delayed feedback, mistake tracking, and spaced repetition.
4. **Model** — model analysis: compare policies on identical states, inspect action distributions and EVs, benchmark compatibility and strength, run lightweight local training or subgame solves, and manage analytical artifacts.

Review is not a fifth primary destination. It is reached from Play through the relevant completed hand, match, or session.

## Model analysis boundary

The Model tab is not intended to become a general-purpose large-scale model-training console. Its core job is to help users understand and compare models. It can include bounded computation that supports analysis, including:

- postflop or other game-specific subgame solving;
- small CFR experiments and educational convergence visualizations;
- side-by-side policy, EV, exploitability/proxy, latency, and coverage comparisons;
- checkpoint metadata, compatibility, evaluation gates, and reproducibility results;
- representative state explorers and bot-versus-bot evaluation.

Large blueprint training, distributed sweeps, and expensive checkpoint production can remain offline or server-side workflows. Their resulting artifacts enter the product through the same manifest, validation, and model-registry contracts.

## Multi-game platform contract

Each supported game supplies a module with:

- authoritative rules and legal-action engine;
- public state and player observation schemas;
- deterministic replay and history presentation;
- strategy-provider capabilities and action translation;
- game-specific Learn content and references;
- Play table/board presentation;
- Train situation generators, grading, and feedback;
- Model comparisons, metrics, and optional lightweight solvers;
- terminology, accessibility behavior, and responsive presentation.

Shared platform services own navigation, user progress, artifact storage, model registry, job execution, comparisons, and safety labeling. A model must never be routed across games, rulesets, player counts, or abstractions unless its capability manifest explicitly supports that contract.

## Near-term interpretation

Poker remains the active implementation priority. Existing policy-training and subgame-solver work is retained, but it will ultimately be presented as analytical tooling inside Model rather than as a standalone Model Training product area. This vision update does not interrupt the current restricted hold'em solver-validation work.
