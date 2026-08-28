#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game_trainer.golden_solver import verify_golden_result
from game_trainer.training_spots import curated_spots

BINARY = Path(
    os.environ.get(
        "GAME_TRAINER_SOLVER_BINARY",
        ROOT / "solver_worker" / "target" / "release" / "game-trainer-solver-worker",
    )
)
GOLDENS = ROOT / "golden" / "solver-results-v1.json"


def solve(request: dict) -> dict:
    completed = subprocess.run(
        (str(BINARY),),
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout.splitlines()[-1])


def main() -> None:
    if not BINARY.is_file():
        raise SystemExit(f"solver worker not found: {BINARY}; run scripts/build_solver_worker.sh")
    golden = json.loads(GOLDENS.read_text())
    expected_by_id = {spot["id"]: spot for spot in golden["spots"]}
    failures: list[str] = []
    checked: list[dict] = []
    for spot in curated_spots():
        request = dict(spot["request"], mode="headless")
        actual = solve(request)
        errors = verify_golden_result(
            request,
            expected_by_id[spot["id"]],
            actual,
            golden["tolerances"],
        )
        checked.append(
            {
                "id": spot["id"],
                "status": "failed" if errors else "ok",
                "exploitability": actual.get("exploitability"),
            }
        )
        failures.extend(f"{spot['id']}: {error}" for error in errors)
    print(
        json.dumps(
            {
                "status": "failed" if failures else "ok",
                "referenceKind": golden["referenceKind"],
                "independentVerified": golden["independentVerified"],
                "checked": checked,
                "errors": failures,
            },
            indent=2,
        )
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
