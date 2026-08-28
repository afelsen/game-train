from __future__ import annotations

import random

RANKS = "23456789TJQKA"
SUITS = "cdhs"
FULL_DECK = tuple(rank + suit for suit in SUITS for rank in RANKS)


def shuffled_deck(seed: int) -> list[str]:
    """Return a deterministic deck whose next card is at the end of the list."""
    deck = list(FULL_DECK)
    random.Random(seed).shuffle(deck)
    return deck


def validate_card(card: str) -> None:
    if len(card) != 2 or card[0] not in RANKS or card[1] not in SUITS:
        raise ValueError(f"invalid card: {card!r}")

