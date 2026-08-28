# Phase 2: provider integration and game service

Status: complete.

## Delivered

- Versioned provider interface with capability checks.
- Registry that rejects unsupported games, player counts, and streets before inference.
- Normalized strategy responses conforming to the Phase 0 wire schema.
- Shared five-action mapping into exact engine actions.
- Pot-relative bet and raise translation with legal min/max clamping.
- Deterministic strategy sampling for reproducible bot play.
- Uniform-random and check/call baseline providers.
- Experimental Fullhouse Deep-CFR adapter.
- In-memory game service that owns authoritative hand state, observations, actions, provider requests, and monotonic request IDs.
- Bot-vs-bot service demo.

## Fullhouse checkpoint decision

The downloaded Fullhouse checkpoint successfully consumes our translated heads-up states and emits normalized strategies. It remains explicitly experimental because its documented training domain is six-player NLHE.

Safeguards:

- Hidden from normal provider listings.
- Every response has `exactState: false`.
- Every response warns that heads-up quality is unvalidated and forbids using it to grade learners.
- Illegal abstract action mass is removed and remaining mass is renormalized.
- Mapped output is checked against the authoritative engine's legal actions.

RLCard remains in its separate seeded Leduc reference harness. It cannot be routed into an NLHE hand because the registry rejects its game domain.

## Action translation v1

- `fold` maps only to a legal fold.
- `check-call` maps to check when free, otherwise call.
- `bet-half-pot` and `bet-pot` map to engine `raise-to` actions.
- For an unopened street, sizing is a fraction of the current pot.
- Facing a wager, sizing is a fraction of the pot after calling, added above the current bet.
- Targets clamp to the engine-provided minimum and maximum raise.
- `all-in` maps to the engine all-in action; a short all-in call may map to call.
- Probability mass without a legal mapping is discarded, then legal mass is normalized.

## Trust and deployment boundary

- The in-process request includes a trusted `HandState` reference for local adapters. It must never be serialized over the wire.
- Remote providers receive only the player-safe observation and the public rules/action contract.
- The service owns all state mutation; providers return recommendations, never mutated game state.
- Experimental providers are opt-in and excluded from default discovery.

## Verification

The 20-test suite covers:

- Phase 0 artifact and model reproducibility.
- Phase 1 scenario and 2,500-hand randomized engine invariants.
- Action sizing and normalization.
- Capability rejection.
- Fullhouse inference legality and schema validation.
- 100 complete sampled provider-driven hands with exact replay.

## Exit recommendation

Proceed to the first HTTP/WebSocket application layer and playable browser table. Keep persistence in memory for the first UI vertical slice, then add SQLite hand history after the interaction contract stabilizes.

