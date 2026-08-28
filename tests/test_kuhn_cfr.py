from __future__ import annotations

import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from game_trainer.kuhn_cfr import KuhnCfrTrainer, train_kuhn

ROOT = Path(__file__).resolve().parent.parent


def request(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "game": "kuhn-poker",
        "algorithm": "cfr",
        "mode": "visual",
        "iterations": 200,
        "seed": 7,
        "reportEvery": 50,
    }
    value.update(changes)
    return value


class KuhnCfrTests(unittest.TestCase):
    def test_events_match_versioned_schemas(self) -> None:
        request_schema = json.loads((ROOT / "schemas" / "training-run-request.schema.json").read_text())
        event_schema = json.loads((ROOT / "schemas" / "training-run-event.schema.json").read_text())
        run_request = request()
        Draft202012Validator(request_schema).validate(run_request)
        events = train_kuhn(run_request)
        self.assertEqual(
            [event["event"] for event in events],
            ["started", "progress", "progress", "progress", "progress", "complete"],
        )
        for event in events:
            Draft202012Validator(event_schema).validate(event)

    def test_visual_and_headless_runs_produce_same_artifact(self) -> None:
        visual = train_kuhn(request(iterations=5_000))[-1]
        headless = train_kuhn(request(iterations=5_000, mode="headless", reportEvery=777))[-1]
        self.assertEqual(visual["configHash"], headless["configHash"])
        self.assertEqual(visual["artifactHash"], headless["artifactHash"])
        self.assertEqual(visual["strategy"], headless["strategy"])
        self.assertEqual(visual["gameValue"], headless["gameValue"])

    def test_converges_to_known_kuhn_value_with_low_exploitability(self) -> None:
        complete = train_kuhn(request(iterations=50_000, mode="headless"))[-1]
        self.assertTrue(math.isclose(complete["gameValue"], -1 / 18, abs_tol=0.001))
        self.assertLess(complete["exploitability"], 0.003)
        self.assertEqual(len(complete["strategy"]), 12)
        for information_set in complete["strategy"]:
            self.assertTrue(
                math.isclose(sum(information_set["actions"].values()), 1.0, abs_tol=1e-9)
            )

    def test_worker_emits_json_lines_and_rejects_invalid_game(self) -> None:
        valid = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run_kuhn_trainer.py")],
            input=json.dumps(request(mode="headless", iterations=10)),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(valid.stdout)["event"], "complete")

        invalid = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run_kuhn_trainer.py")],
            input=json.dumps(request(game="holdem")),
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertEqual(json.loads(invalid.stdout)["event"], "failed")

    def test_resumed_run_exactly_matches_uninterrupted_run(self) -> None:
        uninterrupted = train_kuhn(request(iterations=5_000, mode="headless"))[-1]
        first_leg = train_kuhn(request(iterations=2_000, mode="headless"))[-1]
        resumed = train_kuhn(
            request(
                iterations=5_000,
                mode="headless",
                checkpoint=first_leg["checkpoint"],
            )
        )[-1]
        for key in (
            "configHash",
            "artifactHash",
            "iterations",
            "gameValue",
            "exploitability",
            "strategy",
            "checkpoint",
        ):
            self.assertEqual(resumed[key], uninterrupted[key])
        self.assertEqual(resumed["checkpoint"]["completedIterations"], 5_000)

    def test_tampered_or_wrong_seed_checkpoint_is_rejected(self) -> None:
        checkpoint = train_kuhn(request(iterations=10, mode="headless"))[-1]["checkpoint"]
        tampered = json.loads(json.dumps(checkpoint))
        tampered["nodes"]["J:"]["regretSum"][0] += 1
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            train_kuhn(request(iterations=20, mode="headless", checkpoint=tampered))
        with self.assertRaisesRegex(ValueError, "seed"):
            train_kuhn(request(iterations=20, seed=8, mode="headless", checkpoint=checkpoint))

    def test_rejects_unknown_parameters(self) -> None:
        with self.assertRaisesRegex(ValueError, "fields"):
            list(KuhnCfrTrainer().train_events(request(personality="aggressive")))


if __name__ == "__main__":
    unittest.main()
