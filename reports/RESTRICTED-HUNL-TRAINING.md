# Restricted heads-up hold'em training contract

The first hold'em policy will deliberately solve a small, measurable postflop game rather than claim general heads-up no-limit coverage. Its machine-readable contract is `manifests/restricted-hu-nlhe-flop-cfr-v1.json`; incompatible checkpoints must be rejected rather than silently translated.

## Supported game

- Heads-up, 100 BB, 0.5/1 blinds, no rake.
- A single-raised-pot flop rooted at `Td 9d 6h`, including global suit-isomorphic versions of that two-tone board.
- Fixed OOP and IP ranges from the manifest, with uniform weight across expanded legal combinations.
- Exact card removal and exact remaining-deck chance outcomes on turn and river.
- A fixed 5.5 BB root pot and 97.25 BB effective stack.
- Postflop only. This artifact cannot answer preflop or unrelated-board requests.

This scope is small enough to test end-to-end—tree construction, CFR traversal, persistence, inference, and solver comparison—while exercising real hold'em card removal and multi-street decisions.

## State and action identity

`game_trainer.nlhe_abstraction.encode_information_set` validates states and produces canonical JSON plus its SHA-256 digest. Suits are labeled by first public appearance and then private appearance, so globally suit-isomorphic states share an identity. Numeric values are stored as integer quarter-big-blind units; this exactly represents the 97.25 BB root stack.

History entries use `street:position:action`, for example `flop:oop:check`. The initial action set is:

- No wager faced: check, 50% pot, 100% pot, or all-in.
- Wager faced: fold, call, raise to 2.5x, or all-in.
- At most one raise per street. After that raise, only fold or call remain.

Human sizes outside the tree map to the closest legal size, with exact ties choosing the larger size. This translation is for compatibility at inference boundaries; training itself uses only abstract actions.

## Checkpoint compatibility

A loadable checkpoint must match the abstraction, encoder, and action versions and include hashes for the manifest, expanded ranges, trainer implementation, and policy artifact. A checkpoint trained against a different tree, range, stack, or encoder must fail closed.

## Evaluation gate

Candidate policies will be compared with the existing postflop solver over 50 held-out compatible boards. Acceptance requires:

- mean action-distribution L1 distance no greater than 0.18;
- range-weighted EV loss no greater than 0.08 BB;
- byte-identical artifacts for duplicate seeded runs.

These are initial engineering gates, not proof of equilibrium or optimal full-game play. Thresholds may tighten after the evaluation harness produces a stable baseline.

## Next implementation milestone

Build the deterministic game tree and fixed-range combo expander behind this contract, then add external-sampling MCCFR traversal, checkpoint save/resume, and the held-out solver evaluator. Only after that policy passes the gate should it become selectable in Play or Human Training.
