#!/usr/bin/env python3
"""Verify locally downloaded artifacts against manifest SHA-256 values."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    checked = 0
    for manifest_path in sorted((ROOT / "manifests").glob("*.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for artifact in manifest["artifacts"]:
            path = ROOT / artifact["path"]
            if not path.exists():
                raise SystemExit(f"missing: {artifact['path']}")
            actual = sha256(path)
            if actual != artifact["sha256"]:
                raise SystemExit(f"checksum mismatch: {artifact['path']}\nexpected {artifact['sha256']}\nactual   {actual}")
            checked += 1
            print(f"verified: {artifact['path']}")
    print(f"verified {checked} artifacts")


if __name__ == "__main__":
    main()

