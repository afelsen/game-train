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
    """Authoritative state for a two-to-six-player no-limit Hold'em hand.

    Chip amounts are integers. An action's raise amount is the player's total
    commitment on the current street, matching common poker-engine semantics.
    """

    SCHEMA_VERSION = "1.0.0"

    def __init__(
        self,
        *,
        seed: int,
        button: int = 0,
        starting_stacks: tuple[int, ...] = (10_000, 10_000),
        small_blind: int = 50,
        big_blind: int = 100,
    ) -> None:
        player_count = len(starting_stacks)
        if not 2 <= player_count <= 6:
            raise InvalidState("starting stacks must contain two to six players")
        if button not in range(player_count):
            raise InvalidState("button must identify an occupied seat")
        if any(type(value) is not int or value <= 0 for value in starting_stacks):
            raise InvalidState("starting stacks must be positive integers")
        if type(small_blind) is not int or type(big_blind) is not int or not (0 < small_blind <= big_blind):
            raise InvalidState("blinds must be positive integers with small <= big")

        self.seed = seed
        self.button = button
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.starting_stacks = tuple(starting_stacks)
        self.player_count = player_count
        self.deck = shuffled_deck(seed)
        self.burned: list[str] = []
        self.board: list[str] = []
        self.street = Street.PREFLOP
        self.current_bet = 0
        self.last_full_raise = big_blind
        small_blind_seat = button if player_count == 2 else self._clockwise(button)
        big_blind_seat = self._clockwise(small_blind_seat)
        self.to_act: int | None = button if player_count == 2 else self._clockwise(big_blind_seat)
        self.pending: set[int] = set(range(player_count))
        self.actions: list[dict[str, Any]] = []
        self.result: dict[str, Any] | None = None

        holes = {seat: [] for seat in range(player_count)}
        first_dealt = self._clockwise(button)
        deal_order = [((first_dealt + offset) % player_count) for offset in range(player_count)]
        for _ in range(2):
            for seat in deal_order:
                holes[seat].append(self.deck.pop())
        self.seats = [
            SeatState(seat, starting_stacks[seat], holes[seat])
            for seat in range(player_count)
        ]

        self._post_blind(small_blind_seat, small_blind, "small-blind")
        self._post_blind(big_blind_seat, big_blind, "big-blind")
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
        if seat not in range(self.player_count):
            raise InvalidState(f"invalid seat {seat}")
        return self.seats[seat]

    def _clockwise(self, seat: int) -> int:
        return (seat + 1) % self.player_count

    def _next_pending(self, after: int) -> int | None:
        for offset in range(1, self.player_count + 1):
            candidate = (after + offset) % self.player_count
            if candidate in self.pending and self._seat(candidate).status == PlayerStatus.ACTIVE:
                return candidate
        return None

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

        opponents_can_act = any(
            opponent.seat != seat.seat and opponent.status == PlayerStatus.ACTIVE
            for opponent in self.seats
        )
        if seat.stack > to_call and opponents_can_act:
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
        to_call = self.amount_to_call(seat_number)
        maximum = seat.street_committed + seat.stack
        record_amount = 0

        if action.type == ActionType.FOLD:
            if to_call <= 0:
                raise IllegalAction("cannot fold when checking is available")
            seat.status = PlayerStatus.FOLDED
            self.pending.discard(seat_number)
            self.actions.append({"street": self.street.value, "seat": seat_number, "type": "fold", "amount": 0})
            remaining = [item.seat for item in self.seats if item.status != PlayerStatus.FOLDED]
            if len(remaining) == 1:
                self._award_fold(remaining[0])
            else:
                self._continue_after_action(seat_number)
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
            if not any(
                opponent.seat != seat_number and opponent.status == PlayerStatus.ACTIVE
                for opponent in self.seats
            ):
                raise IllegalAction("cannot raise when no opponent can act")
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
            self.pending = {
                opponent.seat
                for opponent in self.seats
                if opponent.seat != seat_number and opponent.status == PlayerStatus.ACTIVE
            }

        else:
            raise IllegalAction(f"unsupported action {action.type}")

        self.actions.append({"street": self.street.value, "seat": seat_number, "type": action.type.value, "amount": record_amount})
        self._continue_after_action(seat_number)
        self.assert_invariants()

    def _continue_after_action(self, after: int) -> None:
        next_seat = self._next_pending(after)
        if next_seat is not None:
            self.to_act = next_seat
            return
        self._close_betting_round()

    def _close_betting_round(self) -> None:
        self.to_act = None
        active = [seat for seat in self.seats if seat.status == PlayerStatus.ACTIVE]
        if len(active) <= 1 and any(
            seat.status == PlayerStatus.ALL_IN for seat in self.seats
        ):
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
        self.pending = {seat.seat for seat in self.seats if seat.status == PlayerStatus.ACTIVE}
        self.to_act = self._next_pending(self.button)
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

    def _runout_and_showdown(self) -> None:
        while len(self.board) < 5:
            deal_count = 3 if len(self.board) == 0 else 1
            self._burn_and_deal(deal_count)
        self._showdown()

    def _hand_score(self, seat: SeatState) -> int:
        cards = [eval7.Card(card) for card in seat.hole_cards + self.board]
        return int(eval7.evaluate(cards))

    def _showdown(self) -> None:
        scores = [
            self._hand_score(seat) if seat.status != PlayerStatus.FOLDED else None
            for seat in self.seats
        ]
        best_hands = [
            self._best_five(seat.seat) if seat.status != PlayerStatus.FOLDED else None
            for seat in self.seats
        ]
        payouts = [0] * self.player_count
        levels = sorted({seat.hand_committed for seat in self.seats if seat.hand_committed > 0})
        previous = 0
        all_winners: set[int] = set()
        for level in levels:
            contributors = [seat for seat in self.seats if seat.hand_committed >= level]
            pot_slice = (level - previous) * len(contributors)
            eligible = [seat.seat for seat in contributors if seat.status != PlayerStatus.FOLDED]
            if not eligible:
                share, odd = divmod(pot_slice, len(contributors))
                for contributor in contributors:
                    payouts[contributor.seat] += share
                payouts[contributors[0].seat] += odd
                previous = level
                continue
            best_score = max(scores[seat] for seat in eligible)
            winners = [seat for seat in eligible if scores[seat] == best_score]
            share, odd = divmod(pot_slice, len(winners))
            for winner in winners:
                payouts[winner] += share
                all_winners.add(winner)
            for offset in range(1, self.player_count + 1):
                odd_seat = (self.button + offset) % self.player_count
                if odd <= 0:
                    break
                if odd_seat in winners:
                    payouts[odd_seat] += 1
                    odd -= 1
            previous = level
        for seat, payout in zip(self.seats, payouts):
            seat.stack += payout
            seat.hand_committed = 0
            seat.street_committed = 0
        self.result = {
            "reason": "showdown",
            "winners": sorted(all_winners),
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
        payouts = [0] * self.player_count
        payouts[winner] = pot
        self.seats[winner].stack += pot
        for seat in self.seats:
            seat.hand_committed = 0
            seat.street_committed = 0
        self.result = {
            "reason": "fold",
            "winners": [winner],
            "payouts": payouts,
            "scores": None,
            "board": list(self.board),
            "revealedHoleCards": [list(seat.hole_cards) for seat in self.seats],
        }
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
        rank_single = {"T": "ten", "J": "jack", "Q": "queen", "K": "king", "A": "ace", **{str(value): str(value) for value in range(2, 10)}}
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
        best = self._best_five(seat_number)
        best_cards = best[0] if best else hole + self.board
        best_ranks = [card[0] for card in best_cards]
        best_counts = {rank: best_ranks.count(rank) for rank in set(best_ranks)}
        rank_value = {rank: value for value, rank in enumerate("23456789TJQKA", start=2)}
        if category == "two-pair":
            pairs = sorted(
                (rank for rank, count in best_counts.items() if count == 2),
                key=rank_value.get,
                reverse=True,
            )
            return f"Two pair, {rank_name[pairs[0]]} and {rank_name[pairs[1]]}"
        if category == "full-house":
            trips = next(rank for rank, count in best_counts.items() if count == 3)
            pair = next(rank for rank, count in best_counts.items() if count == 2)
            return f"Full house, {rank_name[trips]} full of {rank_name[pair]}"
        if category == "four-of-a-kind":
            quads = next(rank for rank, count in best_counts.items() if count == 4)
            return f"Four of a kind, {rank_name[quads]}"
        if category in ("flush", "high-card"):
            high = max(best_ranks, key=rank_value.get)
            return f"{rank_single[high].title()}-high {'flush' if category == 'flush' else 'hand'}"
        if category in ("straight", "straight-flush"):
            values = {rank_value[rank] for rank in best_ranks}
            high_value = 5 if values == {14, 2, 3, 4, 5} else max(values)
            high_rank = next(rank for rank, value in rank_value.items() if value == high_value)
            label = "straight flush" if category == "straight-flush" else "straight"
            return f"{rank_single[high_rank].title()}-high {label}"
        return {
            "straight-flush": "Straight flush",
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
        all_cards = self.deck + self.burned + self.board + [
            card for seat in self.seats for card in seat.hole_cards
        ]
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
