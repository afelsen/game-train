from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from game_trainer.kuhn_cfr import _content_hash, _validate_checkpoint, _validate_request

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "rlcard"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

import rlcard  # noqa: E402
from rlcard.agents import CFRAgent  # noqa: E402


def _key(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _label(value: bytes) -> str:
    observation = np.frombuffer(value, dtype=float)
    ranks = ("J", "Q", "K")
    private = ranks[int(np.argmax(observation[:3]))]
    public = (
        ranks[int(np.argmax(observation[3:6]))]
        if float(observation[3:6].sum()) > 0
        else "—"
    )
    own = int(np.argmax(observation[6:21]))
    opponent = int(np.argmax(observation[21:36]))
    return f"{private} | board {public} | chips {own}:{opponent}"


class LeducCfrTrainer:
    """Chance-sampled CFR for RLCard's pinned two-player Leduc ruleset."""

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.env = rlcard.make(
            "leduc-holdem", {"seed": seed, "allow_step_back": True}
        )
        self.agent = CFRAgent(self.env)

    def checkpoint(self) -> dict[str, Any]:
        keys = set(self.agent.regrets) | set(self.agent.policy) | set(self.agent.average_policy)
        content: dict[str, Any] = {
            "schemaVersion": "1.0.0",
            "game": "leduc-holdem",
            "algorithm": "cfr",
            "seed": self.seed,
            "completedIterations": self.agent.iteration,
            "nodes": {
                _key(key): {
                    "regretSum": np.asarray(
                        self.agent.regrets.get(key, np.zeros(4)), dtype=float
                    ).tolist(),
                    "strategySum": np.asarray(
                        self.agent.average_policy.get(key, np.zeros(4)), dtype=float
                    ).tolist(),
                    "policy": np.asarray(
                        self.agent.policy.get(key, np.full(4, 0.25)), dtype=float
                    ).tolist(),
                }
                for key in sorted(keys)
            },
        }
        content["checkpointHash"] = _content_hash(content)
        return content

    def load_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        _validate_checkpoint(checkpoint)
        if checkpoint["game"] != "leduc-holdem":
            raise ValueError("checkpoint is not a Leduc hold'em checkpoint")
        if checkpoint["seed"] != self.seed:
            raise ValueError("checkpoint seed does not match training request")
        self.agent.iteration = checkpoint["completedIterations"]
        self.agent.regrets = defaultdict(np.array)
        self.agent.average_policy = defaultdict(np.array)
        self.agent.policy = defaultdict(list)
        for encoded, values in checkpoint["nodes"].items():
            key = _decode(encoded)
            self.agent.regrets[key] = np.asarray(values["regretSum"], dtype=float)
            self.agent.average_policy[key] = np.asarray(
                values["strategySum"], dtype=float
            )
            self.agent.policy[key] = np.asarray(values["policy"], dtype=float)

    def _artifact(self) -> list[dict[str, Any]]:
        result = []
        for key, totals in sorted(self.agent.average_policy.items()):
            values = np.asarray(totals, dtype=float)
            total = float(values.sum())
            if total <= 0:
                continue
            probabilities = values / total
            result.append(
                {
                    "informationSet": _key(key),
                    "label": _label(key),
                    "actions": {
                        action: float(probabilities[index])
                        for index, action in enumerate(("call", "raise", "fold", "check"))
                    },
                }
            )
        return result

    def _reference_score(self, episodes: int = 80) -> float:
        """Average payoff versus the pinned pretrained CFR policy, alternating seats."""
        import rlcard.models

        reference = rlcard.models.load("leduc-holdem-cfr")
        total = 0.0
        np.random.seed(self.seed ^ self.agent.iteration)
        for episode in range(episodes):
            seat = episode % 2
            agents = [reference.agents[0], reference.agents[1]]
            agents[seat] = self.agent
            self.env.set_agents(agents)
            _, payoffs = self.env.run(is_training=False)
            total += float(payoffs[seat])
        return total / episodes

    def train_events(self, request: dict[str, Any]) -> Iterator[dict[str, Any]]:
        _validate_request(request)
        if request["game"] != "leduc-holdem":
            raise ValueError("Leduc trainer requires game leduc-holdem")
        checkpoint = request.get("checkpoint")
        if checkpoint is not None:
            self.load_checkpoint(checkpoint)
        iterations = request["iterations"]
        if self.agent.iteration > iterations:
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
        if request["mode"] == "visual":
            yield {
                "schemaVersion": "1.0.0",
                "event": "started",
                "configHash": config_hash,
                "game": "leduc-holdem",
                "algorithm": "cfr",
            }
        while self.agent.iteration < iterations:
            next_iteration = self.agent.iteration + 1
            self.env.seed((self.seed ^ (next_iteration * 0x9E3779B1)) & 0xFFFFFFFF)
            self.agent.train()
            if request["mode"] == "visual" and self.agent.iteration % report_every == 0:
                yield {
                    "schemaVersion": "1.0.0",
                    "event": "progress",
                    "configHash": config_hash,
                    "iteration": self.agent.iteration,
                    "referenceScore": self._reference_score(),
                    "elapsedMs": int((time.perf_counter() - started) * 1000),
                }
        artifact = self._artifact()
        artifact_hash = hashlib.sha256(
            json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        yield {
            "schemaVersion": "1.0.0",
            "event": "complete",
            "configHash": config_hash,
            "artifactHash": artifact_hash,
            "game": "leduc-holdem",
            "algorithm": "cfr",
            "mode": request["mode"],
            "iterations": iterations,
            "referenceScore": self._reference_score(episodes=200),
            "elapsedMs": int((time.perf_counter() - started) * 1000),
            "strategy": artifact,
            "checkpoint": self.checkpoint(),
        }
