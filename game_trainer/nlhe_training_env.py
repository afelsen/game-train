"""Deterministic game tree for the restricted heads-up NLHE training contract."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Iterator

import eval7

from game_trainer.nlhe_abstraction import ABSTRACTION_ID, RANKS, SUITS, encode_information_set
from game_trainer.poker.cards import FULL_DECK

ROOT = Path(__file__).resolve().parent.parent
RANK_INDEX = {rank: index for index, rank in enumerate(RANKS)}
ROOT_POT_Q = 22
ROOT_STACK_Q = 389
ROOT_BASELINE_Q = ROOT_STACK_Q + ROOT_POT_Q // 2


class InvalidTrainingAction(ValueError):
    """Raised when an action or chance card is illegal in the current node."""


def _descriptor(text: str) -> tuple[str, str, str]:
    if len(text) not in (2, 3) or text[0] not in RANKS or text[1] not in RANKS:
        raise ValueError(f"invalid range descriptor: {text!r}")
    shape = text[2:] or "b"
    if shape not in ("s", "o", "b") or (text[0] == text[1] and shape != "b"):
        raise ValueError(f"invalid range descriptor: {text!r}")
    if text[0] != text[1] and RANK_INDEX[text[0]] <= RANK_INDEX[text[1]]:
        raise ValueError(f"range ranks must be written high-to-low: {text!r}")
    return text[0], text[1], shape


def _expand_token(token: str) -> list[tuple[str, str, str]]:
    if token.endswith("+"):
        first, second, shape = _descriptor(token[:-1])
        if first == second:
            return [(rank, rank, "b") for rank in RANKS[RANK_INDEX[first] :]]
        upper = RANK_INDEX[first]
        return [(first, rank, shape) for rank in RANKS[RANK_INDEX[second] : upper]]
    if "-" in token:
        start_text, end_text = token.split("-", 1)
        first, second, shape = _descriptor(start_text)
        end_first, end_second, end_shape = _descriptor(end_text)
        if first == second and end_first == end_second:
            low, high = sorted((RANK_INDEX[first], RANK_INDEX[end_first]))
            return [(rank, rank, "b") for rank in RANKS[low : high + 1]]
        if first != end_first or shape != end_shape:
            raise ValueError(f"range endpoints must share first rank and shape: {token!r}")
        low, high = sorted((RANK_INDEX[second], RANK_INDEX[end_second]))
        if high >= RANK_INDEX[first]:
            raise ValueError(f"invalid range interval: {token!r}")
        return [(first, rank, shape) for rank in RANKS[low : high + 1]]
    return [_descriptor(token)]


def _combos(descriptor: tuple[str, str, str]) -> Iterator[tuple[str, str]]:
    first, second, shape = descriptor
    if first == second:
        yield from itertools.combinations((first + suit for suit in SUITS), 2)
    elif shape == "s":
        for suit in SUITS:
            yield first + suit, second + suit
    elif shape == "o":
        for first_suit in SUITS:
            for second_suit in SUITS:
                if first_suit != second_suit:
                    yield first + first_suit, second + second_suit
    else:
        for first_suit in SUITS:
            for second_suit in SUITS:
                yield first + first_suit, second + second_suit


def expand_range(range_text: str, blocked: Iterable[str] = ()) -> tuple[tuple[str, str], ...]:
    """Expand standard pair/suited/offsuit + and interval notation deterministically."""
    blocked_cards = frozenset(blocked)
    result: set[tuple[str, str]] = set()
    for raw_token in range_text.split(","):
        token = raw_token.strip()
        if not token:
            raise ValueError("range contains an empty token")
        for descriptor in _expand_token(token):
            for cards in _combos(descriptor):
                if blocked_cards.isdisjoint(cards):
                    result.add(tuple(sorted(cards)))
    return tuple(sorted(result))


def manifest_ranges() -> tuple[str, str]:
    manifest = json.loads((ROOT / "manifests/restricted-hu-nlhe-flop-cfr-v1.json").read_text())
    if manifest["id"] != ABSTRACTION_ID:
        raise ValueError("training manifest abstraction id mismatch")
    return manifest["ranges"]["oop"], manifest["ranges"]["ip"]


def compatible_private_deals(board: Iterable[str]) -> tuple[tuple[tuple[str, str], tuple[str, str]], ...]:
    """Return every blocker-compatible OOP/IP private deal in stable order."""
    board_cards = tuple(board)
    oop_text, ip_text = manifest_ranges()
    oop = expand_range(oop_text, board_cards)
    ip = expand_range(ip_text, board_cards)
    return tuple((oop_cards, ip_cards) for oop_cards in oop for ip_cards in ip if set(oop_cards).isdisjoint(ip_cards))


@dataclass(frozen=True)
class RestrictedNlheState:
    board: tuple[str, ...]
    hole_cards: tuple[tuple[str, str], tuple[str, str]]
    pot_q: int = ROOT_POT_Q
    stacks_q: tuple[int, int] = (ROOT_STACK_Q, ROOT_STACK_Q)
    committed_q: tuple[int, int] = (0, 0)
    actor: int | None = 0
    history: tuple[str, ...] = ()
    raises_this_street: int = 0
    awaiting_chance: bool = False
    terminal_utility_oop_q: int | None = None

    @property
    def street(self) -> str:
        return ("flop", "turn", "river")[len(self.board) - 3]

    @property
    def terminal(self) -> bool:
        return self.terminal_utility_oop_q is not None

    @classmethod
    def root(cls, oop_hole: tuple[str, str], ip_hole: tuple[str, str]) -> "RestrictedNlheState":
        board = ("Td", "9d", "6h")
        used = board + oop_hole + ip_hole
        if len(set(used)) != 7:
            raise ValueError("root cards must be unique")
        oop_range, ip_range = manifest_ranges()
        if tuple(sorted(oop_hole)) not in expand_range(oop_range, board):
            raise ValueError("OOP hand is outside the manifest range")
        if tuple(sorted(ip_hole)) not in expand_range(ip_range, board):
            raise ValueError("IP hand is outside the manifest range")
        return cls(board=board, hole_cards=(tuple(sorted(oop_hole)), tuple(sorted(ip_hole))))

    def _to_call(self) -> int:
        if self.actor is None:
            return 0
        return max(self.committed_q) - self.committed_q[self.actor]

    def legal_actions(self) -> tuple[str, ...]:
        if self.terminal or self.awaiting_chance or self.actor is None:
            return ()
        to_call = self._to_call()
        own_stack = self.stacks_q[self.actor]
        opponent_stack = self.stacks_q[1 - self.actor]
        if to_call:
            actions = ["fold", "call"]
            if self.raises_this_street == 0 and own_stack > to_call and opponent_stack > 0:
                actions.extend(("raise-2.5x", "all-in"))
            return tuple(actions)
        actions = ["check"]
        if own_stack > 0 and opponent_stack > 0:
            actions.extend(("bet-50", "bet-100", "all-in"))
        return tuple(actions)

    def information_set(self) -> dict[str, object]:
        """Encode the acting player's observation using the versioned contract."""
        if self.terminal or self.awaiting_chance or self.actor is None:
            raise InvalidTrainingAction("terminal and chance nodes have no information set")
        return encode_information_set(
            {
                "street": self.street,
                "actor": self.actor,
                "position": ("oop", "ip")[self.actor],
                "holeCards": list(self.hole_cards[self.actor]),
                "board": list(self.board),
                "potBb": self.pot_q / 4,
                "effectiveStackBb": min(self.stacks_q) / 4,
                "toCallBb": self._to_call() / 4,
                "history": list(self.history),
            }
        )

    def chance_outcomes(self) -> tuple[tuple[str, float], ...]:
        if not self.awaiting_chance or self.terminal:
            return ()
        used = set(self.board + self.hole_cards[0] + self.hole_cards[1])
        remaining = tuple(card for card in FULL_DECK if card not in used)
        probability = 1.0 / len(remaining)
        return tuple((card, probability) for card in remaining)

    def deal(self, card: str) -> "RestrictedNlheState":
        choices = {candidate for candidate, _ in self.chance_outcomes()}
        if card not in choices:
            raise InvalidTrainingAction(f"illegal chance card: {card}")
        state = replace(self, board=self.board + (card,), actor=0, awaiting_chance=False)
        if state.stacks_q[0] == 0 or state.stacks_q[1] == 0:
            return state._showdown(state.history) if len(state.board) == 5 else replace(state, actor=None, awaiting_chance=True)
        return state

    def apply(self, action: str) -> "RestrictedNlheState":
        if action not in self.legal_actions():
            raise InvalidTrainingAction(f"illegal action {action!r}; legal actions are {self.legal_actions()}")
        assert self.actor is not None
        actor, opponent = self.actor, 1 - self.actor
        street = self.street
        history = self.history + (f"{street}:{('oop', 'ip')[actor]}:{action}",)

        if action == "fold":
            utility = self._settled_utility(opponent)
            return replace(self, actor=None, history=history, terminal_utility_oop_q=utility)

        if action == "check":
            previous_check = bool(self.history and self.history[-1] == f"{street}:{('oop', 'ip')[opponent]}:check")
            if previous_check:
                return self._close_street(history)
            return replace(self, actor=opponent, history=history)

        if action == "call":
            amount = min(self._to_call(), self.stacks_q[actor])
            state = self._commit(actor, amount, history)
            return state._close_street(history)

        if action == "bet-50":
            amount = min((self.pot_q + 1) // 2, self.stacks_q[actor])
            return self._commit(actor, amount, history, next_actor=opponent)
        if action == "bet-100":
            amount = min(self.pot_q, self.stacks_q[actor])
            return self._commit(actor, amount, history, next_actor=opponent)
        if action == "all-in":
            state = self._commit(actor, self.stacks_q[actor], history, next_actor=opponent)
            return replace(state, raises_this_street=self.raises_this_street + (1 if self._to_call() else 0))
        if action == "raise-2.5x":
            target = min(max(self.committed_q) * 5 // 2, self.committed_q[actor] + self.stacks_q[actor])
            amount = target - self.committed_q[actor]
            state = self._commit(actor, amount, history, next_actor=opponent)
            return replace(state, raises_this_street=1)
        raise AssertionError("unreachable")

    def _commit(self, actor: int, amount: int, history: tuple[str, ...], next_actor: int | None = None) -> "RestrictedNlheState":
        stacks = list(self.stacks_q)
        committed = list(self.committed_q)
        stacks[actor] -= amount
        committed[actor] += amount
        return replace(
            self,
            pot_q=self.pot_q + amount,
            stacks_q=tuple(stacks),
            committed_q=tuple(committed),
            actor=next_actor,
            history=history,
        )

    def _close_street(self, history: tuple[str, ...]) -> "RestrictedNlheState":
        if self.stacks_q[0] == 0 or self.stacks_q[1] == 0:
            return self._runout_value(history)
        if len(self.board) == 5:
            return self._showdown(history)
        return replace(
            self,
            actor=None,
            committed_q=(0, 0),
            history=history,
            raises_this_street=0,
            awaiting_chance=True,
        )

    def _showdown(self, history: tuple[str, ...]) -> "RestrictedNlheState":
        scores = tuple(
            eval7.evaluate([eval7.Card(card) for card in hole + self.board])
            for hole in self.hole_cards
        )
        winner = 0 if scores[0] > scores[1] else 1 if scores[1] > scores[0] else None
        utility = self._settled_utility(winner)
        return replace(self, actor=None, history=history, terminal_utility_oop_q=utility)

    def _settled_utility(self, winner: int | None) -> int:
        payout_oop = self.pot_q if winner == 0 else self.pot_q // 2 if winner is None else 0
        return self.stacks_q[0] + payout_oop - ROOT_BASELINE_Q

    def _runout_value(self, history: tuple[str, ...]) -> "RestrictedNlheState":
        # All-in runouts remain explicit chance nodes so MCCFR can sample them.
        if len(self.board) == 5:
            return self._showdown(history)
        return replace(self, actor=None, committed_q=(0, 0), history=history, awaiting_chance=True)
