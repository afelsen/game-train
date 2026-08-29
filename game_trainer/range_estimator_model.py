"""Masked, interpretable combo-posterior model for range-estimator/v1."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterator

import numpy as np

from game_trainer.range_estimator import _class_name, _preflop_strength
from game_trainer.range_estimator_dataset import (
    DATASET_VERSION,
    SCHEMA_VERSION,
    legal_villain_combos,
    validate_request,
)

MODEL_VERSION = "masked-linear-combo-scorer-v1"
FEATURE_VERSION = "range-combo-features-v1"
FEATURE_COUNT = 11


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    weights = np.exp(shifted)
    return weights / np.sum(weights)


def _action_summary(actions: list[dict[str, Any]]) -> tuple[float, float, float]:
    villain = [action for action in actions if action.get("seat") == 1]
    total = max(1, len(villain))
    aggression = sum(action.get("type") in ("raise-to", "all-in") for action in villain) / total
    passive = sum(action.get("type") in ("check", "call") for action in villain) / total
    folds = sum(action.get("type") == "fold" for action in villain) / total
    return float(aggression), float(passive), float(folds)


def combo_features(context: dict[str, Any], combo: tuple[str, str]) -> np.ndarray:
    """Public context plus a candidate combo; never uses the target label."""
    board = context["board"]
    actions = context["actions"]
    strength = _preflop_strength(combo)
    pair = float(combo[0][0] == combo[1][0])
    suited = float(combo[0][1] == combo[1][1])
    board_ranks = {card[0] for card in board}
    board_suits = {card[1] for card in board}
    connects_board = float(any(card[0] in board_ranks for card in combo))
    suit_matches_board = float(sum(card[1] in board_suits for card in combo)) / 2
    aggression, passive, folds = _action_summary(actions)
    street = len(board) / 5
    return np.array(
        [
            1.0,
            strength,
            strength * strength,
            pair,
            suited,
            connects_board,
            suit_matches_board,
            street,
            aggression,
            passive,
            folds,
        ],
        dtype=np.float64,
    )


@dataclass(frozen=True)
class RangeEstimatorModel:
    weights: tuple[float, ...]
    dataset_hash: str
    calibration_temperature: float = 1.0

    def __post_init__(self) -> None:
        if len(self.weights) != FEATURE_COUNT or self.calibration_temperature <= 0:
            raise ValueError("range estimator model has an incompatible feature contract")

    def predict(self, request: dict[str, Any]) -> dict[str, Any]:
        context = validate_request(request)
        combos = legal_villain_combos(context["heroCards"], context["board"])
        features = np.vstack([combo_features(context, combo) for combo in combos])
        probabilities = _softmax(features @ np.asarray(self.weights) / self.calibration_temperature)
        grouped: dict[str, float] = defaultdict(float)
        for combo, probability in zip(combos, probabilities):
            grouped[_class_name(combo)] += float(probability)
        entropy = -float(np.sum(probabilities * np.log(np.maximum(probabilities, 1e-12))))
        return {
            "schemaVersion": SCHEMA_VERSION,
            "method": MODEL_VERSION,
            "priorId": context["priorId"],
            "combos": [
                {"cards": list(combo), "weight": float(probability)}
                for combo, probability in zip(combos, probabilities)
            ],
            "topClasses": [
                {"handClass": hand_class, "weight": weight}
                for hand_class, weight in sorted(grouped.items(), key=lambda item: item[1], reverse=True)[:8]
            ],
            "entropy": entropy,
            "diagnostics": {
                "legalComboCount": len(combos),
                "normalizationError": abs(float(np.sum(probabilities)) - 1.0),
                "featureVersion": FEATURE_VERSION,
                "datasetHash": self.dataset_hash,
                "calibrationTemperature": self.calibration_temperature,
            },
        }

    def checkpoint(self) -> dict[str, Any]:
        content = {
            "schemaVersion": SCHEMA_VERSION,
            "modelVersion": MODEL_VERSION,
            "featureVersion": FEATURE_VERSION,
            "datasetVersion": DATASET_VERSION,
            "datasetHash": self.dataset_hash,
            "calibrationTemperature": self.calibration_temperature,
            "weights": list(self.weights),
        }
        content["checkpointHash"] = _hash(content)
        return content


class RangeEstimatorTrainer:
    """Deterministic SGD trainer that only observes public context and labels."""

    def __init__(self, seed: int = 0) -> None:
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        self.seed = seed

    def train_events(
        self,
        dataset: dict[str, Any],
        *,
        epochs: int,
        learning_rate: float,
        report_every: int = 1,
    ) -> Iterator[dict[str, Any]]:
        if type(epochs) is not int or epochs < 1 or type(report_every) is not int or report_every < 1:
            raise ValueError("epochs and report_every must be positive integers")
        if not isinstance(learning_rate, (int, float)) or not 0 < learning_rate <= 1:
            raise ValueError("learning_rate must be between 0 and 1")
        manifest, records = dataset.get("manifest"), dataset.get("records")
        if not isinstance(manifest, dict) or not isinstance(records, list):
            raise ValueError("range estimator dataset must contain manifest and records")
        if manifest.get("datasetVersion") != DATASET_VERSION:
            raise ValueError("range estimator dataset version is incompatible")
        train = [record for record in records if record.get("split") == "train"]
        validation = [record for record in records if record.get("split") == "validation"]
        if not train or not validation:
            raise ValueError("range estimator dataset needs train and validation examples")
        dataset_hash = str(manifest["recordHash"])
        weights = np.zeros(FEATURE_COUNT, dtype=np.float64)
        yield {
            "schemaVersion": SCHEMA_VERSION,
            "event": "started",
            "modelVersion": MODEL_VERSION,
            "datasetHash": dataset_hash,
            "epochs": epochs,
            "trainExamples": len(train),
            "validationExamples": len(validation),
        }
        order_rng = random.Random(self.seed)
        for epoch in range(1, epochs + 1):
            order = list(range(len(train)))
            order_rng.shuffle(order)
            for index in order:
                context, target_index, features = _prepared_record(train[index])
                probabilities = _softmax(features @ weights)
                target = np.zeros(len(probabilities), dtype=np.float64)
                target[target_index] = 1.0
                weights -= float(learning_rate) * (features.T @ (probabilities - target))
            if epoch % report_every == 0 or epoch == epochs:
                metrics = _metrics(validation, weights)
                yield {
                    "schemaVersion": SCHEMA_VERSION,
                    "event": "progress" if epoch < epochs else "complete",
                    "epoch": epoch,
                    "epochs": epochs,
                    **metrics,
                    "checkpoint": RangeEstimatorModel(tuple(weights), dataset_hash).checkpoint(),
                }


def _prepared_record(record: dict[str, Any]) -> tuple[dict[str, Any], int, np.ndarray]:
    context = validate_request(record["context"])
    combos = legal_villain_combos(context["heroCards"], context["board"])
    target = frozenset(record["targetVillainCards"])
    target_index = next((index for index, combo in enumerate(combos) if frozenset(combo) == target), None)
    if target_index is None:
        raise ValueError("range estimator target is not a legal combo")
    return context, target_index, np.vstack([combo_features(context, combo) for combo in combos])


def _metrics(records: list[dict[str, Any]], weights: np.ndarray) -> dict[str, float]:
    nll = brier = top1 = top5 = class_top1 = baseline_nll = baseline_brier = 0.0
    confidences: list[tuple[float, float]] = []
    for record in records:
        context, target_index, features = _prepared_record(record)
        probabilities = _softmax(features @ weights)
        target_probability = float(probabilities[target_index])
        combos = legal_villain_combos(context["heroCards"], context["board"])
        nll -= math.log(max(target_probability, 1e-12))
        brier += float(np.sum(probabilities * probabilities) - 2 * target_probability + 1)
        top1 += float(int(np.argmax(probabilities) == target_index))
        top5 += float(target_index in np.argsort(probabilities)[-5:])
        target_class = _class_name(combos[target_index])
        class_weights: dict[str, float] = defaultdict(float)
        for combo, probability in zip(combos, probabilities):
            class_weights[_class_name(combo)] += float(probability)
        class_top1 += float(max(class_weights, key=class_weights.get) == target_class)
        legal_count = len(probabilities)
        baseline_nll += math.log(legal_count)
        baseline_brier += 1 - 1 / legal_count
        confidences.append((float(np.max(probabilities)), float(int(np.argmax(probabilities) == target_index))))
    ece = _expected_calibration_error(confidences)
    count = len(records)
    return {
        "validationNll": nll / count,
        "validationNllGain": (baseline_nll - nll) / count,
        "validationBrier": brier / count,
        "validationBrierImprovement": (baseline_brier - brier) / baseline_brier * 100,
        "validationTop1": top1 / count,
        "validationTop5": top5 / count,
        "validationHandClassTop1": class_top1 / count,
        "validationEce": ece,
    }


def _expected_calibration_error(confidences: list[tuple[float, float]], bins: int = 10) -> float:
    total = len(confidences)
    error = 0.0
    for bucket in range(bins):
        low, high = bucket / bins, (bucket + 1) / bins
        values = [item for item in confidences if low <= item[0] < high or (bucket == bins - 1 and item[0] == 1)]
        if values:
            error += len(values) / total * abs(
                sum(item[0] for item in values) / len(values)
                - sum(item[1] for item in values) / len(values)
            )
    return error


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
