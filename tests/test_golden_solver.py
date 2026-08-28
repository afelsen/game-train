from __future__ import annotations

import unittest

from game_trainer.golden_solver import verify_golden_result


class GoldenSolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = {"startingPot": 100}
        self.expected = {
            "configHash": "a" * 64,
            "iterations": 100,
            "exploitability": 0.5,
            "oopEv": 45.0,
            "ipEv": 55.0,
            "actions": {"Check": 0.75, "Bet(60)": 0.25},
        }
        self.actual = {
            "event": "complete",
            "configHash": "a" * 64,
            "iterations": 100,
            "exploitability": 0.5,
            "oopEv": 45.0,
            "ipEv": 55.0,
            "actions": [
                {"action": "Check", "probability": 0.75},
                {"action": "Bet(60)", "probability": 0.25},
            ],
        }
        self.tolerances = {"probability": 1e-5, "value": 1e-3, "exploitability": 1e-3}

    def test_matching_result_passes(self) -> None:
        self.assertEqual(
            verify_golden_result(self.request, self.expected, self.actual, self.tolerances), []
        )

    def test_strategy_and_conservation_regressions_fail(self) -> None:
        actual = dict(self.actual, oopEv=40.0)
        actual["actions"] = [
            {"action": "Check", "probability": 0.8},
            {"action": "Bet(60)", "probability": 0.1},
        ]
        errors = verify_golden_result(self.request, self.expected, actual, self.tolerances)
        self.assertTrue(any("Check probability" in error for error in errors))
        self.assertTrue(any("probabilities sum" in error for error in errors))
        self.assertTrue(any("seat EVs sum" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
