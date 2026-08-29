"""Durable asynchronous jobs for the masked Villain range estimator."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from game_trainer.range_estimator_dataset import DATASET_VERSION, generate_synthetic_dataset
from game_trainer.phh_range_dataset import PHH_DATASET_VERSION, load_phh_pilot
from game_trainer.range_estimator import _class_name, estimate_villain_range
from game_trainer.range_estimator_model import (
    MODEL_VERSION,
    RangeEstimatorModel,
    RangeEstimatorTrainer,
    _metrics,
)


@dataclass
class RangeEstimatorJob:
    job_id: str
    request: dict[str, Any]
    status: str = "queued"
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class RangeEstimatorJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS range_estimator_jobs (
                    job_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    events_json TEXT NOT NULL,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_range_estimator_jobs_updated
                    ON range_estimator_jobs(updated_at DESC);
                """
            )
            connection.execute(
                "UPDATE range_estimator_jobs SET status = 'failed', error = 'range estimator training interrupted by restart', updated_at = ? WHERE status IN ('queued', 'running')",
                (time.time(),),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def save(self, job: RangeEstimatorJob) -> None:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO range_estimator_jobs
                   (job_id, request_json, status, events_json, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     status=excluded.status, events_json=excluded.events_json,
                     error=excluded.error, updated_at=excluded.updated_at""",
                (job.job_id, json.dumps(job.request), job.status, json.dumps(job.events), job.error, now, now),
            )

    def load(self, job_id: str) -> RangeEstimatorJob | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM range_estimator_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def recent(self, limit: int) -> list[RangeEstimatorJob]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM range_estimator_jobs ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._job(row) for row in rows]

    @staticmethod
    def _job(row: sqlite3.Row) -> RangeEstimatorJob:
        return RangeEstimatorJob(
            row["job_id"], json.loads(row["request_json"]), row["status"],
            json.loads(row["events_json"]), row["error"],
        )


class RangeEstimatorJobManager:
    """Runs deterministic synthetic training in a background thread with live metrics."""

    def __init__(self, database_path: Path | None = None) -> None:
        self.store = RangeEstimatorJobStore(database_path) if database_path else None
        self._jobs: dict[str, RangeEstimatorJob] = {}
        self._lock = threading.Lock()

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        self._validate(request)
        job = RangeEstimatorJob(f"range-{uuid4().hex[:12]}", dict(request))
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist(job)
        threading.Thread(target=self._run, args=(job.job_id,), daemon=True).start()
        return self.snapshot(job.job_id)

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._get(job_id)
            return self._snapshot(job)

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("range estimator job limit must be between 1 and 100")
        jobs = self.store.recent(limit) if self.store else list(self._jobs.values())[-limit:]
        return [self._summary(job) for job in jobs]

    def checkpoint(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            checkpoint = self._latest_checkpoint(self._get(job_id))
            if checkpoint is None:
                raise ValueError("range estimator job has no checkpoint yet")
            return json.loads(json.dumps(checkpoint))

    def evaluate(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._get(job_id)
            checkpoint = self._latest_checkpoint(job)
            if checkpoint is None:
                raise ValueError("range estimator job has no checkpoint yet")
            request = dict(job.request)
        dataset = self._dataset(request)
        test = [record for record in dataset["records"] if record["split"] == "test"]
        if not test:
            raise ValueError("range estimator dataset has no test examples; increase hands")
        metrics = _metrics(test, np.asarray(checkpoint["weights"], dtype=np.float64))
        heuristic = _heuristic_metrics(test)
        return {
            "schemaVersion": "1.0.0",
            "modelVersion": MODEL_VERSION,
            "jobId": job_id,
            "datasetVersion": DATASET_VERSION,
            "datasetHash": dataset["manifest"]["recordHash"],
            "testExamples": len(test),
            **{f"test{key[10:]}": value for key, value in metrics.items()},
            "baselines": {"actionWeightedHeuristicV1": heuristic},
            "checkpointHash": checkpoint["checkpointHash"],
        }

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._get(job_id)
            if job.status not in ("complete", "failed", "cancelled"):
                job.status, job.error = "cancelled", "cancelled by user"
                self._persist(job)
            return self._snapshot(job)

    def resume(self, job_id: str, *, epochs: int | None = None) -> dict[str, Any]:
        with self._lock:
            original = self._get(job_id)
            checkpoint = self._latest_checkpoint(original)
            latest = next((event for event in reversed(original.events) if event.get("epoch") is not None), None)
            if checkpoint is None or latest is None:
                raise ValueError("range estimator job has no checkpoint to resume")
            completed_epoch = int(latest["epoch"])
            target_epochs = int(epochs if epochs is not None else original.request["epochs"])
            if target_epochs <= completed_epoch:
                raise ValueError("resume epochs must exceed the saved checkpoint epoch")
            request = dict(original.request)
            request["epochs"] = target_epochs
            request["resumeCheckpoint"] = checkpoint
            request["resumeEpoch"] = completed_epoch
        return self._submit_resume(request)

    def wait(self, job_id: str, timeout: float = 10) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snapshot = self.snapshot(job_id)
            if snapshot["status"] in ("complete", "failed", "cancelled"):
                return snapshot
            time.sleep(0.01)
        return self.snapshot(job_id)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status == "cancelled":
                return
            job.status = "running"
            self._persist(job)
            request = dict(job.request)
        try:
            dataset = self._dataset(request)
            trainer = RangeEstimatorTrainer(request["seed"])
            checkpoint = request.get("resumeCheckpoint")
            for event in trainer.train_events(
                dataset, epochs=request["epochs"], learning_rate=request["learningRate"], report_every=request["reportEvery"],
                report_every_examples=request["reportEveryExamples"],
                initial_weights=tuple(checkpoint["weights"]) if isinstance(checkpoint, dict) else None,
                start_epoch=int(request.get("resumeEpoch", 0)),
            ):
                with self._lock:
                    job = self._jobs[job_id]
                    if job.status == "cancelled":
                        return
                    job.events.append(event)
                    self._persist(job)
            with self._lock:
                job = self._jobs[job_id]
                if job.status != "cancelled":
                    job.status = "complete"
                    self._persist(job)
        except Exception as error:
            with self._lock:
                job = self._jobs[job_id]
                if job.status != "cancelled":
                    job.status, job.error = "failed", str(error)
                    self._persist(job)

    def _get(self, job_id: str) -> RangeEstimatorJob:
        job = self._jobs.get(job_id)
        if job is None and self.store:
            job = self.store.load(job_id)
            if job is not None:
                self._jobs[job_id] = job
        if job is None:
            raise KeyError(f"unknown range estimator job: {job_id}")
        return job

    def _persist(self, job: RangeEstimatorJob) -> None:
        if self.store:
            self.store.save(job)

    @staticmethod
    def _latest_checkpoint(job: RangeEstimatorJob) -> dict[str, Any] | None:
        return next((event["checkpoint"] for event in reversed(job.events) if isinstance(event.get("checkpoint"), dict)), None)

    @classmethod
    def _snapshot(cls, job: RangeEstimatorJob) -> dict[str, Any]:
        return {"jobId": job.job_id, "status": job.status, "request": dict(job.request), "events": list(job.events), "error": job.error,
                "checkpointHash": (checkpoint.get("checkpointHash") if (checkpoint := cls._latest_checkpoint(job)) else None)}

    @classmethod
    def _summary(cls, job: RangeEstimatorJob) -> dict[str, Any]:
        return {"jobId": job.job_id, "status": job.status, "seed": job.request["seed"], "hands": job.request["hands"], "epochs": job.request["epochs"], "error": job.error,
                "checkpointHash": (checkpoint.get("checkpointHash") if (checkpoint := cls._latest_checkpoint(job)) else None)}

    @staticmethod
    def _validate(request: dict[str, Any]) -> None:
        allowed = {"schemaVersion", "source", "seed", "hands", "epochs", "learningRate", "reportEvery", "reportEveryExamples", "resumeCheckpoint", "resumeEpoch"}
        if not {"schemaVersion", "seed", "hands", "epochs", "learningRate", "reportEvery", "reportEveryExamples"}.issubset(request) or not set(request).issubset(allowed):
            raise ValueError("range estimator training request fields do not match range-estimator-training/v1")
        if request["schemaVersion"] != "1.0.0":
            raise ValueError("range estimator training schema is incompatible")
        if type(request["seed"]) is not int or type(request["hands"]) is not int or not 100 <= request["hands"] <= 100_000:
            raise ValueError("seed must be an integer and hands must be between 100 and 100000")
        if type(request["epochs"]) is not int or not 1 <= request["epochs"] <= 1000:
            raise ValueError("epochs must be between 1 and 1000")
        if not isinstance(request["learningRate"], (int, float)) or not 0 < request["learningRate"] <= 1:
            raise ValueError("learningRate must be between 0 and 1")
        if type(request["reportEvery"]) is not int or not 1 <= request["reportEvery"] <= request["epochs"]:
            raise ValueError("reportEvery must be between 1 and epochs")
        if type(request["reportEveryExamples"]) is not int or not 1 <= request["reportEveryExamples"] <= request["hands"]:
            raise ValueError("reportEveryExamples must be between 1 and hands")
        if "resumeCheckpoint" in request and (not isinstance(request["resumeCheckpoint"], dict) or type(request.get("resumeEpoch")) is not int):
            raise ValueError("range estimator resume checkpoint is invalid")
        if request.get("source", "synthetic") not in ("synthetic", "phh-pilot"):
            raise ValueError("range estimator source must be synthetic or phh-pilot")

    def _submit_resume(self, request: dict[str, Any]) -> dict[str, Any]:
        self._validate(request)
        job = RangeEstimatorJob(f"range-{uuid4().hex[:12]}", request)
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist(job)
        threading.Thread(target=self._run, args=(job.job_id,), daemon=True).start()
        return self.snapshot(job.job_id)

    @staticmethod
    def _dataset(request: dict[str, Any]) -> dict[str, Any]:
        if request.get("source", "synthetic") == "phh-pilot":
            path = Path(__file__).resolve().parent.parent / "data" / "external" / "phh" / "pokerstars-25nl-pilot.phhs"
            if not path.is_file():
                raise ValueError("PHH pilot is unavailable; download the public source file first")
            return load_phh_pilot(path)
        return generate_synthetic_dataset(request["seed"], request["hands"])


def _heuristic_metrics(records: list[dict[str, Any]]) -> dict[str, float]:
    """Score the current Play-tab action-weighted heuristic on identical labels."""
    nll = brier = top1 = top5 = class_top1 = baseline_nll = baseline_brier = 0.0
    for record in records:
        context = record["context"]
        estimate = estimate_villain_range(context["heroCards"], context["board"], context["actions"])
        probabilities = [float(combo["weight"]) for combo in estimate["combos"]]
        combos = [tuple(combo["cards"]) for combo in estimate["combos"]]
        target = frozenset(record["targetVillainCards"])
        target_index = next(index for index, combo in enumerate(combos) if frozenset(combo) == target)
        target_probability = probabilities[target_index]
        nll -= math.log(max(target_probability, 1e-12))
        brier += sum(probability * probability for probability in probabilities) - 2 * target_probability + 1
        top1 += float(max(range(len(probabilities)), key=probabilities.__getitem__) == target_index)
        top5 += float(target_index in sorted(range(len(probabilities)), key=probabilities.__getitem__)[-5:])
        grouped: dict[str, float] = {}
        for combo, probability in zip(combos, probabilities):
            hand_class = _class_name(combo)
            grouped[hand_class] = grouped.get(hand_class, 0.0) + probability
        class_top1 += float(max(grouped, key=grouped.get) == _class_name(combos[target_index]))
        baseline_nll += math.log(len(probabilities))
        baseline_brier += 1 - 1 / len(probabilities)
    count = len(records)
    return {
        "nll": nll / count,
        "nllGain": (baseline_nll - nll) / count,
        "brier": brier / count,
        "brierImprovement": (baseline_brier - brier) / baseline_brier * 100,
        "top1": top1 / count,
        "top5": top5 / count,
        "handClassTop1": class_top1 / count,
    }
