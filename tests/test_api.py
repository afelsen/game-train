from __future__ import annotations

import unittest
from pathlib import Path

from game_trainer.api import ApiApplication, build_service

ROOT = Path(__file__).resolve().parent.parent


class ApiApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = ApiApplication(build_service(ROOT, include_fullhouse=True))

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


if __name__ == "__main__":
    unittest.main()

