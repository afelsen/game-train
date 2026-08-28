"""Executable contract for the first restricted heads-up NLHE training tree."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

ABSTRACTION_ID = "restricted-hu-nlhe-flop-cfr-v1"
ENCODER_VERSION = "restricted-hu-nlhe-infoset-v1"
ACTION_VERSION = "restricted-pot-fractions-v1"

RANKS = "23456789TJQKA"
SUITS = "cdhs"
STREETS = ("flop", "turn", "river")
POSITIONS = ("oop", "ip")
NO_BET_ACTIONS = ("check", "bet-50", "bet-100", "all-in")
FACING_BET_ACTIONS = ("fold", "call", "raise-2.5x", "all-in")
ALL_ACTIONS = frozenset(NO_BET_ACTIONS + FACING_BET_ACTIONS)
ROOT_FLOP_RANKS = ("T", "9", "6")
QUARTERS_PER_BB = Decimal("4")


class UnsupportedTrainingState(ValueError):
    """Raised when a state falls outside the declared training abstraction."""


def _card(card: Any) -> str:
    if not isinstance(card, str) or len(card) != 2:
        raise UnsupportedTrainingState(f"invalid card: {card!r}")
    rank, suit = card[0].upper(), card[1].lower()
    if rank not in RANKS or suit not in SUITS:
        raise UnsupportedTrainingState(f"invalid card: {card!r}")
    return rank + suit


def _cards(cards: Any, expected: int | None = None) -> list[str]:
    if not isinstance(cards, (list, tuple)):
        raise UnsupportedTrainingState("cards must be a list or tuple")
    normalized = [_card(card) for card in cards]
    if expected is not None and len(normalized) != expected:
        raise UnsupportedTrainingState(f"expected {expected} cards")
    return normalized


def _quarter_bb(value: Any, field: str) -> int:
    try:
        quarters = Decimal(str(value)) * QUARTERS_PER_BB
    except (InvalidOperation, ValueError):
        raise UnsupportedTrainingState(f"{field} must be numeric") from None
    if quarters != quarters.to_integral_value() or quarters < 0:
        raise UnsupportedTrainingState(f"{field} must be a non-negative multiple of 0.25 BB")
    return int(quarters)


def _canonicalize_cards(board: list[str], hole_cards: list[str]) -> tuple[list[str], list[str]]:
    """Assign suit labels by first public appearance, then private appearance."""
    suit_map: dict[str, str] = {}
    labels = iter("abcd")

    def canonical(card: str) -> str:
        rank, suit = card
        if suit not in suit_map:
            suit_map[suit] = next(labels)
        return rank + suit_map[suit]

    canonical_board = [canonical(card) for card in board]
    # Private-card order is not observable state. Sort before assigning any suits
    # that have not already appeared publicly so input order cannot alter the key.
    hole_cards = sorted(hole_cards, key=lambda card: (-RANKS.index(card[0]), card[1]))
    canonical_hole = [canonical(card) for card in hole_cards]
    canonical_hole.sort(key=lambda card: (-RANKS.index(card[0]), card[1]))
    return canonical_board, canonical_hole


def _validate_root_flop(board: list[str]) -> None:
    flop = board[:3]
    if tuple(card[0] for card in flop) != ROOT_FLOP_RANKS:
        raise UnsupportedTrainingState("board is outside the T-9-6 root flop family")
    if not (flop[0][1] == flop[1][1] and flop[2][1] != flop[0][1]):
        raise UnsupportedTrainingState("board is outside the two-tone T-9-6 root flop family")


def _validate_history(history: Any, street: str) -> list[str]:
    if not isinstance(history, (list, tuple)):
        raise UnsupportedTrainingState("history must be a list or tuple")
    result: list[str] = []
    raises_this_street = 0
    for item in history:
        if not isinstance(item, str):
            raise UnsupportedTrainingState("history entries must be strings")
        parts = item.split(":")
        if len(parts) != 3 or parts[0] not in STREETS or parts[1] not in POSITIONS or parts[2] not in ALL_ACTIONS:
            raise UnsupportedTrainingState(f"invalid abstract history entry: {item!r}")
        if STREETS.index(parts[0]) > STREETS.index(street):
            raise UnsupportedTrainingState("history contains an action from a future street")
        if parts[0] == street and parts[2].startswith("raise-"):
            raises_this_street += 1
        result.append(item)
    if raises_this_street > 1:
        raise UnsupportedTrainingState("at most one raise is supported per street")
    return result


def encode_information_set(state: dict[str, Any]) -> dict[str, Any]:
    """Validate and encode a supported state into a stable information-set identity."""
    street = state.get("street")
    if street not in STREETS:
        raise UnsupportedTrainingState("only flop, turn, and river states are supported")
    actor = state.get("actor")
    if actor not in (0, 1):
        raise UnsupportedTrainingState("actor must be 0 or 1")
    position = state.get("position")
    if position not in POSITIONS:
        raise UnsupportedTrainingState("position must be oop or ip")
    if position != POSITIONS[actor]:
        raise UnsupportedTrainingState("actor 0 is oop and actor 1 is ip")

    board = _cards(state.get("board"), STREETS.index(street) + 3)
    hole_cards = _cards(state.get("holeCards"), 2)
    if len(set(board + hole_cards)) != len(board) + len(hole_cards):
        raise UnsupportedTrainingState("board and hole cards must be unique")
    _validate_root_flop(board)
    history = _validate_history(state.get("history"), street)
    canonical_board, canonical_hole = _canonicalize_cards(board, hole_cards)

    payload = {
        "abstractionId": ABSTRACTION_ID,
        "encoderVersion": ENCODER_VERSION,
        "street": street,
        "actor": actor,
        "position": position,
        "holeCards": canonical_hole,
        "board": canonical_board,
        "potQuarterBb": _quarter_bb(state.get("potBb"), "potBb"),
        "effectiveStackQuarterBb": _quarter_bb(state.get("effectiveStackBb"), "effectiveStackBb"),
        "toCallQuarterBb": _quarter_bb(state.get("toCallBb"), "toCallBb"),
        "history": history,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "informationSetId": hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
        "canonicalJson": canonical_json,
        "payload": payload,
    }


def legal_abstract_actions(state: dict[str, Any]) -> tuple[str, ...]:
    """Return the abstract actions available at a validated information state."""
    encode_information_set(state)
    to_call = Decimal(str(state["toCallBb"]))
    if to_call == 0:
        return NO_BET_ACTIONS
    street = state["street"]
    raised = any(item.split(":")[0] == street and item.split(":")[2].startswith("raise-") for item in state["history"])
    return ("fold", "call") if raised else FACING_BET_ACTIONS


def translate_bet_size(amount_bb: float, pot_bb: float, effective_stack_bb: float) -> str:
    """Map an off-tree wager to the nearest legal abstract size, breaking ties upward."""
    amount = Decimal(str(amount_bb))
    pot = Decimal(str(pot_bb))
    stack = Decimal(str(effective_stack_bb))
    if amount <= 0 or pot <= 0 or stack <= 0 or amount > stack:
        raise UnsupportedTrainingState("bet, pot, and stack must be positive and bet cannot exceed stack")
    candidates = [(min(pot * Decimal("0.5"), stack), "bet-50"), (min(pot, stack), "bet-100"), (stack, "all-in")]
    unique = {size: action for size, action in candidates}
    return min(unique.items(), key=lambda item: (abs(item[0] - amount), -item[0]))[1]


def canonical_policy(actions: Iterable[str], probabilities: Iterable[float]) -> dict[str, float]:
    """Build a stable policy mapping while rejecting actions outside the abstraction."""
    pairs = list(zip(actions, probabilities, strict=True))
    if any(action not in ALL_ACTIONS for action, _ in pairs):
        raise UnsupportedTrainingState("policy contains an unsupported action")
    if any(probability < 0 for _, probability in pairs):
        raise UnsupportedTrainingState("policy probabilities cannot be negative")
    total = sum(probability for _, probability in pairs)
    if total <= 0:
        raise UnsupportedTrainingState("policy must have positive probability mass")
    return {action: probability / total for action, probability in sorted(pairs)}
