from __future__ import annotations

import unittest

from game_trainer.solver_crosscheck import blocker_weighted_action_mix, expand_explicit_range


class SolverCrosscheckTests(unittest.TestCase):
    def test_explicit_range_expansion_respects_shape_weights_and_board(self) -> None:
        combos = expand_explicit_range("AA:0.5,AKs,AKo", board=("Ac",))
        self.assertEqual(len(combos), 3 + 3 + 9)
        self.assertEqual(combos[frozenset(("Ad", "Ah"))], 0.5)
        self.assertNotIn(frozenset(("Ac", "As")), combos)

    def test_action_mix_accounts_for_opponent_blockers(self) -> None:
        own = {
            frozenset(("As", "Ks")): 1.0,
            frozenset(("Ah", "Kh")): 1.0,
        }
        opponent = {
            frozenset(("As", "Qd")): 1.0,
            frozenset(("2c", "3c")): 1.0,
        }
        strategy = {"AsKs": [1.0, 0.0], "AhKh": [0.0, 1.0]}
        mix = blocker_weighted_action_mix(strategy, ["CHECK", "BET"], own, opponent)
        self.assertAlmostEqual(mix["CHECK"], 1 / 3)
        self.assertAlmostEqual(mix["BET"], 2 / 3)


if __name__ == "__main__":
    unittest.main()
