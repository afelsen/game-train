from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class HandHistoryRepository:
    """Small SQLite event store for local hand review."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS hands (
                    session_id TEXT PRIMARY KEY,
                    seed INTEGER NOT NULL,
                    button INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    result_json TEXT,
                    state_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS hand_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES hands(session_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    actor_seat INTEGER,
                    action_json TEXT,
                    observation_json TEXT NOT NULL,
                    strategy_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_hands_started_at
                    ON hands(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_hand_events_session_sequence
                    ON hand_events(session_id, sequence);
                """
            )
            connection.execute("PRAGMA optimize")

    def create_hand(self, session_id: str, state: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO hands
                   (session_id, seed, button, status, started_at, state_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, state["seed"], state["button"], state["street"], _now(), json.dumps(state)),
            )

    def append_event(
        self,
        session_id: str,
        observation: dict[str, Any],
        *,
        actor_seat: int | None = None,
        action: dict[str, Any] | None = None,
        strategy: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM hand_events WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO hand_events
                   (session_id, sequence, actor_seat, action_json, observation_json, strategy_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    sequence,
                    actor_seat,
                    json.dumps(action) if action is not None else None,
                    json.dumps(observation),
                    json.dumps(strategy) if strategy is not None else None,
                    _now(),
                ),
            )

    def update_hand(self, session_id: str, state: dict[str, Any]) -> None:
        terminal = state["street"] == "terminal"
        with self._connect() as connection:
            connection.execute(
                """UPDATE hands SET status = ?, completed_at = ?, result_json = ?, state_json = ?
                   WHERE session_id = ?""",
                (
                    state["street"],
                    _now() if terminal else None,
                    json.dumps(state.get("result")) if terminal else None,
                    json.dumps(state),
                    session_id,
                ),
            )

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT session_id, seed, button, status, started_at, completed_at, result_json, state_json
                   FROM hands ORDER BY started_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "sessionId": row["session_id"],
                "seed": row["seed"],
                "button": row["button"],
                "status": row["status"],
                "startedAt": row["started_at"],
                "completedAt": row["completed_at"],
                "result": json.loads(row["result_json"]) if row["result_json"] else None,
                "botProvider": json.loads(row["state_json"]).get("botProvider"),
            }
            for row in rows
        ]

    def detail(self, session_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            hand = connection.execute("SELECT * FROM hands WHERE session_id = ?", (session_id,)).fetchone()
            if hand is None:
                raise KeyError(f"unknown history hand: {session_id}")
            events = connection.execute(
                """SELECT sequence, actor_seat, action_json, observation_json, strategy_json, created_at
                   FROM hand_events WHERE session_id = ? ORDER BY sequence""",
                (session_id,),
            ).fetchall()
        state = json.loads(hand["state_json"])
        return {
            "sessionId": hand["session_id"],
            "seed": hand["seed"],
            "button": hand["button"],
            "status": hand["status"],
            "startedAt": hand["started_at"],
            "completedAt": hand["completed_at"],
            "result": json.loads(hand["result_json"]) if hand["result_json"] else None,
            "botProvider": state.get("botProvider"),
            "events": [
                {
                    "sequence": row["sequence"],
                    "actorSeat": row["actor_seat"],
                    "action": json.loads(row["action_json"]) if row["action_json"] else None,
                    "observation": json.loads(row["observation_json"]),
                    "strategy": json.loads(row["strategy_json"]) if row["strategy_json"] else None,
                    "createdAt": row["created_at"],
                }
                for row in events
            ],
        }
