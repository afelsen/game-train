# Phase 0 technical spike

Status: complete, with native Rust solver build deferred until the Rust toolchain is installed.

## Environment

- Working runtime: Anaconda Python 3.11.5.
- Local virtual environment: `.venv` (ignored by Git).
- Node was not installed when the spike began, so no frontend framework is selected yet.
- Git 2.39.5 is installed. The repository is initialized on branch `codex/phase-0`.

## Pinned candidates

### Fullhouse Bot

- Revision: `e504793d480b1b975f25258d25939b45c6dbd5a4`.
- Checkpoint: `data/deep_cfr_model.npz`.
- Checkpoint SHA-256: `1102326b68da95564de147106612df71cb891b42f0726ba0212d3b9a5bcae295`.
- Contract: 51 float features to five abstract actions.
- License: repository-authored bot, training, tooling, tests, and docs are MIT. `engine_vendored` is explicitly excluded and will not be reused.
- Key risk: the model was trained for six-player NLHE. Its encoder accepts a two-player-shaped state, but that alone cannot validate heads-up strategy quality.

Decision: retain as a candidate comparison checkpoint; do not call it an optimal heads-up provider.

### RLCard Leduc CFR

- Revision: `d7d0a957baf4cc7225a50522adb0164bf130a9d0`.
- License: MIT.
- Bundled CFR state: average policy, current policy, regrets, and iteration pickles.
- Security constraint: Python pickle can execute code. Load only pinned artifacts whose hashes match the manifest; never accept arbitrary uploaded pickles.
- Game mismatch: Leduc is not NLHE.

Decision: accept as a reference-only CFR/provider-contract fixture.

## Contract decisions

- JSON Schema draft 2020-12, contract version `1.0.0`.
- Separate strategy request, strategy response, and model manifest schemas.
- Each provider declares player counts, streets, stack-depth support, encoder, action abstraction, provenance, hashes, and limitations.
- Provider capability mismatch must return `unsupported`.
- Strategy responses distinguish abstract actions from mapped legal actions and report whether translation was exact.
- Model execution is transport-neutral. Providers may run in-process, in a local isolated worker, or behind an authenticated server API.
- Local execution is preferred for small policies and development, but server-side inference/solving is explicitly permitted for large or GPU-backed providers.

## Remaining Phase 0 work

Phase 0 selected `b-inary/postflop-solver` over TexasSolver and defined the transport-neutral provider protocol. Repeatability and artifact-integrity checks are automated.

Deferred prerequisites:

1. Install Rust before native solver build and benchmark work.
2. Install Node before selecting and scaffolding the browser UI.
3. Perform a dedicated AGPL deployment review before making a modified solver available as a hosted network service.

## Exit recommendation

Proceed to Phase 1: implement the authoritative deterministic heads-up engine. In parallel, install Rust and build a minimal `postflop-solver` provider proof of concept; it is not on the critical path for basic engine work.
