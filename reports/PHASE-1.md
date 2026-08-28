# Phase 1: authoritative heads-up engine

Status: complete.

## Delivered

- Pure Python heads-up NLHE state machine with no UI or model dependencies.
- Deterministic seeded shuffle, hole-card dealing, burns, and board runout.
- Correct heads-up preflop/postflop action order.
- Legal fold, check, call, raise-to, and all-in actions.
- Minimum full raises and incomplete all-in raises.
- Fold settlement, showdown evaluation, split pots, odd-chip rule, and unmatched-contribution refunds.
- Player-safe observations that exclude opponent cards and the undealt deck.
- Complete trusted serialization and exact semantic replay.
- Scenario tests plus 2,500 randomized legal hands with invariant checking and replay.

## Verification

Run:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/demo_engine.py
```

The suite includes all Phase 0 artifact/model checks plus Phase 1 engine tests.

## Exit decision

Proceed to the provider integration layer and local game service. Before using the engine for external evaluation, add differential tests against an independent established Hold'em engine for selected betting and showdown fixtures.

