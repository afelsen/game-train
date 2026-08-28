#!/usr/bin/env python3
"""Convert an extended solver-worker result into a restricted-NLHE oracle reference."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game_trainer.nlhe_evaluation import reference_from_solver_output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("solver_output", type=Path)
    parser.add_argument("--chips-per-bb", type=float, default=4.0)
    args = parser.parse_args()
    output = json.loads(args.solver_output.read_text())
    print(json.dumps(reference_from_solver_output(output, chips_per_bb=args.chips_per_bb), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
