# Postflop solver comparison

## Decision

Use `b-inary/postflop-solver` as the Phase 1/4 integration candidate, behind an isolated local or remote provider service. Do not adopt TexasSolver as the primary training-label engine.

This is a technical selection, not legal advice. Before public hosted deployment, confirm the AGPL source-offer and distribution approach with counsel or a qualified license reviewer.

## Comparison

| Criterion | `postflop-solver` | TexasSolver |
|---|---|---|
| Algorithm | Discounted CFR, γ=3.0 | CFR-family C++ solver |
| Integration | Direct Rust library API; native or WASM wrappers | Console command file, JSON dump, C++/cross-language paths |
| Strategy access | Actions, per-hand strategy, equity, EV, exploitability | JSON strategy dump; overall EV visibility has historically been weaker |
| Abstraction | No card abstraction; chance isomorphism | Configured postflop tree/ranges |
| Performance evidence | Project comparison reported 1.25 GB and 21.1 s to 0.5% in 16-thread WASM mode | Same comparison reported 2.84 GB and 67.1 s |
| Cross-check evidence | Project comparison reported close agreement with PioSOLVER and GTO+ | Same comparison reported a materially different strategy on its test spot |
| License | AGPL-3.0-or-later | AGPL-3.0 |
| Maintenance | Suspended since October 2023 | Still available; project points to a newer GPU product |
| Current-machine build | Blocked until Rust is installed | Would require a C++/Qt build or downloaded console release |

Performance figures above are upstream self-reported and must be reproduced on our hardware before being treated as benchmarks.

## Integration implications

- Pin the exact Rust revision and wrap it behind our provider protocol.
- Keep the AGPL solver service source separable and publish corresponding source when required.
- Treat solver configuration as part of the answer: ranges, board, tree, pot, stack, rake, numeric compression, iterations, and exploitability target.
- Reject exercises lacking defensible starting ranges.
- Estimate memory before allocation and enforce worker limits.
- Cache completed solves by a canonical configuration hash.
- Cross-check golden spots against at least one independent solver before using EV loss to grade users.

## Why not browser-only WASM initially

The same engine can compile to WASM, but server/local-worker execution is preferable initially because it centralizes resource limits, caching, revision control, and result verification. A browser build remains a future offline option.

