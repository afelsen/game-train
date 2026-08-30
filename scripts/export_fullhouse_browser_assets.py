#!/usr/bin/env python3
"""Export the vendored Fullhouse NumPy checkpoint for browser inference."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor/fullhouse-bot"
OUTPUT = ROOT / "web/public/models/fullhouse-v17.json"
LICENSE_OUTPUT = ROOT / "web/public/models/fullhouse-LICENSE.txt"
MODEL_ID = "fullhouse-deep-cfr-experimental-hu"
EXPECTED_MODEL_SHA256 = "1102326b68da95564de147106612df71cb891b42f0726ba0212d3b9a5bcae295"


def encoded(array: np.ndarray) -> dict[str, object]:
    value = np.asarray(array, dtype="<f4", order="C")
    return {
        "shape": list(value.shape),
        "data": base64.b64encode(value.tobytes()).decode("ascii"),
    }


def main() -> None:
    model_path = SOURCE / "data/deep_cfr_model.npz"
    equity_path = SOURCE / "data/preflop_equity.npz"
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if digest != EXPECTED_MODEL_SHA256:
        raise SystemExit(
            f"unexpected Fullhouse checkpoint hash {digest}; audit before exporting"
        )

    with np.load(model_path) as model, np.load(equity_path) as equity:
        artifact = {
            "schemaVersion": "game-train-fullhouse/v1",
            "modelId": MODEL_ID,
            "modelVersion": "e504793",
            "sourceSha256": digest,
            "license": "MIT; see fullhouse-LICENSE.txt",
            "arrays": {name: encoded(model[name]) for name in model.files},
            "equity": {name: encoded(equity[name]) for name in equity.files},
        }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, separators=(",", ":")) + "\n")
    LICENSE_OUTPUT.write_text((SOURCE / "LICENSE").read_text())
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
