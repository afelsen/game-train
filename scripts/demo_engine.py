#!/usr/bin/env python3
"""Play and replay one deterministic heads-up checkdown."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game_trainer.poker import Action, HandState


def main() -> None:
    hand = HandState(seed=20260828)
    hand.apply(Action.call())
    hand.apply(Action.check())
    while not hand.terminal:
        hand.apply(Action.check())

    serialized = hand.to_dict()
    HandState.replay(serialized)
    print(json.dumps(serialized, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
