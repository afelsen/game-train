from __future__ import annotations

import hashlib
import itertools
import math
import random
from typing import Any

import eval7

from game_trainer.poker.cards import FULL_DECK, validate_card


def calculate_equity(hole_cards: list[str], board: list[str], sample_limit: int = 20_000) -> dict[str, Any]:
    """Calculate heads-up showdown equity against one uniformly random legal hand."""
    if len(hole_cards) != 2:
        raise ValueError("equity requires exactly two hole cards")
    if len(board) > 5:
        raise ValueError("board cannot contain more than five cards")
    for card in hole_cards + board:
        validate_card(card)
    if len(set(hole_cards + board)) != len(hole_cards) + len(board):
        raise ValueError("equity cards must be unique")
    remaining = [card for card in FULL_DECK if card not in hole_cards and card not in board]
    missing_board = 5 - len(board)
    outcome_count = math.comb(len(remaining), 2) * math.comb(len(remaining) - 2, missing_board)
    exact = outcome_count <= sample_limit
    wins = ties = losses = 0

    def score(opponent: tuple[str, ...] | list[str], runout: tuple[str, ...] | list[str]) -> None:
        nonlocal wins, ties, losses
        complete_board = board + list(runout)
        hero_score = eval7.evaluate([eval7.Card(card) for card in hole_cards + complete_board])
        opponent_score = eval7.evaluate([eval7.Card(card) for card in list(opponent) + complete_board])
        if hero_score > opponent_score:
            wins += 1
        elif hero_score == opponent_score:
            ties += 1
        else:
            losses += 1

    if exact:
        for opponent in itertools.combinations(remaining, 2):
            runout_pool = [card for card in remaining if card not in opponent]
            for runout in itertools.combinations(runout_pool, missing_board):
                score(opponent, runout)
    else:
        seed_material = "|".join(sorted(hole_cards) + ["/"] + board).encode()
        rng = random.Random(int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big"))
        for _ in range(sample_limit):
            drawn = rng.sample(remaining, 2 + missing_board)
            score(drawn[:2], drawn[2:])

    samples = wins + ties + losses
    equity = (wins + ties / 2) / samples
    standard_error = 0.0 if exact else math.sqrt(equity * (1 - equity) / samples)
    return {
        "schemaVersion": "1.0.0",
        "method": "exact" if exact else "sampled",
        "samples": samples,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "equity": equity,
        "standardError": standard_error,
        "opponentRange": "uniform-random",
    }
