from __future__ import annotations

import json
import random
import unittest

from game_trainer.poker import Action, ActionType, HandState, IllegalAction, Street


def action_types(hand: HandState) -> set[ActionType]:
    return {action.type for action in hand.legal_actions()}


class PokerEngineScenarioTests(unittest.TestCase):
    def test_heads_up_action_order_and_checkdown(self) -> None:
        hand = HandState(seed=11, button=0)
        self.assertEqual(hand.to_act, 0)
        self.assertEqual(hand.amount_to_call(), 50)

        hand.apply(Action.call())
        self.assertEqual(hand.to_act, 1)
        self.assertIn(ActionType.CHECK, action_types(hand))
        hand.apply(Action.check())

        self.assertEqual(hand.street, Street.FLOP)
        self.assertEqual(hand.to_act, 1)
        self.assertEqual(len(hand.board), 3)

        for expected_street in (Street.TURN, Street.RIVER):
            hand.apply(Action.check())
            hand.apply(Action.check())
            self.assertEqual(hand.street, expected_street)
            self.assertEqual(hand.to_act, 1)

        hand.apply(Action.check())
        hand.apply(Action.check())
        self.assertTrue(hand.terminal)
        self.assertEqual(hand.result["reason"], "showdown")
        self.assertEqual(sum(seat.stack for seat in hand.seats), 20_000)

    def test_raise_call_and_minimum_raise(self) -> None:
        hand = HandState(seed=12)
        legal_raise = next(action for action in hand.legal_actions() if action.type == ActionType.RAISE_TO)
        self.assertEqual(legal_raise.min_amount, 200)
        hand.apply(Action.raise_to(300))
        self.assertEqual(hand.current_bet, 300)
        self.assertEqual(hand.last_full_raise, 200)
        self.assertEqual(hand.amount_to_call(), 200)
        hand.apply(Action.call())
        self.assertEqual(hand.street, Street.FLOP)
        self.assertEqual(hand.pot, 600)

    def test_below_minimum_raise_is_rejected_without_mutation(self) -> None:
        hand = HandState(seed=13)
        before = hand.to_dict()
        with self.assertRaises(IllegalAction):
            hand.apply(Action.raise_to(150))
        self.assertEqual(hand.to_dict(), before)

    def test_fold_awards_entire_pot(self) -> None:
        hand = HandState(seed=14)
        hand.apply(Action.fold())
        self.assertTrue(hand.terminal)
        self.assertEqual(hand.result["winners"], [1])
        self.assertEqual(hand.result["payouts"], [0, 150])
        self.assertEqual([seat.stack for seat in hand.seats], [9950, 10050])

    def test_short_all_in_call_refunds_unmatched_chips(self) -> None:
        hand = HandState(seed=15, starting_stacks=(500, 10_000))
        hand.apply(Action.all_in())
        self.assertEqual(hand.amount_to_call(), 400)
        self.assertEqual(action_types(hand), {ActionType.FOLD, ActionType.CALL})
        hand.apply(Action.call())
        self.assertTrue(hand.terminal)
        self.assertEqual(len(hand.board), 5)
        self.assertEqual(sum(seat.stack for seat in hand.seats), 10_500)
        self.assertEqual(sum(hand.result["payouts"]), 1_000)

    def test_short_all_in_raise_is_legal_below_normal_minimum(self) -> None:
        hand = HandState(seed=16, starting_stacks=(150, 10_000))
        self.assertNotIn(ActionType.RAISE_TO, action_types(hand))
        self.assertIn(ActionType.ALL_IN, action_types(hand))
        hand.apply(Action.all_in())
        self.assertEqual(hand.current_bet, 150)
        self.assertEqual(hand.last_full_raise, 100)
        self.assertEqual(action_types(hand), {ActionType.FOLD, ActionType.CALL})

    def test_observation_never_exposes_opponent_hole_cards(self) -> None:
        hand = HandState(seed=17)
        observation = hand.observation(0)
        encoded = json.dumps(observation)
        for card in hand.seats[1].hole_cards:
            self.assertNotIn(card, encoded)
        self.assertEqual(observation["holeCards"], hand.seats[0].hole_cards)

    def test_observation_identifies_hero_best_five_after_flop(self) -> None:
        hand = HandState(seed=117)
        while hand.street == Street.PREFLOP:
            legal = hand.legal_actions()
            action = next(item for item in legal if item.type in (ActionType.CALL, ActionType.CHECK))
            hand.apply(Action(action.type))
        observation = hand.observation(0)
        self.assertEqual(len(observation["bestFive"]), 5)
        self.assertIn(observation["handCategory"], {
            "straight-flush", "four-of-a-kind", "full-house", "flush", "straight",
            "three-of-a-kind", "two-pair", "one-pair", "high-card",
        })
        self.assertEqual(set(observation["bestFiveImportance"]), set(observation["bestFive"]))

    def test_pair_cards_are_more_important_than_kickers(self) -> None:
        hand = HandState(seed=118)
        hand.seats[0].hole_cards = ["Ah", "Ad"]
        hand.board = ["2c", "5d", "9s"]
        observation = hand.observation(0)
        self.assertEqual(observation["handCategory"], "one-pair")
        self.assertEqual(observation["bestFiveImportance"]["Ah"], 3)
        self.assertEqual(observation["bestFiveImportance"]["Ad"], 3)
        self.assertEqual(observation["bestFiveImportance"]["9s"], 2)
        self.assertEqual(observation["bestFiveImportance"]["2c"], 1)

    def test_preflop_hole_cards_are_highlighted_by_role(self) -> None:
        hand = HandState(seed=119)
        hand.seats[0].hole_cards = ["Ah", "7d"]
        observation = hand.observation(0)
        self.assertEqual(observation["handCategory"], "high-card")
        self.assertEqual(observation["bestFiveImportance"], {"Ah": 3, "7d": 1})
        hand.seats[0].hole_cards = ["Qs", "Qh"]
        pair_observation = hand.observation(0)
        self.assertEqual(pair_observation["handCategory"], "one-pair")
        self.assertEqual(pair_observation["handDescription"], "Pocket queens")
        self.assertEqual(set(pair_observation["bestFiveImportance"].values()), {3})

    def test_contextual_pair_and_trips_terminology(self) -> None:
        top_pair = HandState(seed=1)
        top_pair.seats[0].hole_cards = ["Ah", "7d"]
        top_pair.board = ["Ad", "9s", "2c"]
        self.assertEqual(top_pair.observation(0)["handDescription"], "Top pair, aces")
        set_hand = HandState(seed=2)
        set_hand.seats[0].hole_cards = ["Ah", "Ad"]
        set_hand.board = ["Ac", "9s", "2c"]
        self.assertEqual(set_hand.observation(0)["handDescription"], "Set, aces")

    def test_serialized_hand_replays_exactly(self) -> None:
        hand = HandState(seed=18, button=1)
        hand.apply(Action.raise_to(250))
        hand.apply(Action.call())
        hand.apply(Action.check())
        hand.apply(Action.raise_to(300))
        hand.apply(Action.call())
        serialized = hand.to_dict()
        replayed = HandState.replay(serialized)
        self.assertEqual(replayed.to_dict(), serialized)


class PokerEngineInvariantTests(unittest.TestCase):
    def test_randomized_legal_play_preserves_invariants(self) -> None:
        chooser = random.Random(20260828)
        for seed in range(2500):
            stacks = (chooser.randint(2, 200) * 50, chooser.randint(2, 200) * 50)
            hand = HandState(seed=seed, button=seed % 2, starting_stacks=stacks)
            steps = 0
            while not hand.terminal:
                legal = hand.legal_actions()
                self.assertTrue(legal)
                choice = chooser.choice(legal)
                if choice.type == ActionType.RAISE_TO:
                    amount = chooser.randint(choice.min_amount, choice.max_amount)
                    action = Action.raise_to(amount)
                else:
                    action = Action(choice.type)
                hand.apply(action)
                hand.assert_invariants()
                steps += 1
                self.assertLess(steps, 100)
            self.assertEqual(sum(seat.stack for seat in hand.seats), sum(stacks))
            self.assertEqual(hand.pot, 0)
            HandState.replay(hand.to_dict())


if __name__ == "__main__":
    unittest.main()
