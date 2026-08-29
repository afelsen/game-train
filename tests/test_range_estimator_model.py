from __future__ import annotations

import unittest

from game_trainer.range_estimator_dataset import generate_synthetic_dataset
from game_trainer.range_estimator_model import RangeEstimatorModel, RangeEstimatorTrainer


class RangeEstimatorModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = generate_synthetic_dataset(41, 120)

    def test_training_is_reproducible_and_emits_calibration_metrics(self) -> None:
        first = list(RangeEstimatorTrainer(9).train_events(self.dataset, epochs=3, learning_rate=0.02))
        second = list(RangeEstimatorTrainer(9).train_events(self.dataset, epochs=3, learning_rate=0.02))
        self.assertEqual(first, second)
        complete = first[-1]
        self.assertEqual(complete["event"], "complete")
        self.assertIn("validationNll", complete)
        self.assertIn("validationEce", complete)
        self.assertEqual(len(complete["checkpoint"]["weights"]), 19)

    def test_strength_action_interactions_beat_uniform_baseline(self) -> None:
        dataset = generate_synthetic_dataset(20260828, 300)
        events = list(
            RangeEstimatorTrainer(7).train_events(
                dataset, epochs=8, learning_rate=0.03, report_every_examples=1_000
            )
        )
        complete = events[-1]
        self.assertGreater(complete["validationNllGain"], 0.01)

    def test_prediction_masks_blockers_and_normalizes(self) -> None:
        events = list(RangeEstimatorTrainer(9).train_events(self.dataset, epochs=1, learning_rate=0.02))
        checkpoint = events[-1]["checkpoint"]
        model = RangeEstimatorModel(
            tuple(checkpoint["weights"]), checkpoint["datasetHash"], checkpoint["calibrationTemperature"]
        )
        request = self.dataset["records"][0]["context"]
        prediction = model.predict(request)
        self.assertAlmostEqual(sum(combo["weight"] for combo in prediction["combos"]), 1.0)
        known = set(request["heroCards"] + request["board"])
        self.assertTrue(all(not known.intersection(combo["cards"]) for combo in prediction["combos"]))
        self.assertEqual(prediction["diagnostics"]["normalizationError"], 0.0)


if __name__ == "__main__":
    unittest.main()
