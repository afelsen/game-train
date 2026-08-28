from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from game_trainer.training_jobs import TrainingJobManager

ROOT = Path(__file__).resolve().parent.parent
COMMAND = (sys.executable, str(ROOT / "scripts" / "run_kuhn_trainer.py"))


def request(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "game": "kuhn-poker",
        "algorithm": "cfr",
        "mode": "visual",
        "iterations": 200,
        "seed": 11,
        "reportEvery": 50,
    }
    value.update(changes)
    return value


class TrainingJobManagerTests(unittest.TestCase):
    def test_visual_job_persists_events_and_checkpoint(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "training.sqlite3"
            manager = TrainingJobManager(COMMAND, database)
            complete = manager.wait(manager.submit(request())["jobId"])
            self.assertEqual(complete["status"], "complete")
            self.assertEqual(
                [event["event"] for event in complete["events"]],
                ["started", "progress", "progress", "progress", "progress", "complete"],
            )
            checkpoint = manager.checkpoint(complete["jobId"])
            self.assertEqual(checkpoint["completedIterations"], 200)
            self.assertEqual(complete["checkpointHash"], checkpoint["checkpointHash"])

            recovered = TrainingJobManager((sys.executable, "-c", "raise SystemExit(9)"), database)
            self.assertEqual(recovered.snapshot(complete["jobId"])["status"], "complete")
            self.assertEqual(recovered.checkpoint(complete["jobId"]), checkpoint)
            recent = recovered.recent()
            self.assertEqual(recent[0]["jobId"], complete["jobId"])
            self.assertEqual(recent[0]["iterations"], 200)
            model = recovered.register_model(complete["jobId"], "Baseline policy")
            self.assertEqual(model["name"], "Baseline policy")
            self.assertEqual(model["iterations"], 200)
            self.assertEqual(model["sourceJobId"], complete["jobId"])
            self.assertEqual(recovered.models(), [model])

            renamed = recovered.register_model(complete["jobId"], "Renamed policy")
            self.assertEqual(renamed["modelId"], model["modelId"])
            self.assertEqual(renamed["name"], "Renamed policy")

    def test_completed_job_can_resume_to_larger_target(self) -> None:
        manager = TrainingJobManager(COMMAND)
        first = manager.wait(manager.submit(request(iterations=100, mode="headless"))["jobId"])
        resumed = manager.wait(
            manager.resume(first["jobId"], iterations=300, mode="headless")["jobId"]
        )
        uninterrupted = manager.wait(
            manager.submit(request(iterations=300, mode="headless"))["jobId"]
        )
        self.assertEqual(resumed["status"], "complete")
        self.assertEqual(
            resumed["events"][-1]["artifactHash"],
            uninterrupted["events"][-1]["artifactHash"],
        )
        with self.assertRaisesRegex(ValueError, "exceed"):
            manager.resume(first["jobId"], iterations=100)

    def test_running_job_can_be_cancelled(self) -> None:
        slow_worker = "import json,time,sys; json.load(sys.stdin); time.sleep(10)"
        manager = TrainingJobManager((sys.executable, "-c", slow_worker))
        submitted = manager.submit(request())
        cancelled = manager.cancel(submitted["jobId"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["error"], "cancelled by user")
        with self.assertRaisesRegex(ValueError, "no checkpoint"):
            manager.checkpoint(cancelled["jobId"])
        with self.assertRaisesRegex(ValueError, "persistent"):
            manager.register_model(cancelled["jobId"])


if __name__ == "__main__":
    unittest.main()
