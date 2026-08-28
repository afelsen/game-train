# Heads-up NLHE engine contract v1

## Scope

The Phase 1 engine implements one deterministic heads-up no-limit Texas Hold'em cash hand. It is authoritative for cards, legal actions, betting transitions, showdown, payouts, and replay. Models and UI code must submit actions to the engine rather than mutating state.

## Fixed rules

- Two seats numbered `0` and `1`.
- Integer chip accounting.
- Configurable positive starting stacks and blinds; default stacks are 10,000 with 50/100 blinds.
- The button posts the small blind and acts first preflop.
- The non-button acts first after the flop.
- No rake or antes.
- Standard minimum full-raise rule.
- An all-in below the normal minimum is allowed when it is the player's complete remaining stack.
- A short all-in call refunds uncontested excess before showdown.
- With only two players there can be no contested side pot; unequal showdown contributions are refunded.
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
- `observation(seat)` is the player-safe view and excludes the opponent's hole cards and undealt deck.
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

## Deferred beyond Phase 1

- Multi-hand sessions and alternating buttons.
- Time controls, disconnects, and persistence service.
- Multi-player pots and side pots.
- Action translation from model abstractions.
- Formal range tracking.
- Independent differential testing against a second poker engine.

