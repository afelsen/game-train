from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema import Draft202012Validator

from game_trainer.solver_jobs import SolverJobManager

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "solver_worker" / "fixtures" / "turn-td9d6h-qc.json").read_text())
FAKE_WORKER = r"""
import json, sys
request = json.load(sys.stdin)
common = {"schemaVersion": "1.0.0", "configHash": "a" * 64}
if request["mode"] == "visual":
    print(json.dumps({**common, "event": "started", "memoryBytes": 100, "compressedMemoryBytes": 50}), flush=True)
    print(json.dumps({**common, "event": "progress", "iteration": 10, "exploitability": 2.0, "elapsedMs": 1, "actions": []}), flush=True)
print(json.dumps({**common, "event": "complete", "mode": request["mode"], "iterations": 10, "exploitability": 1.0, "elapsedMs": 2, "memoryBytes": 100, "actions": [], "oopEv": 49.0, "ipEv": 51.0}), flush=True)
"""


class SolverJobManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = SolverJobManager((sys.executable, "-c", FAKE_WORKER))

    def test_visual_job_retains_progress_events(self) -> None:
        submitted = self.manager.submit(dict(FIXTURE))
        result = self.manager.wait(submitted["jobId"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual([event["event"] for event in result["events"]], ["started", "progress", "complete"])

    def test_headless_job_only_retains_completion(self) -> None:
        request = dict(FIXTURE, mode="headless")
        submitted = self.manager.submit(request)
        result = self.manager.wait(submitted["jobId"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual([event["event"] for event in result["events"]], ["complete"])

    def test_request_and_event_fixtures_match_schemas(self) -> None:
        request_schema = json.loads((ROOT / "schemas" / "solver-job-request.schema.json").read_text())
        event_schema = json.loads((ROOT / "schemas" / "solver-job-event.schema.json").read_text())
        Draft202012Validator(request_schema).validate(FIXTURE)
        result = self.manager.wait(self.manager.submit(dict(FIXTURE))["jobId"])
        for event in result["events"]:
            Draft202012Validator(event_schema).validate(event)

    def test_invalid_mode_is_rejected_before_process_launch(self) -> None:
        with self.assertRaisesRegex(ValueError, "mode"):
            self.manager.submit(dict(FIXTURE, mode="turbo"))

    def test_completed_result_is_durable_and_reused_across_modes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "solver.sqlite3"
            first_manager = SolverJobManager((sys.executable, "-c", FAKE_WORKER), database)
            first = first_manager.wait(first_manager.submit(dict(FIXTURE))["jobId"])
            self.assertFalse(first["cacheHit"])

            second_manager = SolverJobManager((sys.executable, "-c", "raise SystemExit(9)"), database)
            recovered = second_manager.snapshot(first["jobId"])
            self.assertEqual(recovered["status"], "complete")
            cached = second_manager.submit(dict(FIXTURE, mode="headless", reportEvery=100))
            self.assertEqual(cached["status"], "complete")
            self.assertTrue(cached["cacheHit"])
            self.assertEqual(cached["events"][-1]["mode"], "headless")
            self.assertEqual(cached["cacheKey"], first["cacheKey"])

            bypass_manager = SolverJobManager((sys.executable, "-c", FAKE_WORKER), database)
            bypassed = bypass_manager.wait(
                bypass_manager.submit(dict(FIXTURE, bypassCache=True))["jobId"]
            )
            self.assertEqual(bypassed["status"], "complete")
            self.assertFalse(bypassed["cacheHit"])
            self.assertNotEqual(bypassed["jobId"], first["jobId"])

    def test_running_job_can_be_cancelled(self) -> None:
        slow_worker = "import json,time,sys; json.load(sys.stdin); time.sleep(10)"
        manager = SolverJobManager((sys.executable, "-c", slow_worker))
        submitted = manager.submit(dict(FIXTURE))
        cancelled = manager.cancel(submitted["jobId"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["error"], "cancelled by user")


if __name__ == "__main__":
    unittest.main()
