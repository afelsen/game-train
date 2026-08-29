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

MODEL_VERSION = "masked-linear-combo-scorer-v2"
FEATURE_VERSION = "range-combo-features-v2"
FEATURE_COUNT = 19


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
            strength * aggression,
            strength * passive,
            strength * folds,
            pair * aggression,
            suited * aggression,
            connects_board * aggression,
            connects_board * passive,
            suit_matches_board * aggression,
        ],
        dtype=np.float64,
    )


@dataclass(frozen=True)
class RangeEstimatorModel:
    weights: tuple[float, ...]
    dataset_hash: str
    calibration_temperature: float = 1.0
    dataset_version: str = DATASET_VERSION

    def __post_init__(self) -> None:
        if len(self.weights) != FEATURE_COUNT or self.calibration_temperature <= 0:
            raise ValueError("range estimator model has an incompatible feature contract")

    def predict(self, request: dict[str, Any]) -> dict[str, Any]:
        context = validate_request(request)
        combos = legal_villain_combos(context["heroCards"], context["board"])
        features = np.vstack([combo_features(context, combo) for combo in combos])
        probabilities = _softmax(_linear_scores(features, np.asarray(self.weights)) / self.calibration_temperature)
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
            "datasetVersion": self.dataset_version,
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
        report_every_examples: int = 100,
        initial_weights: tuple[float, ...] | None = None,
        start_epoch: int = 0,
    ) -> Iterator[dict[str, Any]]:
        if (type(epochs) is not int or epochs < 1 or type(report_every) is not int or report_every < 1
                or type(report_every_examples) is not int or report_every_examples < 1):
            raise ValueError("epochs and report intervals must be positive integers")
        if not isinstance(learning_rate, (int, float)) or not 0 < learning_rate <= 1:
            raise ValueError("learning_rate must be between 0 and 1")
        manifest, records = dataset.get("manifest"), dataset.get("records")
        if not isinstance(manifest, dict) or not isinstance(records, list):
            raise ValueError("range estimator dataset must contain manifest and records")
        dataset_version = manifest.get("datasetVersion")
        if not isinstance(dataset_version, str) or not dataset_version:
            raise ValueError("range estimator dataset version is missing")
        train = [record for record in records if record.get("split") == "train"]
        validation = [record for record in records if record.get("split") == "validation"]
        if not train or not validation:
            raise ValueError("range estimator dataset needs train and validation examples")
        if type(start_epoch) is not int or not 0 <= start_epoch < epochs:
            raise ValueError("start_epoch must be zero through epochs minus one")
        if initial_weights is not None and len(initial_weights) != FEATURE_COUNT:
            raise ValueError("initial_weights do not match the model feature contract")
        dataset_hash = str(manifest["recordHash"])
        weights = np.asarray(initial_weights if initial_weights is not None else np.zeros(FEATURE_COUNT), dtype=np.float64)
        # Live curves use a fixed bounded validation sample. The final event is
        # still scored on the full validation split.
        prepared_live_validation = [_prepared_record(record) for record in validation[:100]]
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
        prepared_cache: dict[int, tuple[dict[str, Any], int, np.ndarray]] = {}

        def prepared(index: int) -> tuple[dict[str, Any], int, np.ndarray]:
            """Bound candidate-matrix memory to avoid O(dataset size) allocations."""
            value = prepared_cache.pop(index, None)
            if value is None:
                value = _prepared_record(train[index])
            prepared_cache[index] = value
            if len(prepared_cache) > 128:
                prepared_cache.pop(next(iter(prepared_cache)))
            return value

        for epoch in range(start_epoch + 1, epochs + 1):
            order = list(range(len(train)))
            order_rng.shuffle(order)
            for position, index in enumerate(order, start=1):
                context, target_index, features = prepared(index)
                probabilities = _softmax(_linear_scores(features, weights))
                target = np.zeros(len(probabilities), dtype=np.float64)
                target[target_index] = 1.0
                weights -= float(learning_rate) * np.einsum("ij,i->j", features, probabilities - target)
                if position % report_every_examples == 0 and position < len(order):
                    metrics = _prepared_metrics(prepared_live_validation, weights)
                    yield {
                        "schemaVersion": SCHEMA_VERSION,
                        "event": "progress",
                        "epoch": epoch,
                        "epochs": epochs,
                    "examplesCompleted": (epoch - 1) * len(train) + position,
                        "examplesTotal": epochs * len(train),
                        **metrics,
                        "checkpoint": RangeEstimatorModel(tuple(weights), dataset_hash, dataset_version=dataset_version).checkpoint(),
                    }
            if epoch % report_every == 0 or epoch == epochs:
                metrics = _metrics(validation, weights) if epoch == epochs else _prepared_metrics(prepared_live_validation, weights)
                yield {
                    "schemaVersion": SCHEMA_VERSION,
                    "event": "progress" if epoch < epochs else "complete",
                    "epoch": epoch,
                    "epochs": epochs,
                    "examplesCompleted": epoch * len(train),
                    "examplesTotal": epochs * len(train),
                    **metrics,
                    "checkpoint": RangeEstimatorModel(tuple(weights), dataset_hash, dataset_version=dataset_version).checkpoint(),
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
    return _prepared_metrics([_prepared_record(record) for record in records], weights)


def _prepared_metrics(
    records: list[tuple[dict[str, Any], int, np.ndarray]], weights: np.ndarray
) -> dict[str, float]:
    nll = brier = top1 = top5 = class_top1 = baseline_nll = baseline_brier = 0.0
    confidences: list[tuple[float, float]] = []
    for context, target_index, features in records:
        probabilities = _softmax(_linear_scores(features, weights))
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


def _linear_scores(features: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Avoid small matrix-multiply thread overhead in the per-example SGD loop."""
    return np.einsum("ij,j->i", features, weights)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
