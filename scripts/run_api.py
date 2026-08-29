#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game_trainer.api import ApiApplication, build_service, encode_json
from game_trainer.history import HandHistoryRepository
from game_trainer.solver_jobs import SolverJobManager
from game_trainer.training_jobs import TrainingJobManager
from game_trainer.range_estimator_jobs import RangeEstimatorJobManager

DATABASE_PATH = Path(os.environ.get("GAME_TRAINER_DB_PATH", ROOT / "data" / "game-trainer.sqlite3"))
SOLVER_BINARY = Path(os.environ.get("GAME_TRAINER_SOLVER_BINARY", ROOT / "solver_worker" / "target" / "release" / "game-trainer-solver-worker"))
SOLVER_DATABASE_PATH = Path(os.environ.get("GAME_TRAINER_SOLVER_DB_PATH", ROOT / "data" / "solver-jobs.sqlite3"))
SOLVER_JOBS = SolverJobManager.from_binary(SOLVER_BINARY, SOLVER_DATABASE_PATH) if SOLVER_BINARY.is_file() else None
TRAINING_DATABASE_PATH = Path(os.environ.get("GAME_TRAINER_TRAINING_DB_PATH", ROOT / "data" / "training-jobs.sqlite3"))
TRAINING_JOBS = TrainingJobManager(
    (sys.executable, str(ROOT / "scripts" / "run_trainer.py")),
    TRAINING_DATABASE_PATH,
)
RANGE_ESTIMATOR_DATABASE_PATH = Path(os.environ.get("GAME_TRAINER_RANGE_ESTIMATOR_DB_PATH", ROOT / "data" / "range-estimator-jobs.sqlite3"))
RANGE_ESTIMATOR_JOBS = RangeEstimatorJobManager(RANGE_ESTIMATOR_DATABASE_PATH)
APP = ApiApplication(
    build_service(ROOT),
    history=HandHistoryRepository(DATABASE_PATH),
    solver_jobs=SOLVER_JOBS,
    training_jobs=TRAINING_JOBS,
    range_estimator_jobs=RANGE_ESTIMATOR_JOBS,
)


class Handler(BaseHTTPRequestHandler):
    def _send(self, result) -> None:
        payload = encode_json(result)
        self.send_response(result.status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("request body too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        self._send(APP.handle("GET", self.path))

    def do_POST(self) -> None:
        try:
            result = APP.handle("POST", self.path, self._body())
        except (json.JSONDecodeError, ValueError) as error:
            from game_trainer.api import ApiResult
            result = ApiResult(400, {"error": str(error)})
        self._send(result)

    def log_message(self, format: str, *args) -> None:
        print(f"api: {format % args}")


if __name__ == "__main__":
    host = os.environ.get("GAME_TRAINER_API_HOST", "127.0.0.1")
    port = int(os.environ.get("GAME_TRAINER_API_PORT", "8000"))
    print(f"game train API: http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
