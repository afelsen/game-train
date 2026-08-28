import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from game_trainer.nlhe_abstraction import (
    UnsupportedTrainingState,
    encode_information_set,
    legal_abstract_actions,
    translate_bet_size,
)

ROOT = Path(__file__).resolve().parent.parent


def state(**updates):
    value = {
        "street": "flop",
        "actor": 0,
        "position": "oop",
        "holeCards": ["Ad", "Qh"],
        "board": ["Td", "9d", "6h"],
        "potBb": 5.5,
        "effectiveStackBb": 97.25,
        "toCallBb": 0,
        "history": [],
    }
    value.update(updates)
    return value


class NlheAbstractionTests(unittest.TestCase):
    def test_manifest_matches_schema(self):
        schema = json.loads((ROOT / "schemas/nlhe-training-abstraction.schema.json").read_text())
        manifest = json.loads((ROOT / "manifests/restricted-hu-nlhe-flop-cfr-v1.json").read_text())
        Draft202012Validator(schema).validate(manifest)

    def test_global_suit_permutations_share_information_set(self):
        first = encode_information_set(state())
        second = encode_information_set(state(holeCards=["Ah", "Qs"], board=["Th", "9h", "6s"]))
        self.assertEqual(first["informationSetId"], second["informationSetId"])
        self.assertEqual(first["canonicalJson"], second["canonicalJson"])

    def test_private_card_input_order_does_not_change_identity(self):
        first = encode_information_set(state(holeCards=["Ac", "Qs"]))
        second = encode_information_set(state(holeCards=["Qs", "Ac"]))
        self.assertEqual(first["informationSetId"], second["informationSetId"])

    def test_private_cards_and_history_change_information_set(self):
        baseline = encode_information_set(state())["informationSetId"]
        private_changed = encode_information_set(state(holeCards=["Kd", "Qh"]))["informationSetId"]
        history_changed = encode_information_set(state(history=["flop:oop:check"], actor=1, position="ip"))["informationSetId"]
        self.assertNotEqual(baseline, private_changed)
        self.assertNotEqual(baseline, history_changed)

    def test_rejects_states_outside_contract(self):
        invalid = [
            state(street="preflop", board=[]),
            state(board=["As", "Ks", "2d"]),
            state(potBb=5.1),
            state(holeCards=["Td", "As"]),
        ]
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(UnsupportedTrainingState):
                encode_information_set(candidate)

    def test_legal_actions_apply_raise_cap(self):
        self.assertEqual(legal_abstract_actions(state()), ("check", "bet-50", "bet-100", "all-in"))
        facing_bet = state(toCallBb=2.75, history=["flop:ip:bet-50"])
        self.assertEqual(legal_abstract_actions(facing_bet), ("fold", "call", "raise-2.5x", "all-in"))
        facing_raise = state(toCallBb=6.75, history=["flop:oop:bet-50", "flop:ip:raise-2.5x"])
        self.assertEqual(legal_abstract_actions(facing_raise), ("fold", "call"))

    def test_rejects_two_raises_on_one_street(self):
        with self.assertRaises(UnsupportedTrainingState):
            encode_information_set(state(history=["flop:oop:raise-2.5x", "flop:ip:raise-2.5x"]))

    def test_off_tree_translation_is_nearest_and_ties_up(self):
        self.assertEqual(translate_bet_size(5, 10, 100), "bet-50")
        self.assertEqual(translate_bet_size(7.5, 10, 100), "bet-100")
        self.assertEqual(translate_bet_size(90, 10, 100), "all-in")


if __name__ == "__main__":
    unittest.main()
