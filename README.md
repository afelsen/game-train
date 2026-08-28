# Game Trainer

An educational game simulator and strategy trainer. The first game is heads-up no-limit Texas Hold'em cash poker; backgammon can later use the same game/provider architecture.

See [PLAN.md](./PLAN.md) for the product and implementation plan.

## Initial product boundary

- Educational simulation only; no real-money client integration or automation.
- Heads-up cash game, initially 100 big-blind effective stacks, no rake or antes.
- Local execution where practical, with server-side model inference and solving supported when compute or packaging requires it.
- Provider-neutral strategy API so downloaded policies, local solvers, and our own trained models can be compared using the same states and actions.
