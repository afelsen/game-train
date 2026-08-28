from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from game_trainer.poker.cards import validate_card
from game_trainer.training_spots import curated_spots, seeded_random_spots

ROOT = Path(__file__).resolve().parent.parent


class TrainingSpotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema = json.loads((ROOT / "schemas" / "solver-job-request.schema.json").read_text())
        cls.validator = Draft202012Validator(schema)

    def assert_valid_spot(self, spot: dict[str, object]) -> None:
        request = spot["request"]
        assert isinstance(request, dict)
        self.validator.validate(request)
        cards = [request["flop"][index : index + 2] for index in range(0, 6, 2)] + [request["turn"]]
        for card in cards:
            validate_card(card)
        self.assertEqual(len(cards), len(set(cards)))

    def test_curated_spots_have_stable_unique_identifiers(self) -> None:
        spots = curated_spots()
        self.assertGreaterEqual(len(spots), 3)
        self.assertEqual(len({spot["id"] for spot in spots}), len(spots))
        for spot in spots:
            self.assertEqual(spot["source"], "curated")
            self.assert_valid_spot(spot)

    def test_seeded_random_spots_are_reproducible_and_valid(self) -> None:
        first = seeded_random_spots(1_234, 5)
        self.assertEqual(first, seeded_random_spots(1_234, 5))
        self.assertNotEqual(first, seeded_random_spots(1_235, 5))
        for spot in first:
            self.assertEqual(spot["source"], "seeded-random")
            self.assert_valid_spot(spot)

    def test_random_count_is_bounded(self) -> None:
        for count in (0, 21):
            with self.assertRaisesRegex(ValueError, "count"):
                seeded_random_spots(1, count)


if __name__ == "__main__":
    unittest.main()
