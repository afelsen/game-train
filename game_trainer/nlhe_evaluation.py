"""Acceptance-gate metrics for restricted hold'em policy artifacts."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from game_trainer.nlhe_mccfr import RestrictedNlheMccfrTrainer
from game_trainer.nlhe_abstraction import encode_information_set
from game_trainer.nlhe_training_env import expand_range, manifest_ranges

ROOT = Path(__file__).resolve().parent.parent


def heldout_information_sets(seed: int = 0xC0FFEE, count: int = 50) -> tuple[str, ...]:
    """Select stable, unique OOP root information sets for oracle evaluation."""
    if type(seed) is not int or type(count) is not int or count < 1:
        raise ValueError("seed must be an integer and count must be positive")
    oop_range, _ = manifest_ranges()
    hands = expand_range(oop_range, ("Td", "9d", "6h"))
    indices = list(range(len(hands)))
    random.Random(seed).shuffle(indices)
    result: list[str] = []
    seen: set[str] = set()
    for index in indices:
        key = str(_root_information_set(hands[index])["informationSetId"])
        if key not in seen:
            result.append(key)
            seen.add(key)
        if len(result) == count:
            return tuple(result)
    raise ValueError("not enough unique held-out information sets")


def reference_from_solver_output(
    output: dict[str, Any], *, seed: int = 0xC0FFEE, count: int = 50, chips_per_bb: float = 4.0
) -> dict[str, Any]:
    """Convert a compatible flop worker result into a gate reference artifact."""
    if output.get("event") != "complete" or not isinstance(output.get("handDetails"), list):
        raise ValueError("solver output must be a complete event with handDetails")
    if chips_per_bb <= 0:
        raise ValueError("chipsPerBb must be positive")
    required = set(heldout_information_sets(seed, count))
    grouped: dict[str, dict[str, Any]] = {}
    for detail in output["handDetails"]:
        hand = detail.get("hand")
        if not isinstance(hand, str) or len(hand) != 4:
            raise ValueError("solver hand details contain an invalid hand")
        encoded = _root_information_set((hand[:2], hand[2:]))
        key = str(encoded["informationSetId"])
        if key not in required:
            continue
        weight = float(detail["weight"])
        actions = {action: float(value) for action, value in detail["actions"].items()}
        values = {action: float(value) / chips_per_bb for action, value in detail["actionValues"].items()}
        group = grouped.setdefault(
            key,
            {
                "informationSet": key,
                "weight": 0.0,
                "actions": {action: 0.0 for action in actions},
                "actionValuesBb": {action: 0.0 for action in values},
            },
        )
        if set(group["actions"]) != set(actions) or set(group["actionValuesBb"]) != set(values):
            raise ValueError("suit-isomorphic solver hands have incompatible actions")
        group["weight"] += weight
        for action in actions:
            group["actions"][action] += weight * actions[action]
            group["actionValuesBb"][action] += weight * values[action]
    spots = list(grouped.values())
    for spot in spots:
        weight = spot["weight"]
        if weight <= 0:
            raise ValueError("held-out solver hand has no reach weight")
        spot["actions"] = {action: value / weight for action, value in spot["actions"].items()}
        spot["actionValuesBb"] = {
            action: value / weight for action, value in spot["actionValuesBb"].items()
        }
    if len(spots) != count:
        raise ValueError(f"solver output covers {len(spots)} of {count} held-out information sets")
    spots.sort(key=lambda spot: spot["informationSet"])
    content = {
        "schemaVersion": "1.0.0",
        "id": "",
        "abstractionId": "restricted-hu-nlhe-flop-cfr-v1",
        "solverConfigHash": output.get("configHash"),
        "solverExploitability": output.get("exploitability"),
        "heldoutSeed": seed,
        "chipsPerBb": chips_per_bb,
        "spots": spots,
    }
    content["id"] = f"restricted-hunl-oracle-{_hash({key: value for key, value in content.items() if key != 'id'})[:12]}"
    return content


def policy_from_checkpoint(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate a checkpoint against the live contract and return its average policy."""
    trainer = RestrictedNlheMccfrTrainer(seed=checkpoint.get("seed"))
    trainer.load_checkpoint(checkpoint)
    return trainer.artifact()


def evaluate_policy(
    candidate: list[dict[str, Any]],
    reference: dict[str, Any],
    *,
    duplicate_artifact_hash: str | None = None,
) -> dict[str, Any]:
    """Compare a policy with a per-information-set solver reference."""
    _validate_reference(reference)
    manifest = json.loads((ROOT / "manifests/restricted-hu-nlhe-flop-cfr-v1.json").read_text())
    acceptance = manifest["evaluation"]["acceptance"]
    required_count = manifest["evaluation"]["heldOutInformationSets"]
    candidate_index = {item["informationSet"]: item for item in candidate}
    candidate_hash = _hash(candidate)

    l1_weighted = 0.0
    ev_loss_weighted = 0.0
    total_weight = 0.0
    covered = 0
    missing: list[str] = []
    rows: list[dict[str, Any]] = []
    for spot in reference["spots"]:
        key = spot["informationSet"]
        candidate_node = candidate_index.get(key)
        if candidate_node is None:
            missing.append(key)
            continue
        reference_actions = spot["actions"]
        candidate_actions = candidate_node["actions"]
        if set(candidate_actions) != set(reference_actions):
            missing.append(key)
            continue
        weight = float(spot["weight"])
        l1 = sum(abs(float(candidate_actions[action]) - float(reference_actions[action])) for action in reference_actions)
        values = spot["actionValuesBb"]
        reference_ev = sum(float(reference_actions[action]) * float(values[action]) for action in values)
        candidate_ev = sum(float(candidate_actions[action]) * float(values[action]) for action in values)
        ev_loss = max(0.0, reference_ev - candidate_ev)
        l1_weighted += weight * l1
        ev_loss_weighted += weight * ev_loss
        total_weight += weight
        covered += 1
        rows.append({"informationSet": key, "actionL1": l1, "evLossBb": ev_loss, "weight": weight})

    mean_l1 = l1_weighted / total_weight if total_weight else None
    weighted_ev_loss = ev_loss_weighted / total_weight if total_weight else None
    deterministic = duplicate_artifact_hash == candidate_hash if duplicate_artifact_hash is not None else False
    complete = covered >= required_count and not missing and mean_l1 is not None and weighted_ev_loss is not None
    passed = bool(
        complete
        and mean_l1 <= acceptance["meanActionL1Max"]
        and weighted_ev_loss <= acceptance["weightedEvLossBbMax"]
        and (deterministic or not acceptance["deterministicArtifactRequired"])
    )
    result = {
        "schemaVersion": "1.0.0",
        "abstractionId": manifest["id"],
        "referenceId": reference["id"],
        "candidateArtifactHash": candidate_hash,
        "status": "pass" if passed else "rejected" if complete else "incomplete",
        "coverage": {"required": required_count, "covered": covered, "missing": missing},
        "metrics": {
            "meanActionL1": mean_l1,
            "weightedEvLossBb": weighted_ev_loss,
            "duplicateSeedArtifactMatch": deterministic,
        },
        "thresholds": acceptance,
        "spots": rows,
    }
    result["evaluationHash"] = _hash(result)
    return result


def _validate_reference(reference: dict[str, Any]) -> None:
    if not isinstance(reference, dict) or reference.get("schemaVersion") != "1.0.0":
        raise ValueError("unsupported solver reference")
    if reference.get("abstractionId") != "restricted-hu-nlhe-flop-cfr-v1":
        raise ValueError("solver reference abstraction mismatch")
    spots = reference.get("spots")
    if not isinstance(spots, list) or len({spot.get("informationSet") for spot in spots}) != len(spots):
        raise ValueError("solver reference spots must have unique information sets")
    for spot in spots:
        if set(spot) != {"informationSet", "weight", "actions", "actionValuesBb"}:
            raise ValueError("solver reference spot fields are invalid")
        actions, values = spot["actions"], spot["actionValuesBb"]
        if not isinstance(actions, dict) or set(actions) != set(values) or not actions:
            raise ValueError("reference actions and values must have matching keys")
        if float(spot["weight"]) <= 0 or abs(sum(float(value) for value in actions.values()) - 1.0) > 1e-6:
            raise ValueError("reference weight and action probabilities are invalid")


def _root_information_set(hole_cards: tuple[str, str]) -> dict[str, Any]:
    return encode_information_set(
        {
            "street": "flop",
            "actor": 0,
            "position": "oop",
            "holeCards": list(hole_cards),
            "board": ["Td", "9d", "6h"],
            "potBb": 5.5,
            "effectiveStackBb": 97.25,
            "toCallBb": 0,
            "history": [],
        }
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
