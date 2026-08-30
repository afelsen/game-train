from __future__ import annotations

import itertools
from typing import Any

import eval7

from game_trainer.poker.cards import FULL_DECK, validate_card

RANKS = "23456789TJQKA"


def _class_name(cards: tuple[str, str]) -> str:
    first, second = sorted(cards, key=lambda card: RANKS.index(card[0]), reverse=True)
    if first[0] == second[0]:
        return first[0] + second[0]
    return first[0] + second[0] + ("s" if first[1] == second[1] else "o")


def _preflop_strength(cards: tuple[str, str]) -> float:
    first, second = cards
    high, low = sorted((RANKS.index(first[0]), RANKS.index(second[0])), reverse=True)
    pair = high == low
    suited = first[1] == second[1]
    gap = high - low
    score = (high + low) / 24
    if pair:
        score = 0.48 + high / 24
    if suited:
        score += 0.08
    if gap <= 1:
        score += 0.06
    elif gap >= 4:
        score -= 0.06
    return max(0.02, min(1.0, score))


def estimate_villain_range(
    hole_cards: list[str],
    board: list[str],
    actions: list[dict[str, Any]],
    opponent_seat: int = 1,
) -> dict[str, Any]:
    """Return a transparent action-weighted distribution for one opponent."""
    if type(opponent_seat) is not int or not 1 <= opponent_seat <= 5:
        raise ValueError("opponentSeat must be an integer from 1 to 5")
    known = hole_cards + board
    for card in known:
        validate_card(card)
    if len(set(known)) != len(known):
        raise ValueError("range calculation cards must be unique")
    remaining = [card for card in FULL_DECK if card not in known]
    combos = list(itertools.combinations(remaining, 2))
    if len(board) >= 3:
        scores = [
            eval7.evaluate([eval7.Card(card) for card in list(combo) + board])
            for combo in combos
        ]
        order = {score: index for index, score in enumerate(sorted(set(scores)))}
        denominator = max(1, len(order) - 1)
        strengths = [order[score] / denominator for score in scores]
    else:
        strengths = [_preflop_strength(combo) for combo in combos]

    villain_actions = [action for action in actions if action.get("seat") == opponent_seat]
    weights: list[float] = []
    for strength in strengths:
        weight = 1.0
        for action in villain_actions:
            action_type = action.get("type")
            if action_type in ("raise-to", "all-in"):
                likelihood = 0.15 + 1.85 * strength**2
            elif action_type == "call":
                likelihood = 0.35 + 0.9 * (1 - abs(strength - 0.62))
            elif action_type == "check":
                likelihood = 1.35 - 0.7 * strength
            elif action_type == "fold":
                likelihood = 1.4 - strength
            else:
                continue
            weight *= max(0.05, likelihood)
        weights.append(weight)

    total = sum(weights)
    normalized = [weight / total for weight in weights]
    grouped: dict[str, float] = {}
    for combo, weight in zip(combos, normalized):
        grouped[_class_name(combo)] = grouped.get(_class_name(combo), 0.0) + weight
    top_classes = sorted(grouped.items(), key=lambda item: item[1], reverse=True)[:8]
    sorted_weights = sorted(normalized, reverse=True)
    cumulative = 0.0
    effective_combos = 0
    for weight in sorted_weights:
        cumulative += weight
        effective_combos += 1
        if cumulative >= 0.8:
            break
    return {
        "schemaVersion": "1.0.0",
        "method": "action-weighted-v1",
        "description": "Heuristic estimate from the selected opponent's observed actions; not a solver-derived range.",
        "opponentSeat": opponent_seat,
        "observedActions": len(villain_actions),
        "combos": [
            {"cards": list(combo), "weight": weight}
            for combo, weight in zip(combos, normalized)
        ],
        "topClasses": [
            {"handClass": hand_class, "weight": weight}
            for hand_class, weight in top_classes
        ],
        "effectiveCombos80": effective_combos,
    }
