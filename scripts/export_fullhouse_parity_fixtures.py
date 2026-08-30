#!/usr/bin/env python3
"""Generate browser/Python parity fixtures for the Fullhouse runtime contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor/fullhouse-bot"
sys.path.insert(0, str(VENDOR))

from bot.deep_cfr_lookup import DeepCFRLookup  # noqa: E402
from bot.features import encode_state_dict  # noqa: E402


CASES = [
    {
        "name": "six-max preflop button facing blind",
        "hand": {
            "button": 0,
            "street": "preflop",
            "board": [],
            "pot": 150,
            "currentBet": 100,
            "lastFullRaise": 100,
            "toAct": 0,
            "seats": [
                {"seat": 0, "stack": 10000, "streetCommitted": 0, "handCommitted": 0, "status": "active", "holeCards": ["As", "Kd"]},
                {"seat": 1, "stack": 9950, "streetCommitted": 50, "handCommitted": 50, "status": "active"},
                {"seat": 2, "stack": 9900, "streetCommitted": 100, "handCommitted": 100, "status": "active"},
                {"seat": 3, "stack": 10000, "streetCommitted": 0, "handCommitted": 0, "status": "active"},
                {"seat": 4, "stack": 10000, "streetCommitted": 0, "handCommitted": 0, "status": "active"},
                {"seat": 5, "stack": 10000, "streetCommitted": 0, "handCommitted": 0, "status": "active"},
            ],
            "actions": [
                {"street": "preflop", "seat": 1, "type": "small-blind", "amount": 50},
                {"street": "preflop", "seat": 2, "type": "big-blind", "amount": 100},
            ],
            "legalActions": [
                {"type": "fold", "amount": None, "minAmount": None, "maxAmount": None},
                {"type": "call", "amount": 100, "minAmount": None, "maxAmount": None},
                {"type": "raise-to", "amount": None, "minAmount": 200, "maxAmount": 10000},
                {"type": "all-in", "amount": 10000, "minAmount": None, "maxAmount": None},
            ],
        },
    },
    {
        "name": "multiway flop facing half-pot bet",
        "hand": {
            "button": 3,
            "street": "flop",
            "board": ["Th", "7c", "2h"],
            "pot": 3300,
            "currentBet": 900,
            "lastFullRaise": 900,
            "toAct": 2,
            "seats": [
                {"seat": 0, "stack": 9700, "streetCommitted": 0, "handCommitted": 300, "status": "folded"},
                {"seat": 1, "stack": 9700, "streetCommitted": 0, "handCommitted": 300, "status": "folded"},
                {"seat": 2, "stack": 9700, "streetCommitted": 0, "handCommitted": 300, "status": "active", "holeCards": ["9h", "8h"]},
                {"seat": 3, "stack": 10000, "streetCommitted": 0, "handCommitted": 0, "status": "folded"},
                {"seat": 4, "stack": 8800, "streetCommitted": 900, "handCommitted": 1200, "status": "active"},
                {"seat": 5, "stack": 8800, "streetCommitted": 900, "handCommitted": 1200, "status": "active"},
            ],
            "actions": [
                {"street": "preflop", "seat": 4, "type": "small-blind", "amount": 50},
                {"street": "preflop", "seat": 5, "type": "big-blind", "amount": 100},
                {"street": "preflop", "seat": 0, "type": "raise-to", "amount": 300},
                {"street": "preflop", "seat": 1, "type": "call", "amount": 300},
                {"street": "preflop", "seat": 2, "type": "call", "amount": 300},
                {"street": "preflop", "seat": 3, "type": "fold", "amount": 0},
                {"street": "preflop", "seat": 4, "type": "call", "amount": 250},
                {"street": "preflop", "seat": 5, "type": "call", "amount": 200},
                {"street": "flop", "seat": 4, "type": "raise-to", "amount": 900},
                {"street": "flop", "seat": 5, "type": "call", "amount": 900},
                {"street": "flop", "seat": 0, "type": "fold", "amount": 0},
                {"street": "flop", "seat": 1, "type": "fold", "amount": 0},
            ],
            "legalActions": [
                {"type": "fold", "amount": None, "minAmount": None, "maxAmount": None},
                {"type": "call", "amount": 900, "minAmount": None, "maxAmount": None},
                {"type": "raise-to", "amount": None, "minAmount": 1800, "maxAmount": 9700},
                {"type": "all-in", "amount": 9700, "minAmount": None, "maxAmount": None},
            ],
        },
    },
]


def python_state(hand: dict) -> dict:
    actor = hand["seats"][hand["toAct"]]
    type_map = {"small-blind": "small_blind", "big-blind": "big_blind", "raise-to": "raise"}
    minimum = next((action["minAmount"] for action in hand["legalActions"] if action["type"] == "raise-to"), 0)
    return {
        "your_cards": actor["holeCards"],
        "community_cards": hand["board"],
        "pot": hand["pot"],
        "your_stack": actor["stack"],
        "your_bet_this_street": actor["streetCommitted"],
        "amount_owed": max(0, hand["currentBet"] - actor["streetCommitted"]),
        "min_raise_to": minimum,
        "can_check": hand["currentBet"] == actor["streetCommitted"],
        "seat_to_act": hand["toAct"],
        "dealer": hand["button"],
        "street": hand["street"],
        "current_bet": hand["currentBet"],
        "action_log": [
            {"action": type_map.get(action["type"], action["type"]), "seat": action["seat"], "amount": action["amount"]}
            for action in hand["actions"]
        ],
        "players": [
            {
                "seat": seat["seat"],
                "stack": seat["stack"],
                "is_folded": seat["status"] == "folded",
                "is_all_in": seat["status"] == "all-in",
                "bet_this_street": seat["streetCommitted"],
            }
            for seat in hand["seats"]
        ],
    }


def main() -> None:
    lookup = DeepCFRLookup(VENDOR / "data/deep_cfr_model.npz")
    output = []
    for case in CASES:
        state = python_state(case["hand"])
        features, legal = encode_state_dict(state, lookup._equity_tables)
        output.append({
            **case,
            "expectedFeatures": features.tolist(),
            "expectedLegal": legal.astype(float).tolist(),
            "expectedStrategy": lookup.get_strategy(state).tolist(),
        })
    path = ROOT / "web/lib/runtime/fullhouse-parity.json"
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
