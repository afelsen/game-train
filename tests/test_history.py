from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from game_trainer.history import HandHistoryRepository
from game_trainer.poker import HandState


class HandHistoryRepositoryTests(unittest.TestCase):
    def test_round_trip_and_query_indexes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "history.sqlite3"
            repository = HandHistoryRepository(database)
            hand = HandState(seed=901)
            repository.create_hand("hand-test", hand.to_dict())
            repository.append_event("hand-test", hand.observation(0))
            repository.update_hand("hand-test", hand.to_dict())

            self.assertEqual(repository.recent()[0]["sessionId"], "hand-test")
            self.assertEqual(repository.detail("hand-test")["events"][0]["sequence"], 0)

            with sqlite3.connect(database) as connection:
                history_plan = connection.execute(
                    "EXPLAIN QUERY PLAN SELECT session_id FROM hands ORDER BY started_at DESC LIMIT 20"
                ).fetchall()
                events_plan = connection.execute(
                    "EXPLAIN QUERY PLAN SELECT sequence FROM hand_events WHERE session_id = ? ORDER BY sequence",
                    ("hand-test",),
                ).fetchall()
            self.assertIn("idx_hands_started_at", " ".join(str(row) for row in history_plan))
            self.assertIn("idx_hand_events_session_sequence", " ".join(str(row) for row in events_plan))


if __name__ == "__main__":
    unittest.main()
