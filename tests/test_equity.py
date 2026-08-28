from __future__ import annotations

import unittest

from game_trainer.equity import calculate_equity


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

    def test_duplicate_cards_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            calculate_equity(["Ah", "Ah"], [])
