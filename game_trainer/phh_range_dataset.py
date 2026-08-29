"""Import a bounded, provenance-preserving PHH hand-history pilot."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from game_trainer.range_estimator_dataset import DATASET_VERSION, SCHEMA_VERSION, validate_request

PHH_DATASET_VERSION = "phh-pokerstars-25nl-pilot-v1"


def load_phh_pilot(path: Path) -> dict[str, Any]:
    """Use only two-card showdowns; all source cards/action text remain auditable."""
    records: list[dict[str, Any]] = []
    for block in path.read_text().split("\n\n"):
        if not block.startswith("["):
            continue
        fields = _fields(block)
        actions = ast.literal_eval(fields["actions"])
        shown = [action for action in actions if " sm " in action and "????" not in action]
        if len(shown) != 2:
            continue
        hero_player, hero_cards = _shown(shown[0])
        villain_player, villain_cards = _shown(shown[1])
        seats = {hero_player: 0, villain_player: 1}
        hand_id = str(fields["hand"])
        for index, board, context_actions in _action_snapshots(actions, seats):
            if len(set(hero_cards + villain_cards + board)) != len(hero_cards + villain_cards + board):
                continue
            context = {
                "schemaVersion": SCHEMA_VERSION,
                "rulesetId": "nlhe-hu-v1",
                "villainSeat": 1,
                "heroCards": hero_cards,
                "board": board,
                "position": "button",
                "potChips": max(1, int(float(fields["min_bet"]) * 100)),
                "effectiveStacks": [10_000, 10_000],
                "actions": context_actions,
                "priorId": "phh-pokerstars-25nl-pilot-v1",
            }
            validate_request(context)
            records.append({
                "schemaVersion": SCHEMA_VERSION,
                "datasetVersion": PHH_DATASET_VERSION,
                "exampleId": f"phh-{hand_id}-{index}",
                "split": _split(hand_id),  # keep all snapshots of a hand together
                "context": context,
                "targetVillainCards": villain_cards,
                "provenance": {"source": "PHH Dataset / PokerStars 25NL July 2009", "handId": hand_id, "multiwaySource": len(ast.literal_eval(fields["players"])) > 2},
            })
    if len(records) < 10:
        raise ValueError("PHH pilot did not contain enough two-card showdowns")
    return {
        "manifest": {
            "schemaVersion": SCHEMA_VERSION,
            "datasetVersion": PHH_DATASET_VERSION,
            "source": "MIT-licensed PHH Dataset; PokerStars 25NL July 2009 pilot",
            "hands": len(records),
            "splits": {split: sum(record["split"] == split for record in records) for split in ("train", "validation", "test")},
            "recordHash": _hash(records),
        },
        "records": records,
    }


def _fields(block: str) -> dict[str, str]:
    return dict(line.split(" = ", 1) for line in block.splitlines()[1:] if " = " in line)


def _shown(action: str) -> tuple[str, list[str]]:
    player, cards = action.split(" sm ", 1)
    return player, [cards[:2], cards[2:]]


def _action_snapshots(actions: list[str], seats: dict[str, int]) -> list[tuple[int, list[str], list[dict[str, Any]]]]:
    board: list[str] = []
    output: list[dict[str, Any]] = []
    snapshots: list[tuple[int, list[str], list[dict[str, Any]]]] = []
    for index, action in enumerate(actions):
        if action.startswith("d db "):
            cards = action.removeprefix("d db ")
            board.extend([cards[position:position + 2] for position in range(0, len(cards), 2)])
            continue
        parts = action.split()
        if not parts or parts[0] not in seats or len(parts) < 2 or parts[1] == "sm":
            continue
        code = parts[1]
        action_type = "raise-to" if code == "cbr" else "fold" if code == "f" else "call" if code == "cc" else None
        if action_type:
            output.append({"seat": seats[parts[0]], "street": "unknown", "type": action_type, "amount": 0})
            if seats[parts[0]] == 1:
                snapshots.append((index, list(board), list(output)))
    return snapshots


def _split(hand_id: str) -> str:
    bucket = int(_hash(hand_id)[:8], 16) % 100
    return "train" if bucket < 80 else "validation" if bucket < 90 else "test"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
