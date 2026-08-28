import copy
import unittest

from game_trainer.nlhe_mccfr import RestrictedNlheMccfrTrainer


def request(**updates):
    value = {
        "schemaVersion": "1.0.0",
        "game": "restricted-hu-nlhe-flop",
        "algorithm": "external-sampling-mccfr",
        "mode": "headless",
        "iterations": 12,
        "seed": 27,
        "reportEvery": 4,
    }
    value.update(updates)
    return value


class RestrictedNlheMccfrTests(unittest.TestCase):
    def test_seeded_training_is_reproducible(self):
        first = list(RestrictedNlheMccfrTrainer(seed=27).train_events(request()))[-1]
        second = list(RestrictedNlheMccfrTrainer(seed=27).train_events(request()))[-1]
        self.assertEqual(first["artifactHash"], second["artifactHash"])
        self.assertEqual(first["checkpoint"], second["checkpoint"])
        self.assertGreater(first["informationSets"], 0)
        for node in first["strategy"]:
            self.assertAlmostEqual(sum(node["actions"].values()), 1.0)

    def test_checkpoint_resume_matches_uninterrupted_training(self):
        partial = list(
            RestrictedNlheMccfrTrainer(seed=27).train_events(request(iterations=5))
        )[-1]
        resumed_request = request(iterations=12, checkpoint=partial["checkpoint"])
        resumed = list(RestrictedNlheMccfrTrainer(seed=27).train_events(resumed_request))[-1]
        uninterrupted = list(RestrictedNlheMccfrTrainer(seed=27).train_events(request()))[-1]
        self.assertEqual(resumed["artifactHash"], uninterrupted["artifactHash"])
        self.assertEqual(resumed["checkpoint"], uninterrupted["checkpoint"])

    def test_visual_mode_reports_chartable_progress(self):
        events = list(
            RestrictedNlheMccfrTrainer(seed=3).train_events(
                request(seed=3, mode="visual", iterations=6, reportEvery=2)
            )
        )
        self.assertEqual(
            [event["event"] for event in events],
            ["started", "progress", "progress", "progress", "complete"],
        )
        self.assertEqual([event["iteration"] for event in events[1:4]], [2, 4, 6])
        self.assertTrue(all(event["positiveRegret"] >= 0 for event in events[1:4]))

    def test_checkpoint_rejects_tampering_and_wrong_seed(self):
        complete = list(
            RestrictedNlheMccfrTrainer(seed=27).train_events(request(iterations=2))
        )[-1]
        tampered = copy.deepcopy(complete["checkpoint"])
        tampered["completedIterations"] = 3
        with self.assertRaisesRegex(ValueError, "hash"):
            RestrictedNlheMccfrTrainer(seed=27).load_checkpoint(tampered)
        with self.assertRaisesRegex(ValueError, "seed"):
            RestrictedNlheMccfrTrainer(seed=99).load_checkpoint(complete["checkpoint"])


if __name__ == "__main__":
    unittest.main()
