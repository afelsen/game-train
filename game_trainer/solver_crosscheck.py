from __future__ import annotations

from itertools import combinations
from typing import Iterable

SUITS = "cdhs"


def expand_explicit_range(range_text: str, board: Iterable[str] = ()) -> dict[frozenset[str], float]:
    """Expand TexasSolver's explicit AA/AKs/AKo/AK notation into weighted combos."""
    blocked = set(board)
    combos: dict[frozenset[str], float] = {}
    for weighted_token in range_text.split(","):
        token, separator, weight_text = weighted_token.partition(":")
        weight = float(weight_text) if separator else 1.0
        first, second = token[0], token[1]
        suffix = token[2:] if len(token) > 2 else ""
        candidates: list[tuple[str, str]] = []
        if first == second:
            candidates.extend(combinations((first + suit for suit in SUITS), 2))
        elif suffix == "s":
            candidates.extend((first + suit, second + suit) for suit in SUITS)
        elif suffix == "o":
            candidates.extend(
                (first + first_suit, second + second_suit)
                for first_suit in SUITS
                for second_suit in SUITS
                if first_suit != second_suit
            )
        elif not suffix:
            candidates.extend(
                (first + first_suit, second + second_suit)
                for first_suit in SUITS
                for second_suit in SUITS
            )
        else:
            raise ValueError(f"unsupported explicit range token: {token}")
        for cards in candidates:
            if not blocked.intersection(cards):
                combos[frozenset(cards)] = weight
    return combos


def blocker_weighted_action_mix(
    strategy: dict[str, list[float]],
    actions: list[str],
    own_range: dict[frozenset[str], float],
    opponent_range: dict[frozenset[str], float],
) -> dict[str, float]:
    totals = [0.0] * len(actions)
    total_weight = 0.0
    for cards_text, probabilities in strategy.items():
        cards = frozenset((cards_text[:2], cards_text[2:]))
        own_weight = own_range.get(cards, 0.0)
        compatible_opponent_weight = sum(
            weight for opponent_cards, weight in opponent_range.items() if cards.isdisjoint(opponent_cards)
        )
        reach_weight = own_weight * compatible_opponent_weight
        total_weight += reach_weight
        for index, probability in enumerate(probabilities):
            totals[index] += reach_weight * probability
    if total_weight == 0:
        raise ValueError("strategy and ranges have no compatible combinations")
    return {action: total / total_weight for action, total in zip(actions, totals)}
