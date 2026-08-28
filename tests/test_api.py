from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from game_trainer.api import ApiApplication, build_service
from game_trainer.history import HandHistoryRepository

ROOT = Path(__file__).resolve().parent.parent


class ApiApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        history = HandHistoryRepository(Path(self.temporary_directory.name) / "history.sqlite3")
        self.app = ApiApplication(build_service(ROOT, include_fullhouse=True), history=history)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_health_and_provider_discovery(self) -> None:
        self.assertEqual(self.app.handle("GET", "/v1/health").status, 200)
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

    def test_strategy_response_and_illegal_action_error(self) -> None:
        created = self.app.handle("POST", "/v1/hands", {"seed": 52})
        session_id = created.body["sessionId"]
        strategy = self.app.handle("POST", f"/v1/hands/{session_id}/strategy", {})
        self.assertEqual(strategy.status, 200)
        self.assertEqual(strategy.body["status"], "ok")
        bad = self.app.handle("POST", f"/v1/hands/{session_id}/actions", {"type": "check"})
        self.assertEqual(bad.status, 400)

    def test_opponent_provider_can_be_selected(self) -> None:
        created = self.app.handle("POST", "/v1/hands", {"seed": 54, "button": 1, "botProvider": "uniform-random-hu"})
        self.assertEqual(created.status, 201)
        self.assertEqual(created.body["botProvider"], "uniform-random-hu")
        unknown = self.app.handle("POST", "/v1/hands", {"seed": 55, "botProvider": "missing"})
        self.assertEqual(unknown.status, 404)

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


if __name__ == "__main__":
    unittest.main()
