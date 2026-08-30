# Two-to-six-player NLHE engine contract v2

## Scope

The engine implements one deterministic two-to-six-player no-limit Texas Hold'em cash hand. The Play MVP uses six seats. It is authoritative for cards, legal actions, betting transitions, side pots, showdown, payouts, and replay. Models and UI code submit actions to the engine rather than mutating state.

## Fixed rules

- Two to six seats numbered from `0`.
- Integer chip accounting.
- Configurable positive starting stacks and blinds; default stacks are 10,000 with 50/100 blinds.
- Heads-up: the button posts the small blind and acts first preflop.
- Multiway: the small blind is left of the button, the big blind is next, and action starts left of the big blind.
- Postflop action starts with the first active player left of the button.
- No rake or antes.
- Standard minimum full-raise rule.
- An all-in below the normal minimum is allowed when it is the player's complete remaining stack.
- Showdown contributions are divided into layered main and side pots. Only non-folded contributors to a layer are eligible to win it.
- On a tied pot with an odd chip, the first seat clockwise from the button receives it.

## Action API

The engine exposes five action types:

| Action | Amount semantics |
|---|---|
| `fold` | No amount. Legal only when facing a wager. |
| `check` | No amount. Legal only when the amount to call is zero. |
| `call` | Engine computes the lesser of amount owed and remaining stack. |
| `raise-to` | Integer total committed by the player on the current street. |
| `all-in` | Engine computes the player's maximum street commitment. |

`legal_actions()` returns the applicable actions with call amount and raise interval. Provider action translation must map into this exact legal set.

## Determinism and replay

- A local `random.Random(seed)` instance shuffles the canonical 52-card deck; no global RNG is consumed.
- Dealing includes burn cards before flop, turn, and river.
- `to_dict()` is the complete trusted engine state, including private cards and remaining deck. It must never be sent directly to an untrusted client.
- `observation(seat)` is the player-safe view and excludes every opponent's hole cards and the undealt deck.
- `HandState.replay(serialized)` reconstructs the hand from configuration, seed, and action history, then requires the entire resulting state to match.

## Invariants

The engine checks after construction and every successful action:

- All 52 cards are valid, unique, and accounted for across deck, burns, board, and hole cards.
- Stacks and commitments never become negative.
- Street commitment never exceeds total hand commitment.
- Starting chips equal current stacks plus current commitments.
- Terminal hands have no actor, no pending action, zero pot, and a result.
- Non-terminal acting seats are present in the pending set.

## Trust boundary

- `to_dict()` is for trusted persistence, fixtures, and replay.
- `observation(seat)` is the only state representation intended for a player client or strategy provider.
- The current Python objects are mutable internally; callers must treat them as opaque and use methods. A service adapter will own each hand and return serialized copies.
- Serialized states from external users are not accepted as authority. Reconstruct from the seed/configuration and validate the action log instead.

## Deferred

- Tournament rules, antes, rake, and rebuys.
- Time controls and disconnect handling.
- Learned multiway range tracking; Play currently uses transparent per-seat heuristics.
- Independent differential testing against a second poker engine.
