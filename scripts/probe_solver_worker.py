#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
BINARY = Path(os.environ.get("GAME_TRAINER_SOLVER_BINARY", ROOT / "solver_worker" / "target" / "release" / "game-trainer-solver-worker"))


def run(fixture_name: str) -> list[dict]:
    fixture = (ROOT / "solver_worker" / "fixtures" / fixture_name).read_bytes()
    completed = subprocess.run((str(BINARY),), input=fixture, capture_output=True, check=True)
    events = [json.loads(line) for line in completed.stdout.splitlines()]
    schema = json.loads((ROOT / "schemas" / "solver-job-event.schema.json").read_text())
    for event in events:
        Draft202012Validator(schema).validate(event)
    return events


def comparable(event: dict) -> dict:
    return {key: value for key, value in event.items() if key not in {"elapsedMs", "mode"}}


def main() -> None:
    if not BINARY.is_file():
        raise SystemExit(f"solver worker not found: {BINARY}; run scripts/build_solver_worker.sh")
    visual = run("turn-td9d6h-qc.json")
    headless = run("turn-td9d6h-qc-headless.json")
    assert len(visual) > 1
    assert [event["event"] for event in headless] == ["complete"]
    assert comparable(visual[-1]) == comparable(headless[-1])
    result = visual[-1]
    print(json.dumps({
        "status": "ok",
        "visualEvents": len(visual),
        "headlessEvents": len(headless),
        "configHash": result["configHash"],
        "iterations": result["iterations"],
        "exploitability": result["exploitability"],
        "memoryBytes": result["memoryBytes"],
        "actions": result["actions"],
    }, indent=2))


if __name__ == "__main__":
    main()
