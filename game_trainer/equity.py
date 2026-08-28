from __future__ import annotations

import hashlib
import itertools
import math
import random
from typing import Any

import eval7

from game_trainer.poker.cards import FULL_DECK, validate_card

HAND_CATEGORIES = (
    "high-card", "one-pair", "two-pair", "three-of-a-kind", "straight",
    "flush", "full-house", "four-of-a-kind", "straight-flush",
)
EVAL7_CATEGORY = {
    "High Card": "high-card", "Pair": "one-pair", "Two Pair": "two-pair",
    "Trips": "three-of-a-kind", "Straight": "straight", "Flush": "flush",
    "Full House": "full-house", "Quads": "four-of-a-kind", "Straight Flush": "straight-flush",
}


def _validate_known_cards(hole_cards: list[str], board: list[str]) -> list[str]:
    if len(hole_cards) != 2:
        raise ValueError("calculation requires exactly two hole cards")
    if len(board) > 5:
        raise ValueError("board cannot contain more than five cards")
    for card in hole_cards + board:
        validate_card(card)
    if len(set(hole_cards + board)) != len(hole_cards) + len(board):
        raise ValueError("calculation cards must be unique")
    return [card for card in FULL_DECK if card not in hole_cards and card not in board]


def calculate_equity(hole_cards: list[str], board: list[str], sample_limit: int = 20_000) -> dict[str, Any]:
    """Calculate heads-up showdown equity against one uniformly random legal hand."""
    remaining = _validate_known_cards(hole_cards, board)
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


def calculate_hand_chances(hole_cards: list[str], board: list[str], sample_limit: int = 20_000) -> dict[str, Any]:
    """Return cumulative chances of making each hand category by the river."""
    remaining = _validate_known_cards(hole_cards, board)
    missing_board = 5 - len(board)
    runout_count = math.comb(len(remaining), missing_board)
    exact = runout_count <= sample_limit
    counts = {category: 0 for category in HAND_CATEGORIES}

    def record(runout: tuple[str, ...] | list[str]) -> None:
        cards = [eval7.Card(card) for card in hole_cards + board + list(runout)]
        category = EVAL7_CATEGORY[eval7.handtype(eval7.evaluate(cards))]
        counts[category] += 1

    if exact:
        for runout in itertools.combinations(remaining, missing_board):
            record(runout)
    else:
        seed_material = ("hand-chances|" + "|".join(sorted(hole_cards) + ["/"] + board)).encode()
        rng = random.Random(int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big"))
        for _ in range(sample_limit):
            record(rng.sample(remaining, missing_board))

    samples = sum(counts.values())
    exact_probabilities: dict[str, float] = {}
    combinations: dict[str, int] = {}
    cumulative = 0
    at_least: dict[str, float] = {}
    for category in reversed(HAND_CATEGORIES):
        exact_probabilities[category] = counts[category] / samples
        combinations[category] = counts[category]
        cumulative += counts[category]
        at_least[category] = cumulative / samples

    baseline_counts = {category: 0 for category in HAND_CATEGORIES}
    baseline_samples = min(5_000, sample_limit)
    baseline_seed = (
        "hand-baseline|" + "|".join(sorted(hole_cards) + ["/"] + board)
    ).encode()
    baseline_rng = random.Random(
        int.from_bytes(hashlib.sha256(baseline_seed).digest()[:8], "big")
    )
    for _ in range(baseline_samples):
        drawn = baseline_rng.sample(remaining, 2 + missing_board)
        cards = [eval7.Card(card) for card in drawn[:2] + board + drawn[2:]]
        category = EVAL7_CATEGORY[eval7.handtype(eval7.evaluate(cards))]
        baseline_counts[category] += 1
    baseline_cumulative = 0
    baseline_exact: dict[str, float] = {}
    baseline_at_least: dict[str, float] = {}
    for category in reversed(HAND_CATEGORIES):
        baseline_exact[category] = baseline_counts[category] / baseline_samples
        baseline_cumulative += baseline_counts[category]
        baseline_at_least[category] = baseline_cumulative / baseline_samples
    return {
        "schemaVersion": "1.0.0",
        "method": "exact" if exact else "sampled",
        "samples": samples,
        "exact": exact_probabilities,
        "combinations": combinations,
        "atLeast": at_least,
        "outs": combinations,
        "baselineExact": baseline_exact,
        "baselineAtLeast": baseline_at_least,
        "baselineSamples": baseline_samples,
        "baselineLabel": "random legal hand",
    }
