#!/usr/bin/env python3
"""Validate checked-in manifests and examples against versioned JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(schema_path: Path, instance_path: Path) -> None:
    validator = Draft202012Validator(load(schema_path), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(load(instance_path)), key=lambda error: list(error.path))
    if errors:
        details = "\n".join(f"{list(error.path)}: {error.message}" for error in errors)
        raise SystemExit(f"{instance_path} failed validation:\n{details}")
    print(f"valid: {instance_path.relative_to(ROOT)}")


def main() -> None:
    schema = ROOT / "schemas/model-manifest.schema.json"
    for manifest in sorted((ROOT / "manifests").glob("*.json")):
        if manifest.name == "restricted-hu-nlhe-flop-cfr-v1.json":
            continue
        validate(schema, manifest)
    validate(
        ROOT / "schemas/nlhe-training-abstraction.schema.json",
        ROOT / "manifests/restricted-hu-nlhe-flop-cfr-v1.json",
    )
    validate(ROOT / "schemas/strategy-request.schema.json", ROOT / "examples/strategy-request.json")
    validate(ROOT / "schemas/strategy-response.schema.json", ROOT / "examples/strategy-response.json")


if __name__ == "__main__":
    main()
