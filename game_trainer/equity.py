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


def _hero_participating_category(hole_cards: list[str], board: list[str]) -> str:
    """Return the best five-card category that uses at least one Hero card."""
    hole_set = set(hole_cards)
    eligible = (
        combination
        for combination in itertools.combinations(hole_cards + board, 5)
        if hole_set.intersection(combination)
    )
    best = max(
        eligible,
        key=lambda combination: eval7.evaluate(
            [eval7.Card(card) for card in combination]
        ),
    )
    score = eval7.evaluate([eval7.Card(card) for card in best])
    return EVAL7_CATEGORY[eval7.handtype(score)]


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


def calculate_equity(
    hole_cards: list[str],
    board: list[str],
    sample_limit: int = 20_000,
    opponent_weights: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calculate heads-up showdown equity against one uniformly random legal hand."""
    remaining = _validate_known_cards(hole_cards, board)
    missing_board = 5 - len(board)
    outcome_count = math.comb(len(remaining), 2) * math.comb(len(remaining) - 2, missing_board)
    exact = opponent_weights is None and outcome_count <= sample_limit
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

    if opponent_weights is not None:
        weighted: list[tuple[list[str], float]] = []
        remaining_set = set(remaining)
        for item in opponent_weights:
            cards = item.get("cards")
            weight = item.get("weight")
            if (
                not isinstance(cards, list)
                or len(cards) != 2
                or any(not isinstance(card, str) or card not in remaining_set for card in cards)
                or cards[0] == cards[1]
                or not isinstance(weight, (int, float))
                or weight < 0
            ):
                raise ValueError("invalid weighted opponent combo")
            weighted.append((cards, float(weight)))
        if not weighted or sum(weight for _, weight in weighted) <= 0:
            raise ValueError("weighted opponent range has no probability mass")
        seed_material = ("weighted-equity|" + "|".join(sorted(hole_cards) + ["/"] + board)).encode()
        rng = random.Random(int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big"))
        population = [cards for cards, _ in weighted]
        weights = [weight for _, weight in weighted]
        for _ in range(sample_limit):
            opponent = rng.choices(population, weights=weights, k=1)[0]
            runout_pool = [card for card in remaining if card not in opponent]
            score(opponent, rng.sample(runout_pool, missing_board))
    elif exact:
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
        "opponentRange": "action-weighted-v1" if opponent_weights is not None else "uniform-random",
    }


def calculate_hand_chances(hole_cards: list[str], board: list[str], sample_limit: int = 20_000) -> dict[str, Any]:
    """Return cumulative chances of making each hand category by the river."""
    remaining = _validate_known_cards(hole_cards, board)
    missing_board = 5 - len(board)
    runout_count = math.comb(len(remaining), missing_board)
    exact = runout_count <= sample_limit
    counts = {category: 0 for category in HAND_CATEGORIES}

    def record(runout: tuple[str, ...] | list[str]) -> None:
        category = _hero_participating_category(hole_cards, board + list(runout))
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
    baseline_hand_count = min(200, baseline_samples)
    baseline_runouts_per_hand = max(1, baseline_samples // baseline_hand_count)
    baseline_by_hand = {
        category: [] for category in HAND_CATEGORIES
    }
    baseline_seed = (
        "hand-baseline|" + "|".join(sorted(hole_cards) + ["/"] + board)
    ).encode()
    baseline_rng = random.Random(
        int.from_bytes(hashlib.sha256(baseline_seed).digest()[:8], "big")
    )
    for _ in range(baseline_hand_count):
        baseline_hole = baseline_rng.sample(remaining, 2)
        runout_pool = [card for card in remaining if card not in baseline_hole]
        hand_counts = {category: 0 for category in HAND_CATEGORIES}
        for _ in range(baseline_runouts_per_hand):
            runout = baseline_rng.sample(runout_pool, missing_board)
            category = _hero_participating_category(baseline_hole, board + runout)
            baseline_counts[category] += 1
            hand_counts[category] += 1
        for category in HAND_CATEGORIES:
            baseline_by_hand[category].append(
                hand_counts[category] / baseline_runouts_per_hand
            )
    baseline_samples = baseline_hand_count * baseline_runouts_per_hand
    baseline_cumulative = 0
    baseline_exact: dict[str, float] = {}
    baseline_at_least: dict[str, float] = {}
    percentile_75_exact: dict[str, float] = {}
    for category in reversed(HAND_CATEGORIES):
        baseline_exact[category] = baseline_counts[category] / baseline_samples
        ordered_probabilities = sorted(baseline_by_hand[category])
        percentile_75_exact[category] = ordered_probabilities[
            math.ceil(0.75 * len(ordered_probabilities)) - 1
        ]
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
        "percentile75Exact": percentile_75_exact,
        "baselineSamples": baseline_samples,
        "baselineLabel": "75th percentile of random legal hands",
    }
