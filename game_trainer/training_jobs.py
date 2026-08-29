from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from game_trainer.kuhn_cfr import _validate_request


@dataclass
class TrainingJob:
    job_id: str
    request: dict[str, Any]
    status: str = "queued"
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class TrainingJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS training_jobs (
                    job_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    events_json TEXT NOT NULL,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_training_jobs_updated
                    ON training_jobs(updated_at DESC);
                CREATE TABLE IF NOT EXISTS training_models (
                    model_id TEXT PRIMARY KEY,
                    source_job_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    artifact_json TEXT NOT NULL,
                    registered_at REAL NOT NULL,
                    FOREIGN KEY(source_job_id) REFERENCES training_jobs(job_id)
                );
                CREATE INDEX IF NOT EXISTS idx_training_models_registered
                    ON training_models(registered_at DESC);
                """
            )
            connection.execute(
                "UPDATE training_jobs SET status = 'failed', error = 'training process interrupted by restart', updated_at = ? WHERE status IN ('queued', 'running')",
                (time.time(),),
            )
            connection.execute("PRAGMA optimize")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def save(self, job: TrainingJob) -> None:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO training_jobs
                   (job_id, request_json, status, events_json, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     status=excluded.status, events_json=excluded.events_json,
                     error=excluded.error, updated_at=excluded.updated_at""",
                (
                    job.job_id,
                    json.dumps(job.request),
                    job.status,
                    json.dumps(job.events),
                    job.error,
                    now,
                    now,
                ),
            )

    def load(self, job_id: str) -> TrainingJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM training_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return TrainingJob(
            job_id=row["job_id"],
            request=json.loads(row["request_json"]),
            status=row["status"],
            events=json.loads(row["events_json"]),
            error=row["error"],
        )

    def recent(self, limit: int = 20) -> list[TrainingJob]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM training_jobs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            TrainingJob(
                job_id=row["job_id"],
                request=json.loads(row["request_json"]),
                status=row["status"],
                events=json.loads(row["events_json"]),
                error=row["error"],
            )
            for row in rows
        ]

    def save_model(
        self, model_id: str, source_job_id: str, name: str, artifact: dict[str, Any]
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO training_models
                   (model_id, source_job_id, name, artifact_json, registered_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT DO NOTHING""",
                (
                    model_id,
                    source_job_id,
                    name,
                    json.dumps(artifact),
                    time.time(),
                ),
            )
            connection.execute(
                "UPDATE training_models SET name = ? WHERE model_id = ? OR source_job_id = ?",
                (name, model_id, source_job_id),
            )

    def models(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM training_models ORDER BY registered_at DESC"
            ).fetchall()
        return [
            {
                "modelId": row["model_id"],
                "sourceJobId": row["source_job_id"],
                "name": row["name"],
                **json.loads(row["artifact_json"]),
            }
            for row in rows
        ]


class TrainingJobManager:
    """Runs CFR trainers out of process with durable state and cancellation."""

    def __init__(self, command: Sequence[str], database_path: Path | None = None) -> None:
        if not command:
            raise ValueError("training command cannot be empty")
        self.command = tuple(command)
        self.store = TrainingJobStore(database_path) if database_path is not None else None
        self._jobs: dict[str, TrainingJob] = {}
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._lock = threading.Lock()

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        _validate_request(request)
        job = TrainingJob(f"train-{uuid4().hex[:12]}", dict(request))
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist(job)
        threading.Thread(target=self._run, args=(job.job_id,), daemon=True).start()
        return self.snapshot(job.job_id)

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._get(job_id)
            latest_checkpoint = self._latest_checkpoint(job)
            return {
                "jobId": job.job_id,
                "status": job.status,
                "game": job.request["game"],
                "algorithm": job.request["algorithm"],
                "mode": job.request["mode"],
                "events": list(job.events),
                "error": job.error,
                "checkpointHash": latest_checkpoint.get("checkpointHash")
                if latest_checkpoint
                else None,
            }

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("training job limit must be between 1 and 100")
        if self.store is None:
            with self._lock:
                jobs = list(reversed(list(self._jobs.values())))[:limit]
        else:
            jobs = self.store.recent(limit)
        return [
            {
                "jobId": job.job_id,
                "status": job.status,
                "game": job.request["game"],
                "algorithm": job.request["algorithm"],
                "mode": job.request["mode"],
                "iterations": job.request["iterations"],
                "seed": job.request["seed"],
                "error": job.error,
                "checkpointHash": (
                    checkpoint.get("checkpointHash")
                    if (checkpoint := self._latest_checkpoint(job))
                    else None
                ),
            }
            for job in jobs
        ]

    def checkpoint(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            checkpoint = self._latest_checkpoint(self._get(job_id))
            if checkpoint is None:
                raise ValueError("training job has no checkpoint yet")
            return json.loads(json.dumps(checkpoint))

    def register_model(self, job_id: str, name: str | None = None) -> dict[str, Any]:
        if self.store is None:
            raise ValueError("model registry requires persistent training storage")
        with self._lock:
            job = self._get(job_id)
            if job.status != "complete":
                raise ValueError("only completed training jobs can be registered")
            complete = next(
                (event for event in reversed(job.events) if event.get("event") == "complete"),
                None,
            )
            if complete is None or not isinstance(complete.get("checkpoint"), dict):
                raise ValueError("completed training job has no checkpoint artifact")
            artifact_hash = str(complete["artifactHash"])
            game = job.request["game"]
            game_labels = {
                "kuhn-poker": "Kuhn CFR",
                "leduc-holdem": "Leduc CFR",
                "restricted-hu-nlhe-flop": "Restricted Hold'em MCCFR",
            }
            model_prefixes = {
                "kuhn-poker": "kuhn-cfr",
                "leduc-holdem": "leduc-cfr",
                "restricted-hu-nlhe-flop": "restricted-hunl-mccfr",
            }
            game_label = game_labels[game]
            model_prefix = model_prefixes[game]
            model_id = f"{model_prefix}-{artifact_hash[:12]}"
            model_name = (name or f"{game_label} · {complete['iterations']:,} iterations").strip()
            if not model_name or len(model_name) > 80:
                raise ValueError("model name must contain 1 to 80 characters")
            artifact = {
                "game": job.request["game"],
                "algorithm": job.request["algorithm"],
                "version": "1.0.0",
                "iterations": complete["iterations"],
                "seed": job.request["seed"],
                "artifactHash": artifact_hash,
                "checkpointHash": complete["checkpoint"]["checkpointHash"],
                "strategy": complete.get("strategy", []),
            }
            if complete["checkpoint"].get("storage") == "sqlite-v1":
                artifact["checkpoint"] = complete["checkpoint"]
            for metric in ("gameValue", "exploitability", "referenceScore", "informationSets"):
                if metric in complete:
                    artifact[metric] = complete[metric]
            self.store.save_model(model_id, job_id, model_name, artifact)
        return next(model for model in self.models() if model["modelId"] == model_id)

    def models(self) -> list[dict[str, Any]]:
        if self.store is None:
            return []
        return self.store.models()

    def model_strategy(
        self, model_id: str, information_set: str, legal_actions: list[str] | None = None
    ) -> dict[str, Any]:
        model = next(
            (candidate for candidate in self.models() if candidate["modelId"] == model_id),
            None,
        )
        if model is None:
            raise KeyError(f"unknown training model: {model_id}")
        node = next(
            (
                candidate
                for candidate in model["strategy"]
                if candidate["informationSet"] == information_set
            ),
            None,
        )
        if node is None and model.get("checkpoint", {}).get("storage") == "sqlite-v1":
            path = Path(model["checkpoint"]["path"])
            with sqlite3.connect(path) as connection:
                row = connection.execute(
                    "SELECT actions_json, strategy_json FROM nodes WHERE information_set = ?",
                    (information_set,),
                ).fetchone()
            if row is not None:
                action_names = json.loads(row[0])
                strategy_sum = [float(value) for value in json.loads(row[1])]
                total = sum(strategy_sum)
                probabilities = (
                    [value / total for value in strategy_sum]
                    if total > 0
                    else [1.0 / len(action_names)] * len(action_names)
                )
                node = {"informationSet": information_set, "actions": dict(zip(action_names, probabilities))}
        if node is None:
            raise KeyError("model has no matching information set")
        actions = dict(node["actions"])
        if legal_actions is not None:
            if not legal_actions or any(action not in actions for action in legal_actions):
                raise ValueError("legalActions must contain known model actions")
            actions = {action: actions[action] for action in legal_actions}
        total = sum(actions.values())
        if total <= 0:
            probability = 1.0 / len(actions)
            actions = {action: probability for action in actions}
        else:
            actions = {action: probability / total for action, probability in actions.items()}
        return {
            "modelId": model_id,
            "game": model["game"],
            "informationSet": information_set,
            "actions": actions,
        }

    def resume(
        self,
        job_id: str,
        *,
        iterations: int,
        mode: str = "visual",
        report_every: int = 100,
    ) -> dict[str, Any]:
        with self._lock:
            original = self._get(job_id)
            checkpoint = self._latest_checkpoint(original)
            if checkpoint is None:
                raise ValueError("training job has no checkpoint to resume")
            if type(iterations) is not int or iterations <= checkpoint["completedIterations"]:
                raise ValueError("resume iterations must exceed the checkpoint iteration")
            request = {
                "schemaVersion": "1.0.0",
                "game": original.request["game"],
                "algorithm": original.request["algorithm"],
                "mode": mode,
                "iterations": iterations,
                "seed": original.request["seed"],
                "reportEvery": report_every,
                "checkpoint": checkpoint,
            }
        return self.submit(request)

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._get(job_id)
            if job.status not in ("complete", "failed", "cancelled"):
                job.status = "cancelled"
                job.error = "cancelled by user"
                self._persist(job)
            process = self._processes.get(job_id)
        if process is not None and process.poll() is None:
            process.terminate()
        return self.snapshot(job_id)

    def wait(self, job_id: str, timeout: float = 10.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snapshot = self.snapshot(job_id)
            if snapshot["status"] in ("complete", "failed", "cancelled"):
                return snapshot
            time.sleep(0.01)
        return self.snapshot(job_id)

    def _get(self, job_id: str) -> TrainingJob:
        job = self._jobs.get(job_id)
        if job is None and self.store is not None:
            job = self.store.load(job_id)
            if job is not None:
                self._jobs[job_id] = job
        if job is None:
            raise KeyError(f"unknown training job: {job_id}")
        return job

    @staticmethod
    def _latest_checkpoint(job: TrainingJob) -> dict[str, Any] | None:
        for event in reversed(job.events):
            if isinstance(event.get("checkpoint"), dict):
                return event["checkpoint"]
        return None

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status == "cancelled":
                return
            job.status = "running"
            self._persist(job)
            request_bytes = json.dumps(job.request, separators=(",", ":")).encode()
        try:
            process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                env={
                    **os.environ,
                    **(
                        {
                            "GAME_TRAINER_ARTIFACT_DIR": str(
                                self.store.path.parent / "training-artifacts"
                            ),
                            "GAME_TRAINER_ARTIFACT_NAME": job_id,
                        }
                        if self.store is not None
                        else {}
                    ),
                },
            )
            with self._lock:
                self._processes[job_id] = process
                cancelled = self._jobs[job_id].status == "cancelled"
            if cancelled:
                process.terminate()
            assert process.stdin is not None and process.stdout is not None
            if not cancelled:
                process.stdin.write(request_bytes)
            process.stdin.close()
            for line in process.stdout:
                event = json.loads(line)
                with self._lock:
                    job = self._jobs[job_id]
                    if job.status == "cancelled":
                        break
                    job.events.append(event)
                    self._persist(job)
            return_code = process.wait(timeout=5)
            stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
            process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            with self._lock:
                job = self._jobs[job_id]
                if job.status != "cancelled":
                    if return_code == 0 and job.events and job.events[-1].get("event") == "complete":
                        job.status = "complete"
                    else:
                        job.status = "failed"
                        job.error = (
                            job.events[-1].get("error")
                            if job.events
                            else stderr.strip() or f"worker exited {return_code}"
                        )
                    self._persist(job)
                self._processes.pop(job_id, None)
        except Exception as error:
            with self._lock:
                job = self._jobs[job_id]
                if job.status != "cancelled":
                    job.status = "failed"
                    job.error = str(error)
                    self._persist(job)
                self._processes.pop(job_id, None)

    def _persist(self, job: TrainingJob) -> None:
        if self.store is not None:
            self.store.save(job)
