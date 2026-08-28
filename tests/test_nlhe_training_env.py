import unittest

from game_trainer.nlhe_training_env import (
    InvalidTrainingAction,
    RestrictedNlheState,
    compatible_private_deals,
    expand_range,
)


class RangeExpansionTests(unittest.TestCase):
    def test_expands_plus_and_interval_notation(self):
        self.assertEqual(len(expand_range("66+")), 9 * 6)
        self.assertEqual(len(expand_range("A8s+")), 6 * 4)
        self.assertEqual(len(expand_range("A5s-A4s")), 2 * 4)
        self.assertEqual(len(expand_range("AQs-A2s")), 11 * 4)
        self.assertEqual(len(expand_range("ATo+")), 4 * 12)
        self.assertEqual(len(expand_range("QQ-22")), 11 * 6)

    def test_deduplicates_and_applies_board_blockers(self):
        combos = expand_range("AA,AKs,AKs", blocked=("Ac",))
        self.assertEqual(len(combos), 3 + 3)
        self.assertEqual(combos, tuple(sorted(combos)))

    def test_manifest_private_deals_are_deterministic_and_compatible(self):
        first = compatible_private_deals(("Td", "9d", "6h"))
        second = compatible_private_deals(("Td", "9d", "6h"))
        self.assertEqual(first, second)
        self.assertGreater(len(first), 10_000)
        for oop, ip in first:
            self.assertTrue(set(oop).isdisjoint(ip))


class RestrictedEnvironmentTests(unittest.TestCase):
    def root(self):
        return RestrictedNlheState.root(("Ac", "Ah"), ("Kc", "Qc"))

    def test_check_check_reaches_exact_turn_chance_node(self):
        root = self.root()
        self.assertEqual(root.information_set(), self.root().information_set())
        state = root.apply("check").apply("check")
        self.assertTrue(state.awaiting_chance)
        with self.assertRaises(InvalidTrainingAction):
            state.information_set()
        outcomes = state.chance_outcomes()
        self.assertEqual(len(outcomes), 45)
        self.assertAlmostEqual(sum(probability for _, probability in outcomes), 1.0)
        turn = state.deal(outcomes[0][0])
        self.assertEqual(turn.street, "turn")
        self.assertEqual(turn.actor, 0)

    def test_bet_call_moves_chips_and_closes_street(self):
        root = self.root()
        after_bet = root.apply("bet-50")
        self.assertEqual(after_bet.pot_q, 33)
        self.assertEqual(after_bet.committed_q, (11, 0))
        self.assertEqual(after_bet.legal_actions(), ("fold", "call", "raise-2.5x", "all-in"))
        after_call = after_bet.apply("call")
        self.assertEqual(after_call.pot_q, 44)
        self.assertEqual(after_call.committed_q, (0, 0))
        self.assertTrue(after_call.awaiting_chance)

    def test_raise_cap_and_fold_terminal_utility(self):
        raised = self.root().apply("bet-100").apply("raise-2.5x")
        self.assertEqual(raised.legal_actions(), ("fold", "call"))
        folded = raised.apply("fold")
        self.assertTrue(folded.terminal)
        self.assertLess(folded.terminal_utility_oop_q, 0)
        with self.assertRaises(InvalidTrainingAction):
            folded.apply("call")

    def test_deterministic_river_showdown(self):
        state = self.root().apply("check").apply("check")
        state = state.deal("2c").apply("check").apply("check")
        state = state.deal("3c").apply("check").apply("check")
        self.assertTrue(state.terminal)
        self.assertGreater(state.terminal_utility_oop_q, 0)

    def test_all_in_call_runs_out_only_through_chance_nodes(self):
        state = self.root().apply("all-in").apply("call")
        self.assertTrue(state.awaiting_chance)
        self.assertEqual(state.actor, None)
        state = state.deal("2c")
        self.assertTrue(state.awaiting_chance)
        state = state.deal("3c")
        self.assertTrue(state.terminal)

    def test_root_rejects_blocked_or_out_of_range_hands(self):
        with self.assertRaises(ValueError):
            RestrictedNlheState.root(("Td", "Ah"), ("Kc", "Qc"))
        with self.assertRaises(ValueError):
            RestrictedNlheState.root(("2c", "7h"), ("Kc", "Qc"))


if __name__ == "__main__":
    unittest.main()
