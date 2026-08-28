from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
