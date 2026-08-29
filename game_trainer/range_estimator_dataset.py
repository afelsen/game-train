"""Versioned inputs and deterministic synthetic data for range-estimator/v1."""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from typing import Any

import eval7

from game_trainer.poker.cards import FULL_DECK, validate_card
from game_trainer.range_estimator import _preflop_strength

SCHEMA_VERSION = "1.0.0"
RULESET_ID = "nlhe-hu-v1"
DATASET_VERSION = "synthetic-range-estimator-v1"


def legal_villain_combos(hero_cards: list[str], board: list[str]) -> list[tuple[str, str]]:
    """Enumerate every blocker-valid Villain combo in canonical deck order."""
    _validate_cards(hero_cards, board)
    known = set(hero_cards + board)
    return list(itertools.combinations((card for card in FULL_DECK if card not in known), 2))


def validate_request(request: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on invalid public range-estimator requests."""
    required = {
        "schemaVersion", "rulesetId", "villainSeat", "heroCards", "board",
        "position", "potChips", "effectiveStacks", "actions", "priorId",
    }
    if set(request) != required:
        raise ValueError("range estimator request fields do not match range-estimator/v1")
    if request["schemaVersion"] != SCHEMA_VERSION or request["rulesetId"] != RULESET_ID:
        raise ValueError("range estimator request contract is incompatible")
    if request["villainSeat"] != 1 or request["position"] not in ("button", "big-blind"):
        raise ValueError("range estimator request has an unsupported seat or position")
    hero_cards, board = request["heroCards"], request["board"]
    if not isinstance(hero_cards, list) or not isinstance(board, list):
        raise ValueError("heroCards and board must be lists")
    _validate_cards(hero_cards, board)
    if type(request["potChips"]) is not int or request["potChips"] <= 0:
        raise ValueError("potChips must be a positive integer")
    stacks = request["effectiveStacks"]
    if (
        not isinstance(stacks, list)
        or len(stacks) != 2
        or any(type(stack) is not int or stack < 0 for stack in stacks)
    ):
        raise ValueError("effectiveStacks must contain two non-negative integers")
    if not isinstance(request["actions"], list) or any(not isinstance(action, dict) for action in request["actions"]):
        raise ValueError("actions must be a list of action objects")
    if not isinstance(request["priorId"], str) or not request["priorId"].strip():
        raise ValueError("priorId must be a non-empty string")
    return request


def generate_synthetic_dataset(seed: int, hands: int) -> dict[str, Any]:
    """Generate replayable labeled examples without leaking labels into context."""
    if type(seed) is not int or type(hands) is not int or not 1 <= hands <= 100_000:
        raise ValueError("seed must be an integer and hands must be 1 through 100000")
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    for index in range(hands):
        dealt = rng.sample(FULL_DECK, 9)
        hero_cards, villain_cards, board = dealt[:2], dealt[2:4], dealt[4:]
        street = rng.choice((0, 3, 4))
        visible_board = board[:street]
        context = _context_for_hand(rng, hero_cards, villain_cards, visible_board, index)
        label = list(villain_cards)
        record = {
            "schemaVersion": SCHEMA_VERSION,
            "datasetVersion": DATASET_VERSION,
            "exampleId": _hash({"seed": seed, "index": index})[:20],
            "split": _split(seed, index),
            "context": context,
            "targetVillainCards": label,
        }
        records.append(record)
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "datasetVersion": DATASET_VERSION,
        "seed": seed,
        "hands": hands,
        "splits": {split: sum(record["split"] == split for record in records) for split in ("train", "validation", "test")},
        "recordHash": _hash(records),
        "source": "deterministic-synthetic-hu-v1",
    }
    return {"manifest": manifest, "records": records}


def _context_for_hand(
    rng: random.Random,
    hero_cards: list[str],
    villain_cards: list[str],
    board: list[str],
    index: int,
) -> dict[str, Any]:
    position = "button" if index % 2 == 0 else "big-blind"
    pot = 150 if not board else 600 + 100 * len(board)
    stacks = [10_000 - pot // 2, 10_000 - pot // 2]
    strength = _villain_strength(villain_cards, board)
    hero_action = {"seat": 0, "street": _street_name(board), "type": "raise-to", "amount": pot}
    villain_type = "raise-to" if strength > 0.72 else "call" if strength > 0.35 else "fold"
    if board and strength < 0.3:
        villain_type = "check"
    villain_action = {
        "seat": 1,
        "street": _street_name(board),
        "type": villain_type,
        "amount": pot * (2 if villain_type == "raise-to" else 1),
    }
    request = {
        "schemaVersion": SCHEMA_VERSION,
        "rulesetId": RULESET_ID,
        "villainSeat": 1,
        "heroCards": list(hero_cards),
        "board": list(board),
        "position": position,
        "potChips": pot,
        "effectiveStacks": stacks,
        "actions": [hero_action, villain_action],
        "priorId": "uniform-legal-combos-v1",
    }
    validate_request(request)
    return request


def _villain_strength(cards: list[str], board: list[str]) -> float:
    if not board:
        return _preflop_strength((cards[0], cards[1]))
    score = eval7.evaluate([eval7.Card(card) for card in cards + board])
    return min(1.0, score / 135004160.0)


def _street_name(board: list[str]) -> str:
    return {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)]


def _validate_cards(hero_cards: list[str], board: list[str]) -> None:
    if len(hero_cards) != 2 or len(board) > 5:
        raise ValueError("range estimator requires two Hero cards and at most five board cards")
    if any(not isinstance(card, str) for card in hero_cards + board):
        raise ValueError("cards must be strings")
    for card in hero_cards + board:
        validate_card(card)
    if len(set(hero_cards + board)) != len(hero_cards) + len(board):
        raise ValueError("range estimator cards must be unique")


def _split(seed: int, index: int) -> str:
    bucket = int(_hash({"seed": seed, "index": index})[:8], 16) % 100
    return "train" if bucket < 80 else "validation" if bucket < 90 else "test"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
