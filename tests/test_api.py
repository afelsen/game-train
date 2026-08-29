from __future__ import annotations

import unittest
import json
import sys
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path

from game_trainer.api import ApiApplication, build_service
from game_trainer.history import HandHistoryRepository
from game_trainer.solver_jobs import SolverJobManager
from game_trainer.training_jobs import TrainingJobManager
from game_trainer.range_estimator_jobs import RangeEstimatorJobManager

ROOT = Path(__file__).resolve().parent.parent


class ApiApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        history = HandHistoryRepository(Path(self.temporary_directory.name) / "history.sqlite3")
        self.app = ApiApplication(build_service(ROOT, include_fullhouse=True), history=history)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_health_and_provider_discovery(self) -> None:
        health = self.app.handle("GET", "/v1/health")
        self.assertEqual(health.status, 200)
        self.assertEqual(health.body["solver"], "unavailable")
        result = self.app.handle("GET", "/v1/providers")
        self.assertEqual(result.status, 200)
        self.assertIn("check-call-hu", {item["id"] for item in result.body["providers"]})

    def test_complete_interactive_hand(self) -> None:
        created = self.app.handle("POST", "/v1/hands", {"seed": 51})
        self.assertEqual(created.status, 201)
        session_id = created.body["sessionId"]
        observation = created.body["observation"]
        steps = 0
        while observation["street"] != "terminal":
            legal = observation["legalActions"]
            action = next(item for item in legal if item["type"] in ("check", "call"))
            result = self.app.handle("POST", f"/v1/hands/{session_id}/actions", {"type": action["type"]})
            self.assertEqual(result.status, 200)
            observation = result.body["observation"]
            steps += 1
            self.assertLess(steps, 10)
        self.assertEqual(observation["result"]["reason"], "showdown")
        self.assertEqual(len(observation["result"]["revealedHoleCards"]), 2)
        self.assertEqual(len(observation["result"]["bestHands"]), 2)

    def test_strategy_response_and_illegal_action_error(self) -> None:
        created = self.app.handle("POST", "/v1/hands", {"seed": 52})
        session_id = created.body["sessionId"]
        strategy = self.app.handle("POST", f"/v1/hands/{session_id}/strategy", {})
        self.assertEqual(strategy.status, 200)
        self.assertEqual(strategy.body["status"], "ok")
        bad = self.app.handle("POST", f"/v1/hands/{session_id}/actions", {"type": "check"})
        self.assertEqual(bad.status, 400)

    def test_opponent_provider_can_be_selected(self) -> None:
        with patch.object(self.app.service, "apply_provider_action", wraps=self.app.service.apply_provider_action) as apply_provider_action:
            created = self.app.handle("POST", "/v1/hands", {"seed": 54, "button": 1, "botProvider": "uniform-random-hu"})
        self.assertEqual(created.status, 201)
        self.assertEqual(created.body["botProvider"], "uniform-random-hu")
        self.assertTrue(apply_provider_action.called)
        self.assertTrue(all(call.args[1] == "uniform-random-hu" for call in apply_provider_action.call_args_list))
        detail = self.app.handle("GET", f"/v1/history/{created.body['sessionId']}")
        self.assertEqual(detail.body["botProvider"], "uniform-random-hu")
        unknown = self.app.handle("POST", "/v1/hands", {"seed": 55, "botProvider": "missing"})
        self.assertEqual(unknown.status, 404)

    def test_opponent_provider_can_change_during_a_hand(self) -> None:
        created = self.app.handle("POST", "/v1/hands", {"seed": 57, "botProvider": "check-call-hu"})
        session_id = created.body["sessionId"]
        changed = self.app.handle(
            "POST",
            f"/v1/hands/{session_id}/bot-provider",
            {"providerId": "uniform-random-hu"},
        )
        self.assertEqual(changed.status, 200)
        self.assertEqual(changed.body["botProvider"], "uniform-random-hu")
        fetched = self.app.handle("GET", f"/v1/hands/{session_id}")
        self.assertEqual(fetched.body["botProvider"], "uniform-random-hu")

        legal = next(
            action
            for action in fetched.body["observation"]["legalActions"]
            if action["type"] in ("check", "call")
        )
        with patch.object(
            self.app.service,
            "apply_provider_action",
            wraps=self.app.service.apply_provider_action,
        ) as apply_provider_action:
            acted = self.app.handle(
                "POST",
                f"/v1/hands/{session_id}/actions",
                {"type": legal["type"]},
            )
        self.assertEqual(acted.status, 200)
        self.assertTrue(apply_provider_action.called)
        self.assertTrue(
            all(
                call.args[1] == "uniform-random-hu"
                for call in apply_provider_action.call_args_list
            )
        )

        missing = self.app.handle(
            "POST",
            f"/v1/hands/{session_id}/bot-provider",
            {"providerId": "missing"},
        )
        self.assertEqual(missing.status, 404)

    def test_new_hand_accepts_continuing_cash_game_stacks(self) -> None:
        created = self.app.handle("POST", "/v1/hands", {"seed": 56, "button": 1, "startingStacks": [12_500, 7_500]})
        self.assertEqual(created.status, 201)
        self.assertEqual(sum(seat["stack"] + seat["handCommitted"] for seat in created.body["observation"]["seats"]), 20_000)
        self.assertEqual(created.body["observation"]["button"], 1)
        invalid = self.app.handle("POST", "/v1/hands", {"startingStacks": [20_000, 0]})
        self.assertEqual(invalid.status, 400)

    def test_custom_raise_and_history_replay(self) -> None:
        created = self.app.handle("POST", "/v1/hands", {"seed": 53})
        session_id = created.body["sessionId"]
        legal_raise = next(item for item in created.body["observation"]["legalActions"] if item["type"] == "raise-to")
        amount = min(legal_raise["maxAmount"], legal_raise["minAmount"] + 100)
        result = self.app.handle("POST", f"/v1/hands/{session_id}/actions", {"type": "raise-to", "amount": amount})
        self.assertEqual(result.status, 200)

        recent = self.app.handle("GET", "/v1/history?limit=10")
        self.assertEqual(recent.status, 200)
        self.assertEqual(recent.body["hands"][0]["sessionId"], session_id)
        detail = self.app.handle("GET", f"/v1/history/{session_id}")
        self.assertGreaterEqual(len(detail.body["events"]), 2)
        self.assertIn("observation", detail.body["events"][0])

    def test_solver_job_routes(self) -> None:
        fixture = json.loads((ROOT / "solver_worker" / "fixtures" / "turn-td9d6h-qc-headless.json").read_text())
        worker = "import json,sys; r=json.load(sys.stdin); print(json.dumps({'schemaVersion':'1.0.0','event':'complete','mode':r['mode']}))"
        app = ApiApplication(
            build_service(ROOT, include_fullhouse=True),
            solver_jobs=SolverJobManager((sys.executable, "-c", worker)),
        )
        submitted = app.handle("POST", "/v1/solver/jobs", fixture)
        self.assertEqual(submitted.status, 202)
        result = app.solver_jobs.wait(submitted.body["jobId"])
        fetched = app.handle("GET", f"/v1/solver/jobs/{result['jobId']}")
        self.assertEqual(fetched.status, 200)
        self.assertEqual(fetched.body["status"], "complete")

        slow_worker = "import json,time,sys; json.load(sys.stdin); time.sleep(10)"
        cancellable = SolverJobManager((sys.executable, "-c", slow_worker))
        cancel_app = ApiApplication(build_service(ROOT), solver_jobs=cancellable)
        queued = cancel_app.handle("POST", "/v1/solver/jobs", fixture)
        cancelled = cancel_app.handle("POST", f"/v1/solver/jobs/{queued.body['jobId']}/cancel")
        self.assertEqual(cancelled.body["status"], "cancelled")

    def test_solver_job_route_explains_unavailable_worker(self) -> None:
        result = self.app.handle("POST", "/v1/solver/jobs", {})
        self.assertEqual(result.status, 400)
        self.assertIn("unavailable", result.body["error"])

    def test_training_spot_routes_are_reproducible(self) -> None:
        curated = self.app.handle("GET", "/v1/training/spots?source=curated")
        self.assertEqual(curated.status, 200)
        self.assertGreaterEqual(len(curated.body["spots"]), 3)

        first = self.app.handle("GET", "/v1/training/spots?source=random&seed=42&count=2")
        second = self.app.handle("GET", "/v1/training/spots?source=random&seed=42&count=2")
        self.assertEqual(first.status, 200)
        self.assertEqual(first.body, second.body)
        self.assertEqual(len(first.body["spots"]), 2)

        invalid = self.app.handle("GET", "/v1/training/spots?source=unknown")
        self.assertEqual(invalid.status, 400)

    def test_model_training_job_checkpoint_and_resume_routes(self) -> None:
        manager = TrainingJobManager(
            (sys.executable, str(ROOT / "scripts" / "run_trainer.py")),
            Path(self.temporary_directory.name) / "training.sqlite3",
        )
        app = ApiApplication(
            build_service(ROOT, include_fullhouse=False), training_jobs=manager
        )
        run_request = {
            "schemaVersion": "1.0.0",
            "game": "kuhn-poker",
            "algorithm": "cfr",
            "mode": "headless",
            "iterations": 100,
            "seed": 5,
            "reportEvery": 25,
        }
        submitted = app.handle("POST", "/v1/training/jobs", run_request)
        self.assertEqual(submitted.status, 202)
        completed = manager.wait(submitted.body["jobId"])
        recent = app.handle("GET", "/v1/training/jobs?limit=5")
        self.assertEqual(recent.status, 200)
        self.assertEqual(recent.body["jobs"][0]["jobId"], completed["jobId"])
        self.assertEqual(recent.body["jobs"][0]["iterations"], 100)
        fetched = app.handle("GET", f"/v1/training/jobs/{completed['jobId']}")
        self.assertEqual(fetched.body["status"], "complete")
        checkpoint = app.handle(
            "GET", f"/v1/training/jobs/{completed['jobId']}/checkpoint"
        )
        self.assertEqual(checkpoint.body["completedIterations"], 100)
        resumed = app.handle(
            "POST",
            f"/v1/training/jobs/{completed['jobId']}/resume",
            {"iterations": 200, "mode": "headless", "reportEvery": 25},
        )
        self.assertEqual(resumed.status, 202)
        self.assertEqual(manager.wait(resumed.body["jobId"])["status"], "complete")
        registered = app.handle(
            "POST",
            f"/v1/training/jobs/{completed['jobId']}/register",
            {"name": "API policy"},
        )
        self.assertEqual(registered.status, 201)
        models = app.handle("GET", "/v1/training/models")
        self.assertEqual(models.status, 200)
        self.assertEqual(models.body["models"][0]["name"], "API policy")
        node = models.body["models"][0]["strategy"][0]
        strategy = app.handle(
            "POST",
            f"/v1/training/models/{registered.body['modelId']}/strategy",
            {"informationSet": node["informationSet"], "legalActions": ["pass", "bet"]},
        )
        self.assertEqual(strategy.status, 200)
        self.assertAlmostEqual(sum(strategy.body["actions"].values()), 1.0)

    def test_range_estimator_training_job_and_eval_routes(self) -> None:
        manager = RangeEstimatorJobManager(Path(self.temporary_directory.name) / "range-estimator.sqlite3")
        app = ApiApplication(build_service(ROOT, include_fullhouse=False), range_estimator_jobs=manager)
        submitted = app.handle("POST", "/v1/range-estimator/jobs", {
            "schemaVersion": "1.0.0", "seed": 19, "hands": 120,
            "epochs": 2, "learningRate": 0.02, "reportEvery": 1, "reportEveryExamples": 100,
        })
        self.assertEqual(submitted.status, 202)
        completed = manager.wait(submitted.body["jobId"])
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["events"][-1]["event"], "complete")
        evaluation = app.handle("GET", f"/v1/range-estimator/jobs/{completed['jobId']}/eval")
        self.assertEqual(evaluation.status, 200)
        self.assertGreater(evaluation.body["testExamples"], 0)
        checkpoint = app.handle("GET", f"/v1/range-estimator/jobs/{completed['jobId']}/checkpoint")
        self.assertEqual(checkpoint.status, 200)
        self.assertIn("weights", checkpoint.body)


if __name__ == "__main__":
    unittest.main()
