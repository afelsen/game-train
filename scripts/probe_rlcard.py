#!/usr/bin/env python3
"""Load RLCard's pinned pretrained Leduc CFR policy and play one episode."""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor/rlcard"
sys.path.insert(0, str(VENDOR))

import rlcard  # noqa: E402
import rlcard.models  # noqa: E402
import numpy as np  # noqa: E402


def main() -> None:
    # RLCard's environment-local seed does not cover the CFR agent's global
    # NumPy sampling path, so both RNG sources are seeded explicitly.
    random.seed(17)
    np.random.seed(17)
    started = time.perf_counter()
    model = rlcard.models.load("leduc-holdem-cfr")
    env = rlcard.make("leduc-holdem", config={"seed": 17})
    env.set_agents(model.agents)
    trajectories, payoffs = env.run(is_training=False)
    elapsed_ms = (time.perf_counter() - started) * 1000
    decision_count = sum(len(player_trajectory) // 2 for player_trajectory in trajectories)
    result = {
        "artifact": "rlcard-leduc-cfr-d7d0a95",
        "seed": 17,
        "payoffs": [float(value) for value in payoffs],
        "decisionCount": decision_count,
        "terminal": True,
        "elapsedMsIncludingLoad": elapsed_ms
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
