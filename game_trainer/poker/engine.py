from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass
from enum import Enum
from typing import Any

import eval7

from .cards import shuffled_deck, validate_card
from .errors import IllegalAction, InvalidState


class Street(str, Enum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    TERMINAL = "terminal"


class PlayerStatus(str, Enum):
    ACTIVE = "active"
    FOLDED = "folded"
    ALL_IN = "all-in"


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE_TO = "raise-to"
    ALL_IN = "all-in"


@dataclass(frozen=True)
class Action:
    type: ActionType
    amount: int | None = None

    @classmethod
    def fold(cls) -> "Action":
        return cls(ActionType.FOLD)

    @classmethod
    def check(cls) -> "Action":
        return cls(ActionType.CHECK)

    @classmethod
    def call(cls) -> "Action":
        return cls(ActionType.CALL)

    @classmethod
    def raise_to(cls, amount: int) -> "Action":
        return cls(ActionType.RAISE_TO, amount)

    @classmethod
    def all_in(cls) -> "Action":
        return cls(ActionType.ALL_IN)


@dataclass(frozen=True)
class LegalAction:
    type: ActionType
    amount: int | None = None
    min_amount: int | None = None
    max_amount: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "amount": self.amount,
            "minAmount": self.min_amount,
            "maxAmount": self.max_amount,
        }


@dataclass
class SeatState:
    seat: int
    stack: int
    hole_cards: list[str]
    street_committed: int = 0
    hand_committed: int = 0
    status: PlayerStatus = PlayerStatus.ACTIVE

    def to_dict(self, include_hole_cards: bool = True) -> dict[str, Any]:
        result = {
            "seat": self.seat,
            "stack": self.stack,
            "streetCommitted": self.street_committed,
            "handCommitted": self.hand_committed,
            "status": self.status.value,
        }
        if include_hole_cards:
            result["holeCards"] = list(self.hole_cards)
        return result


class HandState:
    """Authoritative state for one heads-up no-limit Hold'em hand.

    Chip amounts are integers. An action's raise amount is the player's total
    commitment on the current street, matching common poker-engine semantics.
    """

    SCHEMA_VERSION = "1.0.0"

    def __init__(
        self,
        *,
        seed: int,
        button: int = 0,
        starting_stacks: tuple[int, int] = (10_000, 10_000),
        small_blind: int = 50,
        big_blind: int = 100,
    ) -> None:
        if button not in (0, 1):
            raise InvalidState("button must be seat 0 or 1")
        if len(starting_stacks) != 2 or any(type(value) is not int or value <= 0 for value in starting_stacks):
            raise InvalidState("starting stacks must be two positive integers")
        if type(small_blind) is not int or type(big_blind) is not int or not (0 < small_blind <= big_blind):
            raise InvalidState("blinds must be positive integers with small <= big")

        self.seed = seed
        self.button = button
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.starting_stacks = tuple(starting_stacks)
        self.deck = shuffled_deck(seed)
        self.burned: list[str] = []
        self.board: list[str] = []
        self.street = Street.PREFLOP
        self.current_bet = 0
        self.last_full_raise = big_blind
        self.to_act: int | None = button
        self.pending: set[int] = {0, 1}
        self.actions: list[dict[str, Any]] = []
        self.result: dict[str, Any] | None = None

        holes = {0: [], 1: []}
        for _ in range(2):
            holes[button].append(self.deck.pop())
            holes[1 - button].append(self.deck.pop())
        self.seats = [
            SeatState(0, starting_stacks[0], holes[0]),
            SeatState(1, starting_stacks[1], holes[1]),
        ]

        self._post_blind(button, small_blind, "small-blind")
        self._post_blind(1 - button, big_blind, "big-blind")
        self.current_bet = max(seat.street_committed for seat in self.seats)
        self._auto_finish_if_no_decision()
        self.assert_invariants()

    @property
    def pot(self) -> int:
        return sum(seat.hand_committed for seat in self.seats)

    @property
    def terminal(self) -> bool:
        return self.street == Street.TERMINAL

    def _seat(self, seat: int) -> SeatState:
        if seat not in (0, 1):
            raise InvalidState(f"invalid seat {seat}")
        return self.seats[seat]

    def _commit(self, seat: SeatState, amount: int) -> None:
        if type(amount) is not int or amount < 0 or amount > seat.stack:
            raise InvalidState(f"invalid commitment {amount} for stack {seat.stack}")
        seat.stack -= amount
        seat.street_committed += amount
        seat.hand_committed += amount
        if seat.stack == 0:
            seat.status = PlayerStatus.ALL_IN

    def _post_blind(self, seat_number: int, blind: int, action_type: str) -> None:
        seat = self._seat(seat_number)
        amount = min(blind, seat.stack)
        self._commit(seat, amount)
        self.actions.append({"street": Street.PREFLOP.value, "seat": seat_number, "type": action_type, "amount": amount})

    def amount_to_call(self, seat_number: int | None = None) -> int:
        if seat_number is None:
            if self.to_act is None:
                return 0
            seat_number = self.to_act
        seat = self._seat(seat_number)
        return max(0, self.current_bet - seat.street_committed)

    def legal_actions(self) -> list[LegalAction]:
        if self.terminal or self.to_act is None:
            return []
        seat = self._seat(self.to_act)
        if seat.status != PlayerStatus.ACTIVE:
            return []
        to_call = self.amount_to_call()
        maximum = seat.street_committed + seat.stack
        actions: list[LegalAction] = []
        if to_call > 0:
            actions.append(LegalAction(ActionType.FOLD))
            actions.append(LegalAction(ActionType.CALL, amount=min(to_call, seat.stack)))
        else:
            actions.append(LegalAction(ActionType.CHECK))

        opponent = self._seat(1 - self.to_act)
        if seat.stack > to_call and opponent.status == PlayerStatus.ACTIVE:
            minimum = self.current_bet + self.last_full_raise
            if self.current_bet == 0:
                minimum = self.big_blind
            if maximum >= minimum:
                actions.append(LegalAction(ActionType.RAISE_TO, min_amount=minimum, max_amount=maximum))
            actions.append(LegalAction(ActionType.ALL_IN, amount=maximum))
        elif seat.stack > 0 and to_call > 0:
            # CALL already represents a short all-in call; do not duplicate it.
            pass
        return actions

    def apply(self, action: Action) -> None:
        if self.terminal or self.to_act is None:
            raise IllegalAction("the hand is terminal")
        seat_number = self.to_act
        seat = self._seat(seat_number)
        opponent = self._seat(1 - seat_number)
        to_call = self.amount_to_call(seat_number)
        maximum = seat.street_committed + seat.stack
        record_amount = 0

        if action.type == ActionType.FOLD:
            if to_call <= 0:
                raise IllegalAction("cannot fold when checking is available")
            seat.status = PlayerStatus.FOLDED
            self.actions.append({"street": self.street.value, "seat": seat_number, "type": "fold", "amount": 0})
            self._award_fold(1 - seat_number)
            self.assert_invariants()
            return

        if action.type == ActionType.CHECK:
            if to_call != 0:
                raise IllegalAction(f"cannot check facing {to_call}")
            self.pending.discard(seat_number)
            record_amount = 0

        elif action.type == ActionType.CALL:
            if to_call <= 0:
                raise IllegalAction("cannot call when checking is available")
            record_amount = min(to_call, seat.stack)
            self._commit(seat, record_amount)
            self.pending.discard(seat_number)

        elif action.type in (ActionType.RAISE_TO, ActionType.ALL_IN):
            if seat.stack <= to_call:
                raise IllegalAction("no chips available beyond a call")
            if opponent.status == PlayerStatus.ALL_IN:
                raise IllegalAction("cannot raise when the opponent is all-in")
            target = maximum if action.type == ActionType.ALL_IN else action.amount
            if type(target) is not int:
                raise IllegalAction("raise-to requires an integer amount")
            if target <= self.current_bet or target > maximum:
                raise IllegalAction(f"raise target must be above {self.current_bet} and at most {maximum}")
            raise_size = target - self.current_bet
            minimum = self.big_blind if self.current_bet == 0 else self.current_bet + self.last_full_raise
            if action.type == ActionType.RAISE_TO and target < minimum:
                raise IllegalAction(f"minimum raise-to is {minimum}")
            if action.type == ActionType.ALL_IN and target < minimum and target != maximum:
                raise IllegalAction("invalid incomplete all-in")
            record_amount = target
            increment = target - seat.street_committed
            self._commit(seat, increment)
            if raise_size >= self.last_full_raise:
                self.last_full_raise = raise_size
            self.current_bet = target
            self.pending = {opponent.seat} if opponent.status == PlayerStatus.ACTIVE else set()

        else:
            raise IllegalAction(f"unsupported action {action.type}")

        self.actions.append({"street": self.street.value, "seat": seat_number, "type": action.type.value, "amount": record_amount})
        self._continue_after_action()
        self.assert_invariants()

    def _continue_after_action(self) -> None:
        active_pending = [seat for seat in sorted(self.pending) if self._seat(seat).status == PlayerStatus.ACTIVE]
        if active_pending:
            self.to_act = active_pending[0]
            return
        self._close_betting_round()

    def _close_betting_round(self) -> None:
        self.to_act = None
        self._refund_unmatched_for_showdown()
        if any(seat.status == PlayerStatus.ALL_IN for seat in self.seats):
            self._runout_and_showdown()
            return
        if self.street == Street.RIVER:
            self._showdown()
            return
        self._advance_street()

    def _advance_street(self) -> None:
        for seat in self.seats:
            seat.street_committed = 0
        self.current_bet = 0
        self.last_full_raise = self.big_blind
        if self.street == Street.PREFLOP:
            self._burn_and_deal(3)
            self.street = Street.FLOP
        elif self.street == Street.FLOP:
            self._burn_and_deal(1)
            self.street = Street.TURN
        elif self.street == Street.TURN:
            self._burn_and_deal(1)
            self.street = Street.RIVER
        else:
            raise InvalidState(f"cannot advance from {self.street}")
        first = 1 - self.button
        self.pending = {seat.seat for seat in self.seats if seat.status == PlayerStatus.ACTIVE}
        self.to_act = first if first in self.pending else (next(iter(self.pending)) if self.pending else None)
        self._auto_finish_if_no_decision()

    def _burn_and_deal(self, count: int) -> None:
        self.burned.append(self.deck.pop())
        for _ in range(count):
            self.board.append(self.deck.pop())

    def _auto_finish_if_no_decision(self) -> None:
        active = [seat for seat in self.seats if seat.status == PlayerStatus.ACTIVE]
        all_in = [seat for seat in self.seats if seat.status == PlayerStatus.ALL_IN]
        if not self.terminal and all_in and len(active) <= 1:
            if active and self.amount_to_call(active[0].seat) > 0:
                self.pending = {active[0].seat}
                self.to_act = active[0].seat
            else:
                self._runout_and_showdown()

    def _refund_unmatched_for_showdown(self) -> None:
        """Refund only uncontested excess when play will continue to showdown."""
        committed = [seat.hand_committed for seat in self.seats]
        if committed[0] == committed[1]:
            return
        high = 0 if committed[0] > committed[1] else 1
        difference = abs(committed[0] - committed[1])
        self.seats[high].hand_committed -= difference
        self.seats[high].street_committed = max(0, self.seats[high].street_committed - difference)
        self.seats[high].stack += difference

    def _runout_and_showdown(self) -> None:
        self._refund_unmatched_for_showdown()
        while len(self.board) < 5:
            deal_count = 3 if len(self.board) == 0 else 1
            self._burn_and_deal(deal_count)
        self._showdown()

    def _hand_score(self, seat: SeatState) -> int:
        cards = [eval7.Card(card) for card in seat.hole_cards + self.board]
        return int(eval7.evaluate(cards))

    def _showdown(self) -> None:
        self._refund_unmatched_for_showdown()
        pot = self.pot
        scores = [self._hand_score(seat) for seat in self.seats]
        best_hands = [self._best_five(seat) for seat in (0, 1)]
        payouts = [0, 0]
        if scores[0] > scores[1]:
            winners = [0]
        elif scores[1] > scores[0]:
            winners = [1]
        else:
            winners = [0, 1]
        share, odd = divmod(pot, len(winners))
        for winner in winners:
            payouts[winner] += share
        if odd:
            odd_chip_seat = 1 - self.button
            payouts[odd_chip_seat if odd_chip_seat in winners else winners[0]] += odd
        for seat, payout in zip(self.seats, payouts):
            seat.stack += payout
            seat.hand_committed = 0
            seat.street_committed = 0
        self.result = {
            "reason": "showdown",
            "winners": winners,
            "payouts": payouts,
            "scores": scores,
            "board": list(self.board),
            "revealedHoleCards": [list(seat.hole_cards) for seat in self.seats],
            "bestHands": [
                {"cards": hand[0], "category": hand[1], "importance": hand[2]} if hand else None
                for hand in best_hands
            ],
        }
        self._mark_terminal()

    def _award_fold(self, winner: int) -> None:
        pot = self.pot
        payouts = [0, 0]
        payouts[winner] = pot
        self.seats[winner].stack += pot
        for seat in self.seats:
            seat.hand_committed = 0
            seat.street_committed = 0
        self.result = {"reason": "fold", "winners": [winner], "payouts": payouts, "scores": None, "board": list(self.board)}
        self._mark_terminal()

    def _mark_terminal(self) -> None:
        self.street = Street.TERMINAL
        self.to_act = None
        self.pending.clear()
        self.current_bet = 0

    def observation(self, seat_number: int) -> dict[str, Any]:
        seat = self._seat(seat_number)
        best_hand = self._best_five(seat_number)
        preflop_hand = self._preflop_highlight(seat_number) if best_hand is None and not self.board else None
        return {
            "schemaVersion": self.SCHEMA_VERSION,
            "seed": self.seed,
            "button": self.button,
            "street": self.street.value,
            "board": list(self.board),
            "pot": self.pot,
            "smallBlind": self.small_blind,
            "bigBlind": self.big_blind,
            "currentBet": self.current_bet,
            "amountToCall": max(0, self.current_bet - seat.street_committed),
            "toAct": self.to_act,
            "heroSeat": seat_number,
            "holeCards": list(seat.hole_cards),
            "bestFive": best_hand[0] if best_hand else [],
            "handCategory": best_hand[1] if best_hand else preflop_hand[0] if preflop_hand else None,
            "handDescription": self._hand_description(seat_number, best_hand[1] if best_hand else preflop_hand[0] if preflop_hand else None),
            "bestFiveImportance": best_hand[2] if best_hand else preflop_hand[1] if preflop_hand else {},
            "seats": [item.to_dict(include_hole_cards=False) for item in self.seats],
            "actions": copy.deepcopy(self.actions),
            "legalActions": [action.to_dict() for action in self.legal_actions()] if self.to_act == seat_number else [],
            "result": copy.deepcopy(self.result),
        }

    def _best_five(self, seat_number: int) -> tuple[list[str], str, dict[str, int]] | None:
        cards = self._seat(seat_number).hole_cards + self.board
        if len(cards) < 5:
            return None
        best_cards = max(
            itertools.combinations(cards, 5),
            key=lambda combination: eval7.evaluate([eval7.Card(card) for card in combination]),
        )
        score = eval7.evaluate([eval7.Card(card) for card in best_cards])
        category = {
            "Straight Flush": "straight-flush",
            "Quads": "four-of-a-kind",
            "Full House": "full-house",
            "Flush": "flush",
            "Straight": "straight",
            "Trips": "three-of-a-kind",
            "Two Pair": "two-pair",
            "Pair": "one-pair",
            "High Card": "high-card",
        }[eval7.handtype(score)]
        cards_list = list(best_cards)
        return cards_list, category, self._card_importance(cards_list, category)

    def _preflop_highlight(self, seat_number: int) -> tuple[str, dict[str, int]]:
        cards = self._seat(seat_number).hole_cards
        if cards[0][0] == cards[1][0]:
            return "one-pair", {card: 3 for card in cards}
        rank_value = {rank: value for value, rank in enumerate("23456789TJQKA", start=2)}
        ordered = sorted(cards, key=lambda card: rank_value[card[0]], reverse=True)
        return "high-card", {ordered[0]: 3, ordered[1]: 1}

    def _hand_description(self, seat_number: int, category: str | None) -> str | None:
        if category is None:
            return None
        hole = self._seat(seat_number).hole_cards
        rank_name = {"T": "tens", "J": "jacks", "Q": "queens", "K": "kings", "A": "aces", **{str(value): f"{value}s" for value in range(2, 10)}}
        if not self.board:
            if hole[0][0] == hole[1][0]:
                return f"Pocket {rank_name[hole[0][0]]}"
            suited = "suited" if hole[0][1] == hole[1][1] else "offsuit"
            return f"{hole[0][0]}{hole[1][0]} {suited}"
        ranks = [card[0] for card in hole + self.board]
        counts = {rank: ranks.count(rank) for rank in set(ranks)}
        if category == "one-pair":
            pair_rank = next(rank for rank, count in counts.items() if count == 2)
            hole_count = sum(card[0] == pair_rank for card in hole)
            board_ranks = [card[0] for card in self.board]
            rank_value = {rank: value for value, rank in enumerate("23456789TJQKA", start=2)}
            if hole_count == 2:
                highest_board = max(rank_value[rank] for rank in board_ranks)
                return f"Overpair, pocket {rank_name[pair_rank]}" if rank_value[pair_rank] > highest_board else f"Pocket {rank_name[pair_rank]}"
            if hole_count == 0:
                return f"Paired board, {rank_name[pair_rank]}"
            distinct_board = sorted({rank_value[rank] for rank in board_ranks}, reverse=True)
            position = distinct_board.index(rank_value[pair_rank])
            label = "Top pair" if position == 0 else "Bottom pair" if position == len(distinct_board) - 1 else "Middle pair"
            return f"{label}, {rank_name[pair_rank]}"
        if category == "three-of-a-kind":
            trip_rank = next(rank for rank, count in counts.items() if count == 3)
            hole_count = sum(card[0] == trip_rank for card in hole)
            label = "Set" if hole_count == 2 else "Trips" if hole_count == 1 else "Three of a kind on board"
            return f"{label}, {rank_name[trip_rank]}"
        return {
            "straight-flush": "Straight flush",
            "four-of-a-kind": "Four of a kind",
            "full-house": "Full house",
            "flush": "Flush",
            "straight": "Straight",
            "two-pair": "Two pair",
            "high-card": "High card",
        }.get(category, category.replace("-", " ").title())

    @staticmethod
    def _card_importance(cards: list[str], category: str) -> dict[str, int]:
        """Describe each best-five card's structural role: 3 defining, 2 supporting, 1 kicker."""
        if category in ("straight", "straight-flush"):
            return {card: 3 for card in cards}
        rank_value = {rank: value for value, rank in enumerate("23456789TJQKA", start=2)}
        groups: dict[str, list[str]] = {}
        for card in cards:
            groups.setdefault(card[0], []).append(card)
        ordered = sorted(groups.values(), key=lambda group: (len(group), rank_value[group[0][0]]), reverse=True)
        importance: dict[str, int] = {}
        if category == "four-of-a-kind":
            levels = [3, 1]
        elif category == "full-house":
            levels = [3, 3]
        elif category == "three-of-a-kind":
            levels = [3, 1, 1]
        elif category == "two-pair":
            levels = [3, 3, 1]
        elif category == "one-pair":
            levels = [3, 1, 1, 1]
        else:  # Flush and high card are ranked by their highest cards.
            levels = [3, 2, 1, 1, 1]
        for group, level in zip(ordered, levels):
            for card in group:
                importance[card] = level
        return importance

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.SCHEMA_VERSION,
            "seed": self.seed,
            "button": self.button,
            "startingStacks": list(self.starting_stacks),
            "smallBlind": self.small_blind,
            "bigBlind": self.big_blind,
            "deck": list(self.deck),
            "burned": list(self.burned),
            "board": list(self.board),
            "street": self.street.value,
            "currentBet": self.current_bet,
            "lastFullRaise": self.last_full_raise,
            "toAct": self.to_act,
            "pending": sorted(self.pending),
            "seats": [seat.to_dict() for seat in self.seats],
            "actions": copy.deepcopy(self.actions),
            "result": copy.deepcopy(self.result),
        }

    @classmethod
    def replay(cls, serialized: dict[str, Any]) -> "HandState":
        if serialized.get("schemaVersion") != cls.SCHEMA_VERSION:
            raise InvalidState("unsupported hand schema version")
        hand = cls(
            seed=serialized["seed"],
            button=serialized["button"],
            starting_stacks=tuple(serialized["startingStacks"]),
            small_blind=serialized["smallBlind"],
            big_blind=serialized["bigBlind"],
        )
        for record in serialized["actions"][2:]:
            action_type = ActionType(record["type"])
            if action_type == ActionType.RAISE_TO:
                action = Action.raise_to(record["amount"])
            elif action_type == ActionType.ALL_IN:
                action = Action.all_in()
            else:
                action = Action(action_type)
            hand.apply(action)
        if hand.to_dict() != serialized:
            raise InvalidState("replayed state does not match serialized state")
        return hand

    def assert_invariants(self) -> None:
        all_cards = self.deck + self.burned + self.board + self.seats[0].hole_cards + self.seats[1].hole_cards
        if len(all_cards) != 52 or len(set(all_cards)) != 52:
            raise InvalidState("cards must be unique and account for the full deck")
        for card in all_cards:
            validate_card(card)
        if any(seat.stack < 0 or seat.street_committed < 0 or seat.hand_committed < 0 for seat in self.seats):
            raise InvalidState("chip counts cannot be negative")
        total = sum(seat.stack + seat.hand_committed for seat in self.seats)
        if total != sum(self.starting_stacks):
            raise InvalidState(f"chip conservation failed: {total} != {sum(self.starting_stacks)}")
        if any(seat.street_committed > seat.hand_committed for seat in self.seats):
            raise InvalidState("street commitment cannot exceed hand commitment")
        if self.terminal:
            if self.to_act is not None or self.pending or self.pot != 0 or self.result is None:
                raise InvalidState("invalid terminal state")
        elif self.to_act is not None and self.to_act not in self.pending:
            raise InvalidState("acting seat must be pending")
