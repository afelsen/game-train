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
    opponent_count: int = 1,
    opponent_ranges: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Calculate showdown equity against one to five opponent hands."""
    if type(opponent_count) is not int or not 1 <= opponent_count <= 5:
        raise ValueError("opponentCount must be an integer from 1 to 5")
    if opponent_weights is not None and opponent_ranges is not None:
        raise ValueError("use opponentWeights or opponentRanges, not both")
    if opponent_ranges is not None and len(opponent_ranges) != opponent_count:
        raise ValueError("opponentRanges must contain one range per opponent")
    if opponent_weights is not None:
        opponent_ranges = [opponent_weights]
    remaining = _validate_known_cards(hole_cards, board)
    missing_board = 5 - len(board)
    cards_needed = 2 * opponent_count + missing_board
    if cards_needed > len(remaining):
        raise ValueError("not enough unknown cards for the requested opponents")
    outcome_count = (
        math.comb(len(remaining), 2) * math.comb(len(remaining) - 2, missing_board)
        if opponent_count == 1
        else sample_limit + 1
    )
    exact = opponent_ranges is None and opponent_count == 1 and outcome_count <= sample_limit
    wins = ties = losses = 0
    equity_total = equity_square_total = 0.0

    def score(opponents: list[list[str]], runout: tuple[str, ...] | list[str]) -> None:
        nonlocal wins, ties, losses, equity_total, equity_square_total
        complete_board = board + list(runout)
        hero_score = eval7.evaluate([eval7.Card(card) for card in hole_cards + complete_board])
        opponent_scores = [
            eval7.evaluate([eval7.Card(card) for card in opponent + complete_board])
            for opponent in opponents
        ]
        best_opponent = max(opponent_scores)
        if hero_score > best_opponent:
            wins += 1
            share = 1.0
        elif hero_score == best_opponent:
            ties += 1
            share = 1 / (1 + sum(score == hero_score for score in opponent_scores))
        else:
            losses += 1
            share = 0.0
        equity_total += share
        equity_square_total += share * share

    if opponent_ranges is not None:
        weighted_ranges: list[tuple[list[list[str]], list[float]]] = []
        remaining_set = set(remaining)
        for opponent_range in opponent_ranges:
            weighted: list[tuple[list[str], float]] = []
            for item in opponent_range:
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
            population = [cards for cards, _ in weighted]
            cumulative = list(itertools.accumulate(weight for _, weight in weighted))
            weighted_ranges.append((population, cumulative))
        seed_material = (
            f"weighted-equity-{opponent_count}|" + "|".join(sorted(hole_cards) + ["/"] + board)
        ).encode()
        rng = random.Random(int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big"))
        for _ in range(sample_limit):
            opponents: list[list[str]] = []
            blocked: set[str] = set()
            for population, cumulative in weighted_ranges:
                cards = None
                for _attempt in range(100):
                    candidate = rng.choices(population, cum_weights=cumulative, k=1)[0]
                    if not blocked.intersection(candidate):
                        cards = candidate
                        break
                if cards is None:
                    raise ValueError("opponent ranges have no collision-free assignment")
                opponents.append(cards)
                blocked.update(cards)
            runout_pool = [card for card in remaining if card not in blocked]
            score(opponents, rng.sample(runout_pool, missing_board))
    elif exact:
        for opponent in itertools.combinations(remaining, 2):
            runout_pool = [card for card in remaining if card not in opponent]
            for runout in itertools.combinations(runout_pool, missing_board):
                score([list(opponent)], runout)
    else:
        seed_material = (
            f"equity-{opponent_count}|" + "|".join(sorted(hole_cards) + ["/"] + board)
        ).encode()
        rng = random.Random(int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big"))
        for _ in range(sample_limit):
            drawn = rng.sample(remaining, cards_needed)
            opponents = [drawn[index:index + 2] for index in range(0, 2 * opponent_count, 2)]
            score(opponents, drawn[2 * opponent_count:])

    samples = wins + ties + losses
    equity = equity_total / samples
    variance = max(0.0, equity_square_total / samples - equity * equity)
    standard_error = 0.0 if exact else math.sqrt(variance / samples)
    return {
        "schemaVersion": "1.0.0",
        "method": "exact" if exact else "sampled",
        "samples": samples,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "equity": equity,
        "standardError": standard_error,
        "opponentCount": opponent_count,
        "playerCount": opponent_count + 1,
        "opponentRange": "action-weighted-v1" if opponent_ranges is not None else "uniform-random",
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
