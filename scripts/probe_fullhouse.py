#!/usr/bin/env python3
"""Load the pinned Fullhouse checkpoint and emit one normalized strategy."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor/fullhouse-bot"
sys.path.insert(0, str(VENDOR))

from bot.deep_cfr_lookup import DeepCFRLookup  # noqa: E402

ACTIONS = ["fold", "check-call", "bet-half-pot", "bet-pot", "all-in"]


def main() -> None:
    state = {
        "your_cards": ["As", "Kd"],
        "community_cards": [],
        "pot": 150,
        "your_stack": 9900,
        "your_bet_this_street": 50,
        "amount_owed": 50,
        "min_raise_to": 200,
        "can_check": False,
        "seat_to_act": 0,
        "dealer": 0,
        "street": "preflop",
        "hand_num": 1,
        "action_log": [
            {"action": "small_blind", "seat": 0, "amount": 50},
            {"action": "big_blind", "seat": 1, "amount": 100}
        ],
        "players": [
            {"seat": 0, "stack": 9900, "is_folded": False, "is_all_in": False, "bet_this_street": 50},
            {"seat": 1, "stack": 9900, "is_folded": False, "is_all_in": False, "bet_this_street": 100}
        ]
    }
    started = time.perf_counter()
    model = DeepCFRLookup(VENDOR / "data/deep_cfr_model.npz")
    strategy = model.get_strategy(state)
    elapsed_ms = (time.perf_counter() - started) * 1000
    result = {
        "artifact": "fullhouse-deep-cfr-e504793",
        "probeState": "synthetic heads-up button facing big blind",
        "warning": "The checkpoint was trained for six-player play; successful inference does not establish heads-up validity.",
        "strategy": dict(zip(ACTIONS, map(float, strategy))),
        "probabilitySum": float(strategy.sum()),
        "elapsedMsIncludingLoad": elapsed_ms
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

