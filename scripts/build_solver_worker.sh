#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cargo_bin="${CARGO_BIN:-$HOME/.cargo/bin/cargo}"

RUSTFLAGS="${RUSTFLAGS:-} -A dangerous-implicit-autorefs" \
  "$cargo_bin" build --release --manifest-path "$project_root/solver_worker/Cargo.toml"

echo "Solver worker: $project_root/solver_worker/target/release/game-trainer-solver-worker"
