from __future__ import annotations

import unittest

from game_trainer.range_estimator_dataset import (
    generate_synthetic_dataset,
    legal_villain_combos,
    validate_request,
)


class RangeEstimatorDatasetTests(unittest.TestCase):
    def test_legal_combos_exclude_hero_and_board_blockers(self) -> None:
        combos = legal_villain_combos(["Ah", "Kd"], ["7c", "5s", "2d"])
        self.assertEqual(len(combos), 1_081)
        self.assertTrue(all(not {"Ah", "Kd", "7c", "5s", "2d"}.intersection(combo) for combo in combos))

    def test_dataset_is_deterministic_and_hides_label_from_context(self) -> None:
        first = generate_synthetic_dataset(19, 25)
        self.assertEqual(first, generate_synthetic_dataset(19, 25))
        self.assertEqual(first["manifest"]["hands"], 25)
        for record in first["records"]:
            context = record["context"]
            target = set(record["targetVillainCards"])
            self.assertEqual(set(context), {
                "schemaVersion", "rulesetId", "villainSeat", "heroCards", "board",
                "position", "potChips", "effectiveStacks", "actions", "priorId",
            })
            self.assertFalse(target.intersection(context["heroCards"] + context["board"]))
            self.assertTrue(
                any(
                    set(combo) == target
                    for combo in legal_villain_combos(context["heroCards"], context["board"])
                )
            )

    def test_request_rejects_blocker_conflicts(self) -> None:
        request = generate_synthetic_dataset(4, 1)["records"][0]["context"]
        request["board"] = [request["heroCards"][0]]
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_request(request)


if __name__ == "__main__":
    unittest.main()
