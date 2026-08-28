from __future__ import annotations

import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run_probe(name: str) -> dict:
    process = subprocess.run(
        [PYTHON, str(ROOT / "scripts" / name)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(process.stdout)


class PhaseZeroTests(unittest.TestCase):
    def test_fullhouse_strategy_is_repeatable_and_normalized(self) -> None:
        first = run_probe("probe_fullhouse.py")
        second = run_probe("probe_fullhouse.py")
        self.assertEqual(first["strategy"], second["strategy"])
        self.assertTrue(math.isclose(sum(first["strategy"].values()), 1.0, abs_tol=1e-6))
        self.assertTrue(all(math.isfinite(value) and value >= 0 for value in first["strategy"].values()))

    def test_rlcard_seeded_match_is_repeatable_and_zero_sum(self) -> None:
        first = run_probe("probe_rlcard.py")
        second = run_probe("probe_rlcard.py")
        self.assertEqual(first["payoffs"], second["payoffs"])
        self.assertEqual(first["decisionCount"], second["decisionCount"])
        self.assertEqual(sum(first["payoffs"]), 0)
        self.assertTrue(first["terminal"])


if __name__ == "__main__":
    unittest.main()

