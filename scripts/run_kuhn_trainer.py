#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game_trainer.kuhn_cfr import KuhnCfrTrainer


def main() -> None:
    try:
        request = json.load(sys.stdin)
        for event in KuhnCfrTrainer(seed=request.get("seed", 0)).train_events(request):
            print(json.dumps(event, separators=(",", ":")), flush=True)
    except (ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"schemaVersion": "1.0.0", "event": "failed", "error": str(error)},
                separators=(",", ":"),
            ),
            flush=True,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
