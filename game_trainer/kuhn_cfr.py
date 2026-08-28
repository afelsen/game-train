from __future__ import annotations

import hashlib
import itertools
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

CARDS = ("J", "Q", "K")
ACTIONS = ("pass", "bet")
DEALS = tuple(itertools.permutations(range(3), 2))


@dataclass
class InformationSet:
    regret_sum: list[float] = field(default_factory=lambda: [0.0, 0.0])
    strategy_sum: list[float] = field(default_factory=lambda: [0.0, 0.0])

    def strategy(self, reach_probability: float) -> tuple[float, float]:
        positive = [max(value, 0.0) for value in self.regret_sum]
        total = sum(positive)
        strategy = (positive[0] / total, positive[1] / total) if total else (0.5, 0.5)
        for index, probability in enumerate(strategy):
            self.strategy_sum[index] += reach_probability * probability
        return strategy

    def average_strategy(self) -> tuple[float, float]:
        total = sum(self.strategy_sum)
        return (
            (self.strategy_sum[0] / total, self.strategy_sum[1] / total)
            if total
            else (0.5, 0.5)
        )


def _terminal_utility_player_zero(cards: tuple[int, int], history: str) -> float | None:
    if history == "pp":
        return 1.0 if cards[0] > cards[1] else -1.0
    if history == "bp":
        return 1.0
    if history == "pbp":
        return -1.0
    if history in ("bb", "pbb"):
        return 2.0 if cards[0] > cards[1] else -2.0
    return None


def _information_set(card: int, history: str) -> str:
    return f"{CARDS[card]}:{history}"


def _profile_utility(
    cards: tuple[int, int],
    history: str,
    strategy: dict[str, tuple[float, float]],
    pure_player: int | None = None,
    pure_actions: dict[str, int] | None = None,
) -> float:
    terminal = _terminal_utility_player_zero(cards, history)
    if terminal is not None:
        return terminal
    player = len(history) % 2
    key = _information_set(cards[player], history)
    probabilities = strategy.get(key, (0.5, 0.5))
    if player == pure_player and pure_actions is not None:
        probabilities = (1.0, 0.0) if pure_actions[key] == 0 else (0.0, 1.0)
    return sum(
        probability * _profile_utility(cards, history + action_code, strategy, pure_player, pure_actions)
        for probability, action_code in zip(probabilities, ("p", "b"))
    )


def evaluate_strategy(strategy: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """Return player-zero value and exact two-player NashConv exploitability."""
    value = sum(_profile_utility(deal, "", strategy) for deal in DEALS) / len(DEALS)
    best_responses: list[float] = []
    for player, histories in ((0, ("", "pb")), (1, ("p", "b"))):
        keys = [_information_set(card, history) for card in range(3) for history in histories]
        best = float("-inf")
        for choices in itertools.product((0, 1), repeat=len(keys)):
            pure = dict(zip(keys, choices))
            utility_zero = sum(
                _profile_utility(deal, "", strategy, player, pure) for deal in DEALS
            ) / len(DEALS)
            best = max(best, utility_zero if player == 0 else -utility_zero)
        best_responses.append(best)
    return value, max(0.0, sum(best_responses))


class KuhnCfrTrainer:
    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.completed_iterations = 0
        self.nodes: dict[str, InformationSet] = {}

    def checkpoint(self) -> dict[str, Any]:
        content: dict[str, Any] = {
            "schemaVersion": "1.0.0",
            "game": "kuhn-poker",
            "algorithm": "cfr",
            "seed": self.seed,
            "completedIterations": self.completed_iterations,
            "nodes": {
                key: {
                    "regretSum": list(node.regret_sum),
                    "strategySum": list(node.strategy_sum),
                }
                for key, node in sorted(self.nodes.items())
            },
        }
        content["checkpointHash"] = _content_hash(content)
        return content

    def load_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        _validate_checkpoint(checkpoint)
        if checkpoint["game"] != "kuhn-poker":
            raise ValueError("checkpoint is not a Kuhn poker checkpoint")
        if checkpoint["seed"] != self.seed:
            raise ValueError("checkpoint seed does not match training request")
        self.completed_iterations = checkpoint["completedIterations"]
        self.nodes = {
            key: InformationSet(
                regret_sum=[float(value) for value in values["regretSum"]],
                strategy_sum=[float(value) for value in values["strategySum"]],
            )
            for key, values in checkpoint["nodes"].items()
        }

    def _cfr(
        self,
        cards: tuple[int, int],
        history: str,
        reach_zero: float,
        reach_one: float,
    ) -> float:
        terminal_zero = _terminal_utility_player_zero(cards, history)
        player = len(history) % 2
        if terminal_zero is not None:
            return terminal_zero if player == 0 else -terminal_zero
        key = _information_set(cards[player], history)
        node = self.nodes.setdefault(key, InformationSet())
        own_reach = reach_zero if player == 0 else reach_one
        opponent_reach = reach_one if player == 0 else reach_zero
        strategy = node.strategy(own_reach)
        action_utilities = []
        node_utility = 0.0
        for action_index, action_code in enumerate(("p", "b")):
            next_zero = reach_zero * strategy[action_index] if player == 0 else reach_zero
            next_one = reach_one * strategy[action_index] if player == 1 else reach_one
            utility = -self._cfr(cards, history + action_code, next_zero, next_one)
            action_utilities.append(utility)
            node_utility += strategy[action_index] * utility
        for action_index, utility in enumerate(action_utilities):
            node.regret_sum[action_index] += opponent_reach * (utility - node_utility)
        return node_utility

    def average_strategy(self) -> dict[str, tuple[float, float]]:
        return {key: node.average_strategy() for key, node in sorted(self.nodes.items())}

    def artifact(self) -> list[dict[str, Any]]:
        strategy = self.average_strategy()
        return [
            {
                "informationSet": key,
                "player": 0 if history in ("", "pb") else 1,
                "card": card,
                "history": history,
                "actions": {action: probability for action, probability in zip(ACTIONS, probabilities)},
            }
            for key, probabilities in strategy.items()
            for card, history in (key.split(":"),)
        ]

    def train_events(self, request: dict[str, Any]) -> Iterator[dict[str, Any]]:
        _validate_request(request)
        if request.get("checkpoint") is not None:
            self.load_checkpoint(request["checkpoint"])
        mode = request["mode"]
        iterations = request["iterations"]
        if self.completed_iterations > iterations:
            raise ValueError("checkpoint is beyond requested iterations")
        report_every = request["reportEvery"]
        canonical = {
            key: value
            for key, value in dict(request, mode="headless", reportEvery=100).items()
            if key != "checkpoint"
        }
        config_hash = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        started = time.perf_counter()
        if mode == "visual":
            yield {
                "schemaVersion": "1.0.0",
                "event": "started",
                "configHash": config_hash,
                "game": "kuhn-poker",
                "algorithm": "cfr",
            }
        for iteration in range(self.completed_iterations + 1, iterations + 1):
            deals = list(DEALS)
            rng = random.Random((self.seed << 32) ^ iteration)
            rng.shuffle(deals)
            for deal in deals:
                self._cfr(deal, "", 1.0, 1.0)
            self.completed_iterations = iteration
            if mode == "visual" and iteration % report_every == 0:
                value, exploitability = evaluate_strategy(self.average_strategy())
                yield {
                    "schemaVersion": "1.0.0",
                    "event": "progress",
                    "configHash": config_hash,
                    "iteration": iteration,
                    "gameValue": value,
                    "exploitability": exploitability,
                    "elapsedMs": int((time.perf_counter() - started) * 1000),
                }
        strategy_artifact = self.artifact()
        value, exploitability = evaluate_strategy(self.average_strategy())
        artifact_hash = hashlib.sha256(
            json.dumps(strategy_artifact, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        yield {
            "schemaVersion": "1.0.0",
            "event": "complete",
            "configHash": config_hash,
            "artifactHash": artifact_hash,
            "game": "kuhn-poker",
            "algorithm": "cfr",
            "mode": mode,
            "iterations": iterations,
            "gameValue": value,
            "exploitability": exploitability,
            "elapsedMs": int((time.perf_counter() - started) * 1000),
            "strategy": strategy_artifact,
            "checkpoint": self.checkpoint(),
        }


def _validate_request(request: dict[str, Any]) -> None:
    required = {
        "schemaVersion",
        "game",
        "algorithm",
        "mode",
        "iterations",
        "seed",
        "reportEvery",
    }
    if not required.issubset(request) or set(request) - required != ({"checkpoint"} if "checkpoint" in request else set()):
        raise ValueError(
            f"training request fields must contain {sorted(required)} with only optional checkpoint"
        )
    if request["schemaVersion"] != "1.0.0":
        raise ValueError("unsupported schemaVersion")
    supported = {
        ("kuhn-poker", "cfr"),
        ("leduc-holdem", "cfr"),
        ("restricted-hu-nlhe-flop", "external-sampling-mccfr"),
    }
    if (request["game"], request["algorithm"]) not in supported:
        raise ValueError("unsupported game and training algorithm combination")
    if request["mode"] not in ("visual", "headless"):
        raise ValueError("mode must be visual or headless")
    if type(request["iterations"]) is not int or not 1 <= request["iterations"] <= 1_000_000:
        raise ValueError("iterations must be an integer from 1 to 1000000")
    if type(request["seed"]) is not int:
        raise ValueError("seed must be an integer")
    if type(request["reportEvery"]) is not int or request["reportEvery"] < 1:
        raise ValueError("reportEvery must be a positive integer")


def _content_hash(content: dict[str, Any]) -> str:
    canonical = {key: value for key, value in content.items() if key != "checkpointHash"}
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _validate_checkpoint(checkpoint: dict[str, Any]) -> None:
    if not isinstance(checkpoint, dict):
        raise ValueError("checkpoint must be an object")
    required = {
        "schemaVersion",
        "game",
        "algorithm",
        "seed",
        "completedIterations",
        "nodes",
        "checkpointHash",
    }
    if set(checkpoint) != required:
        raise ValueError("checkpoint fields do not match checkpoint/v1")
    if (
        checkpoint["schemaVersion"] != "1.0.0"
        or checkpoint["game"] not in ("kuhn-poker", "leduc-holdem")
        or checkpoint["algorithm"] != "cfr"
    ):
        raise ValueError("checkpoint is not a supported CFR checkpoint")
    if type(checkpoint["seed"]) is not int:
        raise ValueError("checkpoint seed must be an integer")
    if type(checkpoint["completedIterations"]) is not int or checkpoint["completedIterations"] < 0:
        raise ValueError("checkpoint completedIterations must be non-negative")
    if not isinstance(checkpoint["nodes"], dict):
        raise ValueError("checkpoint nodes must be an object")
    for key, values in checkpoint["nodes"].items():
        if not isinstance(key, str) or not isinstance(values, dict):
            raise ValueError("invalid checkpoint information set")
        expected_fields = (
            {"regretSum", "strategySum", "policy"}
            if checkpoint["game"] == "leduc-holdem"
            else {"regretSum", "strategySum"}
        )
        if set(values) != expected_fields:
            raise ValueError("invalid checkpoint node fields")
        for field_name in expected_fields:
            values_list = values[field_name]
            if (
                not isinstance(values_list, list)
                or len(values_list)
                != (4 if checkpoint["game"] == "leduc-holdem" else 2)
                or any(not isinstance(value, (int, float)) for value in values_list)
            ):
                raise ValueError(f"checkpoint {field_name} has the wrong action count")
    if checkpoint["checkpointHash"] != _content_hash(checkpoint):
        raise ValueError("checkpoint hash mismatch")


def train_kuhn(request: dict[str, Any]) -> list[dict[str, Any]]:
    return list(KuhnCfrTrainer(seed=request.get("seed", 0)).train_events(request))
