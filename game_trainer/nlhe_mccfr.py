"""External-sampling MCCFR for the restricted heads-up NLHE abstraction."""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from game_trainer.kuhn_cfr import _content_hash
from game_trainer.nlhe_abstraction import ABSTRACTION_ID, ACTION_VERSION, ENCODER_VERSION
from game_trainer.nlhe_training_env import RestrictedNlheState, compatible_private_deals, manifest_ranges

ROOT = Path(__file__).resolve().parent.parent
GAME = "restricted-hu-nlhe-flop"
ALGORITHM = "external-sampling-mccfr"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Any) -> str:
    return _sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _contract_hashes(policy: dict[str, Any]) -> dict[str, str]:
    manifest_path = ROOT / "manifests/restricted-hu-nlhe-flop-cfr-v1.json"
    trainer_path = Path(__file__)
    return {
        "manifest": _sha256_bytes(manifest_path.read_bytes()),
        "ranges": _canonical_hash(manifest_ranges()),
        "trainer": _sha256_bytes(trainer_path.read_bytes()),
        "policy": _canonical_hash(policy),
    }


@dataclass
class MccfrNode:
    actions: tuple[str, ...]
    canonical_json: str
    regret_sum: list[float] = field(default_factory=list)
    strategy_sum: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.regret_sum:
            self.regret_sum = [0.0] * len(self.actions)
        if not self.strategy_sum:
            self.strategy_sum = [0.0] * len(self.actions)
        if len(self.regret_sum) != len(self.actions) or len(self.strategy_sum) != len(self.actions):
            raise ValueError("node action and accumulator lengths differ")

    def strategy(self) -> tuple[float, ...]:
        positive = [max(value, 0.0) for value in self.regret_sum]
        total = sum(positive)
        if total <= 0:
            return tuple(1.0 / len(self.actions) for _ in self.actions)
        return tuple(value / total for value in positive)

    def average_strategy(self) -> tuple[float, ...]:
        total = sum(self.strategy_sum)
        if total <= 0:
            return tuple(1.0 / len(self.actions) for _ in self.actions)
        return tuple(value / total for value in self.strategy_sum)


class RestrictedNlheMccfrTrainer:
    """Seed-reproducible alternating external-sampling MCCFR trainer."""

    def __init__(self, seed: int = 0) -> None:
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        self.seed = seed
        self.completed_iterations = 0
        self.nodes: dict[str, MccfrNode] = {}
        self.deals = compatible_private_deals(("Td", "9d", "6h"))

    @staticmethod
    def _sample_index(probabilities: tuple[float, ...], rng: random.Random) -> int:
        target = rng.random()
        cumulative = 0.0
        for index, probability in enumerate(probabilities):
            cumulative += probability
            if target < cumulative:
                return index
        return len(probabilities) - 1

    def _node(self, state: RestrictedNlheState) -> tuple[str, MccfrNode]:
        encoded = state.information_set()
        key = str(encoded["informationSetId"])
        actions = state.legal_actions()
        node = self.nodes.get(key)
        if node is None:
            node = MccfrNode(actions=actions, canonical_json=str(encoded["canonicalJson"]))
            self.nodes[key] = node
        elif node.actions != actions or node.canonical_json != encoded["canonicalJson"]:
            raise ValueError("information-set collision or incompatible action set")
        return key, node

    def _traverse(self, state: RestrictedNlheState, traverser: int, rng: random.Random) -> float:
        if state.terminal:
            assert state.terminal_utility_oop_q is not None
            utility_oop_bb = state.terminal_utility_oop_q / 4
            return utility_oop_bb if traverser == 0 else -utility_oop_bb
        if state.awaiting_chance:
            outcomes = state.chance_outcomes()
            card = outcomes[rng.randrange(len(outcomes))][0]
            return self._traverse(state.deal(card), traverser, rng)

        assert state.actor is not None
        _, node = self._node(state)
        strategy = node.strategy()
        if state.actor == traverser:
            action_utilities = [
                self._traverse(state.apply(action), traverser, rng)
                for action in node.actions
            ]
            node_utility = sum(probability * utility for probability, utility in zip(strategy, action_utilities))
            for index, utility in enumerate(action_utilities):
                node.regret_sum[index] += utility - node_utility
            return node_utility

        for index, probability in enumerate(strategy):
            node.strategy_sum[index] += probability
        chosen = self._sample_index(strategy, rng)
        return self._traverse(state.apply(node.actions[chosen]), traverser, rng)

    def run_iteration(self, iteration: int) -> None:
        if iteration != self.completed_iterations + 1:
            raise ValueError("iterations must run consecutively")
        for traverser in (0, 1):
            rng = random.Random((self.seed << 40) ^ (iteration << 1) ^ traverser)
            deal = self.deals[rng.randrange(len(self.deals))]
            state = RestrictedNlheState(
                board=("Td", "9d", "6h"),
                hole_cards=deal,
            )
            self._traverse(state, traverser, rng)
        self.completed_iterations = iteration

    def artifact(self) -> list[dict[str, Any]]:
        return [
            {
                "informationSet": key,
                "canonicalState": json.loads(node.canonical_json),
                "actions": {
                    action: probability
                    for action, probability in zip(node.actions, node.average_strategy())
                },
            }
            for key, node in sorted(self.nodes.items())
        ]

    def checkpoint(self) -> dict[str, Any]:
        policy = {
            key: {
                "actions": list(node.actions),
                "canonicalJson": node.canonical_json,
                "regretSum": list(node.regret_sum),
                "strategySum": list(node.strategy_sum),
            }
            for key, node in sorted(self.nodes.items())
        }
        content: dict[str, Any] = {
            "schemaVersion": "1.0.0",
            "game": GAME,
            "algorithm": ALGORITHM,
            "seed": self.seed,
            "completedIterations": self.completed_iterations,
            "abstractionId": ABSTRACTION_ID,
            "encoderVersion": ENCODER_VERSION,
            "actionVersion": ACTION_VERSION,
            "requiredHashes": _contract_hashes(policy),
            "nodes": policy,
        }
        content["checkpointHash"] = _content_hash(content)
        return content

    def load_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        _validate_checkpoint(checkpoint)
        if checkpoint["seed"] != self.seed:
            raise ValueError("checkpoint seed does not match training request")
        self.completed_iterations = checkpoint["completedIterations"]
        self.nodes = {
            key: MccfrNode(
                actions=tuple(value["actions"]),
                canonical_json=value["canonicalJson"],
                regret_sum=[float(item) for item in value["regretSum"]],
                strategy_sum=[float(item) for item in value["strategySum"]],
            )
            for key, value in checkpoint["nodes"].items()
        }

    def train_events(self, request: dict[str, Any]) -> Iterator[dict[str, Any]]:
        _validate_request(request)
        if request.get("checkpoint") is not None:
            self.load_checkpoint(request["checkpoint"])
        iterations = request["iterations"]
        if self.completed_iterations > iterations:
            raise ValueError("checkpoint is beyond requested iterations")
        canonical_request = {
            key: value
            for key, value in dict(request, mode="headless", reportEvery=100).items()
            if key != "checkpoint"
        }
        config_hash = _canonical_hash(canonical_request)
        started = time.perf_counter()
        if request["mode"] == "visual":
            yield {
                "schemaVersion": "1.0.0",
                "event": "started",
                "configHash": config_hash,
                "game": GAME,
                "algorithm": ALGORITHM,
                "privateDeals": len(self.deals),
            }
        for iteration in range(self.completed_iterations + 1, iterations + 1):
            self.run_iteration(iteration)
            if request["mode"] == "visual" and iteration % request["reportEvery"] == 0:
                positive_regret = sum(max(value, 0.0) for node in self.nodes.values() for value in node.regret_sum)
                yield {
                    "schemaVersion": "1.0.0",
                    "event": "progress",
                    "configHash": config_hash,
                    "iteration": iteration,
                    "informationSets": len(self.nodes),
                    "positiveRegret": positive_regret,
                    "elapsedMs": int((time.perf_counter() - started) * 1000),
                }
        artifact = self.artifact()
        artifact_hash = _canonical_hash(artifact)
        yield {
            "schemaVersion": "1.0.0",
            "event": "complete",
            "configHash": config_hash,
            "artifactHash": artifact_hash,
            "game": GAME,
            "algorithm": ALGORITHM,
            "mode": request["mode"],
            "iterations": iterations,
            "informationSets": len(self.nodes),
            "elapsedMs": int((time.perf_counter() - started) * 1000),
            "strategy": artifact,
            "checkpoint": self.checkpoint(),
        }


def _validate_request(request: dict[str, Any]) -> None:
    required = {"schemaVersion", "game", "algorithm", "mode", "iterations", "seed", "reportEvery"}
    optional = {"checkpoint"}
    if not required.issubset(request) or set(request) - required - optional:
        raise ValueError("restricted NLHE request fields do not match training-request/v1")
    if request["schemaVersion"] != "1.0.0" or request["game"] != GAME or request["algorithm"] != ALGORITHM:
        raise ValueError("request is not restricted hold'em external-sampling MCCFR")
    if request["mode"] not in ("visual", "headless"):
        raise ValueError("mode must be visual or headless")
    if type(request["iterations"]) is not int or not 1 <= request["iterations"] <= 1_000_000:
        raise ValueError("iterations must be an integer from 1 to 1000000")
    if type(request["seed"]) is not int:
        raise ValueError("seed must be an integer")
    if type(request["reportEvery"]) is not int or request["reportEvery"] < 1:
        raise ValueError("reportEvery must be a positive integer")


def _validate_checkpoint(checkpoint: dict[str, Any]) -> None:
    if not isinstance(checkpoint, dict) or checkpoint.get("checkpointHash") != _content_hash(checkpoint):
        raise ValueError("checkpoint hash mismatch")
    expected = {
        "schemaVersion", "game", "algorithm", "seed", "completedIterations",
        "abstractionId", "encoderVersion", "actionVersion", "requiredHashes", "nodes", "checkpointHash",
    }
    if set(checkpoint) != expected:
        raise ValueError("checkpoint fields do not match restricted-nlhe-checkpoint/v1")
    if (
        checkpoint["schemaVersion"] != "1.0.0"
        or checkpoint["game"] != GAME
        or checkpoint["algorithm"] != ALGORITHM
        or checkpoint["abstractionId"] != ABSTRACTION_ID
        or checkpoint["encoderVersion"] != ENCODER_VERSION
        or checkpoint["actionVersion"] != ACTION_VERSION
    ):
        raise ValueError("checkpoint contract is incompatible")
    if type(checkpoint["seed"]) is not int or type(checkpoint["completedIterations"]) is not int:
        raise ValueError("checkpoint seed and iteration must be integers")
    if checkpoint["completedIterations"] < 0 or not isinstance(checkpoint["nodes"], dict):
        raise ValueError("invalid checkpoint iteration or nodes")
    if checkpoint["requiredHashes"] != _contract_hashes(checkpoint["nodes"]):
        raise ValueError("checkpoint contract or policy hash mismatch")
    for key, value in checkpoint["nodes"].items():
        if not isinstance(key, str) or set(value) != {"actions", "canonicalJson", "regretSum", "strategySum"}:
            raise ValueError("invalid checkpoint node")
        count = len(value["actions"])
        if count == 0 or len(value["regretSum"]) != count or len(value["strategySum"]) != count:
            raise ValueError("checkpoint node action count mismatch")
