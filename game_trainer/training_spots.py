from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from game_trainer.poker.cards import FULL_DECK


RANGE_PROFILES = (
    {
        "id": "single-raised-pot",
        "oop": "66+,A8s+,A5s-A4s,AJo+,K9s+,KQo,QTs+,JTs,96s+,85s+,75s+,65s,54s",
        "ip": "QQ-22,AQs-A2s,ATo+,K5s+,KJo+,Q8s+,J8s+,T7s+,96s+,86s+,75s+,64s+,53s+",
    },
    {
        "id": "button-vs-big-blind",
        "oop": "55+,A2s+,A9o+,K7s+,KTo+,Q8s+,QTo+,J8s+,JTo,T8s+,97s+,86s+,75s+,65s,54s",
        "ip": "22+,A2s+,A2o+,K2s+,K7o+,Q4s+,Q8o+,J6s+,J8o+,T6s+,T8o+,96s+,97o+,85s+,75s+,64s+,53s+",
    },
    {
        "id": "three-bet-pot",
        "oop": "99+,AQs+,AKo,A5s-A4s,KQs",
        "ip": "77+,AJs+,AQo+,A5s-A2s,KQs,KJs,QJs,JTs,T9s,98s",
    },
)


def _request(
    *,
    flop: str,
    turn: str,
    profile: dict[str, str],
    starting_pot: int,
    effective_stack: int,
    max_iterations: int = 100,
) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0.0",
        "mode": "visual",
        "oopRange": profile["oop"],
        "ipRange": profile["ip"],
        "flop": flop,
        "turn": turn,
        "startingPot": starting_pot,
        "effectiveStack": effective_stack,
        "betSizes": "60%, e, a",
        "raiseSizes": "2.5x",
        "maxIterations": max_iterations,
        "targetExploitability": 1.0,
        "reportEvery": 10,
    }


CURATED_SPOTS = (
    {
        "id": "curated-turn-dynamic-diamond-001",
        "title": "Dynamic diamond turn",
        "teachingFocus": "Range interaction on a connected, two-tone board",
        "source": "curated",
        "seed": None,
        "request": _request(
            flop="Td9d6h", turn="Qc", profile=RANGE_PROFILES[0], starting_pot=200, effective_stack=900
        ),
    },
    {
        "id": "curated-turn-ace-paired-002",
        "title": "Paired ace-high turn",
        "teachingFocus": "Small-bet pressure and condensed continuing ranges",
        "source": "curated",
        "seed": None,
        "request": _request(
            flop="Ac7s7d", turn="2c", profile=RANGE_PROFILES[1], starting_pot=550, effective_stack=4_200
        ),
    },
    {
        "id": "curated-turn-threebet-broadway-003",
        "title": "Three-bet broadway turn",
        "teachingFocus": "Polarization with shallow stack-to-pot ratio",
        "source": "curated",
        "seed": None,
        "request": _request(
            flop="KsQh4s", turn="Jd", profile=RANGE_PROFILES[2], starting_pot=1_800, effective_stack=5_200
        ),
    },
)


def curated_spots() -> list[dict[str, Any]]:
    return deepcopy(list(CURATED_SPOTS))


def seeded_random_spots(seed: int, count: int = 1) -> list[dict[str, Any]]:
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if type(count) is not int or not 1 <= count <= 20:
        raise ValueError("count must be an integer from 1 to 20")
    rng = random.Random(seed)
    spots: list[dict[str, Any]] = []
    for index in range(count):
        board = rng.sample(FULL_DECK, 4)
        profile = rng.choice(RANGE_PROFILES)
        starting_pot = rng.choice((200, 400, 550, 800, 1_200, 1_800))
        stack_to_pot = rng.choice((2, 3, 4, 6, 8))
        effective_stack = starting_pot * stack_to_pot
        spot_seed = seed if count == 1 else seed + index
        spots.append(
            {
                "id": f"random-{spot_seed}-{index + 1}",
                "title": f"Seeded turn spot {spot_seed}",
                "teachingFocus": f"Unseen {profile['id'].replace('-', ' ')} decision",
                "source": "seeded-random",
                "seed": spot_seed,
                "request": _request(
                    flop="".join(board[:3]),
                    turn=board[3],
                    profile=profile,
                    starting_pot=starting_pot,
                    effective_stack=effective_stack,
                ),
            }
        )
    return spots
