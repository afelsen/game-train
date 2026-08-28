from __future__ import annotations

import unittest

from game_trainer.equity import calculate_equity, calculate_hand_chances
from game_trainer.range_estimator import estimate_villain_range


class EquityCalculatorTests(unittest.TestCase):
    def test_river_equity_is_exact_and_normalized(self) -> None:
        result = calculate_equity(["Ah", "Ad"], ["Ac", "Ks", "7d", "2c", "3h"])
        self.assertEqual(result["method"], "exact")
        self.assertEqual(result["samples"], 990)
        self.assertAlmostEqual(result["equity"], (result["wins"] + result["ties"] / 2) / result["samples"])
        self.assertEqual(result["standardError"], 0)

    def test_preflop_equity_is_sampled_and_repeatable(self) -> None:
        first = calculate_equity(["Ah", "Kh"], [])
        second = calculate_equity(["Ah", "Kh"], [])
        self.assertEqual(first, second)
        self.assertEqual(first["method"], "sampled")
        self.assertEqual(first["samples"], 20_000)
        self.assertGreater(first["equity"], 0.6)

    def test_action_weighted_range_changes_equity_reproducibly(self) -> None:
        estimated = estimate_villain_range(
            ["Ah", "Kd"],
            ["7c", "5s", "2d"],
            [{"seat": 1, "street": "flop", "type": "raise-to", "amount": 600}],
        )
        first = calculate_equity(
            ["Ah", "Kd"], ["7c", "5s", "2d"], opponent_weights=estimated["combos"]
        )
        second = calculate_equity(
            ["Ah", "Kd"], ["7c", "5s", "2d"], opponent_weights=estimated["combos"]
        )
        random_equity = calculate_equity(["Ah", "Kd"], ["7c", "5s", "2d"])
        self.assertEqual(first, second)
        self.assertEqual(first["opponentRange"], "action-weighted-v1")
        self.assertLess(first["equity"], random_equity["equity"])
        self.assertEqual(estimated["observedActions"], 1)
        self.assertEqual(len(estimated["topClasses"]), 8)

    def test_preflop_actions_do_not_update_behavior_range(self) -> None:
        no_actions = estimate_villain_range(["Ah", "Kd"], [], [])
        raised = estimate_villain_range(
            ["Ah", "Kd"],
            [],
            [
                {
                    "seat": 1,
                    "street": "preflop",
                    "type": "raise-to",
                    "amount": 300,
                }
            ],
        )
        self.assertEqual(raised, no_actions)
        self.assertEqual(raised["observedActions"], 0)

    def test_duplicate_cards_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            calculate_equity(["Ah", "Ah"], [])

    def test_flop_hand_chances_are_exact_and_cumulative(self) -> None:
        result = calculate_hand_chances(["Ah", "Kh"], ["Qh", "Jh", "2c"])
        self.assertEqual(result["method"], "exact")
        self.assertEqual(result["samples"], 1081)
        self.assertGreater(result["atLeast"]["straight-flush"], 0)
        self.assertGreaterEqual(result["atLeast"]["straight"], result["atLeast"]["flush"])
        self.assertEqual(result["atLeast"]["high-card"], 1)
        self.assertEqual(result["combinations"]["straight-flush"], 46)
        self.assertEqual(result["combinations"]["flush"], 332)
        self.assertAlmostEqual(
            result["combinations"]["flush"] / result["samples"],
            result["exact"]["flush"],
        )
        self.assertEqual(result["outs"], result["combinations"])
        self.assertEqual(result["baselineLabel"], "random legal hand")
        self.assertEqual(result["baselineSamples"], 5_000)
        self.assertGreater(
            result["atLeast"]["flush"], result["baselineAtLeast"]["flush"]
        )

    def test_preflop_hand_chances_are_sampled_and_repeatable(self) -> None:
        first = calculate_hand_chances(["7h", "2c"], [])
        second = calculate_hand_chances(["7h", "2c"], [])
        self.assertEqual(first, second)
        self.assertEqual(first["method"], "sampled")
        self.assertEqual(first["samples"], 20_000)
