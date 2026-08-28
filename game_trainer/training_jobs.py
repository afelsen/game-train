from __future__ import annotations

import json
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
                """
            )
            connection.execute(
                "UPDATE training_jobs SET status = 'failed', error = 'training process interrupted by restart', updated_at = ? WHERE status IN ('queued', 'running')",
                (time.time(),),
            )

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
