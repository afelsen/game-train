from __future__ import annotations

import unittest

from game_trainer.leduc_cfr import LeducCfrTrainer


def request(iterations: int, checkpoint: dict | None = None) -> dict:
    value = {
        "schemaVersion": "1.0.0",
        "game": "leduc-holdem",
        "algorithm": "cfr",
        "mode": "headless",
        "iterations": iterations,
        "seed": 19,
        "reportEvery": 2,
    }
    if checkpoint is not None:
        value["checkpoint"] = checkpoint
    return value


class LeducCfrTests(unittest.TestCase):
    def test_training_produces_usable_policy_and_checkpoint(self) -> None:
        complete = list(LeducCfrTrainer(19).train_events(request(4)))[-1]
        self.assertEqual(complete["event"], "complete")
        self.assertEqual(complete["game"], "leduc-holdem")
        self.assertIn("referenceScore", complete)
        self.assertGreater(len(complete["strategy"]), 0)
        self.assertEqual(complete["checkpoint"]["completedIterations"], 4)
        actions = complete["strategy"][0]["actions"]
        self.assertAlmostEqual(sum(actions.values()), 1.0)

    def test_resume_matches_uninterrupted_training_exactly(self) -> None:
        first = list(LeducCfrTrainer(19).train_events(request(3)))[-1]
        resumed = list(
            LeducCfrTrainer(19).train_events(request(7, first["checkpoint"]))
        )[-1]
        uninterrupted = list(LeducCfrTrainer(19).train_events(request(7)))[-1]
        self.assertEqual(resumed["artifactHash"], uninterrupted["artifactHash"])
        self.assertEqual(
            resumed["checkpoint"]["checkpointHash"],
            uninterrupted["checkpoint"]["checkpointHash"],
        )


if __name__ == "__main__":
    unittest.main()
