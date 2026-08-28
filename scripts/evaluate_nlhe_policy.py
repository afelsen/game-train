#!/usr/bin/env python3
"""Evaluate a restricted hold'em checkpoint against a compatible solver reference."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game_trainer.nlhe_evaluation import evaluate_policy, policy_from_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--duplicate-artifact-hash")
    args = parser.parse_args()
    checkpoint = json.loads(args.checkpoint.read_text())
    reference = json.loads(args.reference.read_text())
    result = evaluate_policy(
        policy_from_checkpoint(checkpoint),
        reference,
        duplicate_artifact_hash=args.duplicate_artifact_hash,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "pass" else 2)


if __name__ == "__main__":
    main()
